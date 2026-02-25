"""WaveOS Registry Client — secure bundle download with mTLS, resumable transfers, and chunk verification."""

from __future__ import annotations

import hashlib
import json
import os
import ssl
import tempfile
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.registry.client")


@dataclass
class RegistryClientConfig:
    registry_url: str = "https://localhost:9200"
    auth_token: str = ""
    tls_cert: str = ""
    tls_key: str = ""
    tls_ca: str = ""
    verify_ssl: bool = True
    device_id: str = ""
    site_id: str = ""
    timeout_sec: float = 30.0
    chunk_size: int = 65536
    max_retries: int = 3


class RegistryClient:
    """Client for the WaveOS registry server."""

    def __init__(self, config: Optional[RegistryClientConfig] = None) -> None:
        self.config = config or RegistryClientConfig()
        self._ssl_context = self._build_ssl_context()

    def _build_ssl_context(self) -> Optional[ssl.SSLContext]:
        if not self.config.registry_url.startswith("https"):
            return None
        ctx = ssl.create_default_context()
        if self.config.tls_ca:
            ctx.load_verify_locations(self.config.tls_ca)
        if self.config.tls_cert and self.config.tls_key:
            ctx.load_cert_chain(self.config.tls_cert, self.config.tls_key)
        if not self.config.verify_ssl:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        return ctx

    def _request(self, method: str, path: str, body: Optional[bytes] = None, headers: Optional[Dict[str, str]] = None, timeout: Optional[float] = None) -> Dict[str, Any]:
        url = f"{self.config.registry_url.rstrip('/')}{path}"
        hdrs = {"Content-Type": "application/json"}
        if self.config.auth_token:
            hdrs["Authorization"] = f"Bearer {self.config.auth_token}"
        if self.config.device_id:
            hdrs["X-WaveOS-Identity"] = json.dumps({"device_id": self.config.device_id, "site_id": self.config.site_id})
        if headers:
            hdrs.update(headers)
        req = urllib.request.Request(url, data=body, headers=hdrs, method=method)
        t = timeout or self.config.timeout_sec
        try:
            with urllib.request.urlopen(req, timeout=t, context=self._ssl_context) as resp:
                data = resp.read()
                return {"status": resp.status, "body": json.loads(data) if data else {}, "headers": dict(resp.headers)}
        except urllib.error.HTTPError as exc:
            body_text = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            try:
                error_body = json.loads(body_text)
            except json.JSONDecodeError:
                error_body = {"raw": body_text}
            return {"status": exc.code, "body": error_body, "headers": dict(exc.headers) if exc.headers else {}}
        except (urllib.error.URLError, OSError) as exc:
            return {"status": 0, "body": {"error": str(exc)}, "headers": {}}

    def list_bundles(self, channel: Optional[str] = None) -> List[Dict[str, Any]]:
        path = "/v1/bundles"
        if channel:
            path += f"?channel={channel}"
        resp = self._request("GET", path)
        if resp["status"] == 200:
            return resp["body"].get("bundles", [])
        return []

    def get_entry(self, bundle_id: str) -> Optional[Dict[str, Any]]:
        resp = self._request("GET", f"/v1/bundles/{bundle_id}")
        if resp["status"] == 200:
            return resp["body"]
        return None

    def download_file(self, bundle_id: str, file_name: str, dest_path: Path, expected_sha256: str = "") -> Dict[str, Any]:
        """Download a single file with resume support and integrity verification."""
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        existing_size = dest_path.stat().st_size if dest_path.exists() else 0
        headers: Dict[str, str] = {}
        if existing_size > 0:
            headers["Range"] = f"bytes={existing_size}-"
        url_path = f"/v1/bundles/{bundle_id}/download/{file_name}" if file_name else f"/v1/bundles/{bundle_id}/download"
        url = f"{self.config.registry_url.rstrip('/')}{url_path}"
        hdrs = {"Accept": "application/octet-stream"}
        if self.config.auth_token:
            hdrs["Authorization"] = f"Bearer {self.config.auth_token}"
        hdrs.update(headers)
        req = urllib.request.Request(url, headers=hdrs)
        try:
            with urllib.request.urlopen(req, timeout=self.config.timeout_sec, context=self._ssl_context) as resp:
                server_hash = resp.headers.get("X-Content-SHA256", "")
                mode = "ab" if existing_size > 0 and resp.status == 206 else "wb"
                hasher = hashlib.sha256()
                total = 0
                with dest_path.open(mode) as f:
                    while True:
                        chunk = resp.read(self.config.chunk_size)
                        if not chunk:
                            break
                        hasher.update(chunk)
                        f.write(chunk)
                        total += len(chunk)
                if mode == "wb":
                    actual_hash = hasher.hexdigest()
                else:
                    actual_hash = hashlib.sha256(dest_path.read_bytes()).hexdigest()
                if expected_sha256 and actual_hash != expected_sha256:
                    return {"ok": False, "error": "hash_mismatch", "expected": expected_sha256, "actual": actual_hash}
                if server_hash and actual_hash != server_hash:
                    return {"ok": False, "error": "server_hash_mismatch", "expected": server_hash, "actual": actual_hash}
                return {"ok": True, "path": str(dest_path), "size": total, "sha256": actual_hash, "resumed": mode == "ab"}
        except (urllib.error.URLError, OSError) as exc:
            return {"ok": False, "error": str(exc)}

    def download_bundle(self, bundle_id: str, dest_dir: Path) -> Dict[str, Any]:
        """Download entire bundle with integrity verification."""
        entry = self.get_entry(bundle_id)
        if not entry:
            return {"ok": False, "error": "bundle_not_found"}
        dest_dir.mkdir(parents=True, exist_ok=True)
        manifest_result = self.download_file(bundle_id, "", dest_dir / "bundle.json")
        if not manifest_result.get("ok"):
            return {"ok": False, "error": f"manifest_download_failed: {manifest_result.get('error')}"}
        try:
            manifest = json.loads((dest_dir / "bundle.json").read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            return {"ok": False, "error": f"manifest_parse_failed: {exc}"}
        results: List[Dict[str, Any]] = [manifest_result]
        for artifact in manifest.get("artifacts", []):
            art_path = artifact.get("path", "")
            art_sha = artifact.get("sha256", "")
            if art_path:
                r = self.download_file(bundle_id, art_path, dest_dir / art_path, expected_sha256=art_sha)
                results.append(r)
                if not r.get("ok"):
                    return {"ok": False, "error": f"artifact_failed: {art_path}: {r.get('error')}", "results": results}
        for extra in ["bundle.sig", "attestation.json", "sbom.json", "checksums.txt"]:
            r = self.download_file(bundle_id, extra, dest_dir / extra)
            if r.get("ok"):
                results.append(r)
        return {"ok": True, "bundle_id": bundle_id, "dest_dir": str(dest_dir), "files_downloaded": len(results)}

    def publish(self, bundle_path: str, channel: str = "dev") -> Dict[str, Any]:
        body = json.dumps({"bundle_path": bundle_path, "channel": channel}).encode("utf-8")
        resp = self._request("POST", "/v1/bundles/publish", body=body)
        return resp["body"]

    def health(self) -> Dict[str, Any]:
        resp = self._request("GET", "/v1/health")
        return resp["body"]
