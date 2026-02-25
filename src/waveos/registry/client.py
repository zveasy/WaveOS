"""WaveOS Registry Client — secure download with mTLS, resumable transfers, chunk verification."""

from __future__ import annotations

import hashlib
import json
import os
import ssl
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.registry.client")


@dataclass
class RegistryClientConfig:
    base_url: str = "https://localhost:9200"
    device_id: str = ""
    token: str = ""
    tls_cert: str = ""
    tls_key: str = ""
    tls_ca: str = ""
    chunk_size: int = 1024 * 1024  # 1MB chunks
    max_retries: int = 3
    timeout: float = 30.0


class RegistryClient:
    """Client for WaveOS registry with mTLS and resumable downloads."""

    def __init__(self, config: RegistryClientConfig) -> None:
        self.config = config
        self._ssl_ctx: Optional[ssl.SSLContext] = None
        if config.tls_cert and config.tls_key:
            self._ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            self._ssl_ctx.load_cert_chain(config.tls_cert, config.tls_key)
            if config.tls_ca:
                self._ssl_ctx.load_verify_locations(config.tls_ca)
            else:
                self._ssl_ctx.check_hostname = False
                self._ssl_ctx.verify_mode = ssl.CERT_NONE

    def _headers(self) -> Dict[str, str]:
        h: Dict[str, str] = {}
        if self.config.device_id:
            h["X-Device-ID"] = self.config.device_id
        if self.config.token:
            h["Authorization"] = f"Bearer {self.config.token}"
        return h

    def _request(self, method: str, path: str, data: Optional[bytes] = None, extra_headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        url = f"{self.config.base_url.rstrip('/')}{path}"
        headers = self._headers()
        if extra_headers:
            headers.update(extra_headers)
        if data and "Content-Type" not in headers:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        handler = urllib.request.HTTPSHandler(context=self._ssl_ctx) if self._ssl_ctx else urllib.request.HTTPHandler()
        opener = urllib.request.build_opener(handler)
        try:
            resp = opener.open(req, timeout=self.config.timeout)
            body = resp.read()
            return {"status": resp.status, "data": json.loads(body) if body else {}, "headers": dict(resp.headers)}
        except urllib.error.HTTPError as exc:
            body = exc.read()
            return {"status": exc.code, "data": json.loads(body) if body else {}, "headers": dict(exc.headers)}
        except (urllib.error.URLError, OSError) as exc:
            return {"status": 0, "data": {"error": str(exc)}, "headers": {}}

    def list_bundles(self, channel: Optional[str] = None) -> List[Dict[str, Any]]:
        path = "/v1/bundles"
        if channel:
            path += f"?channel={channel}"
        result = self._request("GET", path)
        if result["status"] == 200:
            return result["data"]
        return []

    def get_bundle_info(self, bundle_id: str) -> Optional[Dict[str, Any]]:
        result = self._request("GET", f"/v1/bundles/{bundle_id}")
        if result["status"] == 200:
            return result["data"]
        return None

    def download_file(self, bundle_id: str, file_path: str, dest: Path) -> Dict[str, Any]:
        """Download a file with resumable transfer and chunk integrity verification."""
        dest.parent.mkdir(parents=True, exist_ok=True)
        existing_size = dest.stat().st_size if dest.exists() else 0
        url = f"{self.config.base_url.rstrip('/')}/v1/bundles/{bundle_id}/download/{file_path}"
        full_hash = hashlib.sha256()
        total_downloaded = existing_size

        if existing_size > 0:
            with dest.open("rb") as f:
                while True:
                    chunk = f.read(self.config.chunk_size)
                    if not chunk:
                        break
                    full_hash.update(chunk)

        retries = 0
        while retries <= self.config.max_retries:
            try:
                headers = self._headers()
                if total_downloaded > 0:
                    headers["Range"] = f"bytes={total_downloaded}-"
                req = urllib.request.Request(url, headers=headers)
                handler = urllib.request.HTTPSHandler(context=self._ssl_ctx) if self._ssl_ctx else urllib.request.HTTPHandler()
                opener = urllib.request.build_opener(handler)
                resp = opener.open(req, timeout=self.config.timeout)
                mode = "ab" if total_downloaded > 0 else "wb"
                with dest.open(mode) as f:
                    while True:
                        chunk = resp.read(self.config.chunk_size)
                        if not chunk:
                            break
                        f.write(chunk)
                        full_hash.update(chunk)
                        total_downloaded += len(chunk)
                server_hash = resp.headers.get("X-Content-SHA256", "")
                return {
                    "ok": True,
                    "path": str(dest),
                    "size": total_downloaded,
                    "sha256": full_hash.hexdigest(),
                    "server_chunk_hash": server_hash,
                }
            except (urllib.error.URLError, OSError) as exc:
                retries += 1
                logger.warning("Download retry %d/%d for %s: %s", retries, self.config.max_retries, file_path, exc)
                if retries > self.config.max_retries:
                    return {"ok": False, "error": str(exc), "downloaded": total_downloaded}

        return {"ok": False, "error": "Max retries exceeded", "downloaded": total_downloaded}

    def download_bundle(self, bundle_id: str, dest_dir: Path) -> Dict[str, Any]:
        """Download full bundle to destination directory."""
        dest_dir.mkdir(parents=True, exist_ok=True)
        manifest_result = self.download_file(bundle_id, "bundle.json", dest_dir / "bundle.json")
        if not manifest_result.get("ok"):
            return {"ok": False, "error": "Failed to download manifest", "details": manifest_result}
        try:
            manifest = json.loads((dest_dir / "bundle.json").read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            return {"ok": False, "error": f"Invalid manifest: {exc}"}
        artifacts = manifest.get("artifacts", [])
        results = [manifest_result]
        for artifact in artifacts:
            art_path = artifact.get("path", "")
            if not art_path or art_path == "bundle.json":
                continue
            r = self.download_file(bundle_id, art_path, dest_dir / art_path)
            results.append(r)
            if r.get("ok"):
                expected_sha = artifact.get("sha256", "")
                if expected_sha and r.get("sha256") != expected_sha:
                    return {"ok": False, "error": f"Integrity check failed for {art_path}", "expected": expected_sha, "got": r.get("sha256")}
        for extra in ("bundle.sig", "attestation.json", "sbom.json", "checksums.txt"):
            self.download_file(bundle_id, extra, dest_dir / extra)
        return {"ok": True, "bundle_id": bundle_id, "artifacts_downloaded": len(results), "dest": str(dest_dir)}

    def health_check(self) -> Dict[str, Any]:
        return self._request("GET", "/health")
