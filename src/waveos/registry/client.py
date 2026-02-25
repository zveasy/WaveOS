"""WaveOS Registry Client — mTLS, resumable downloads, chunk integrity verification."""

from __future__ import annotations

import hashlib
import json
import os
import ssl
import urllib.request
import urllib.error
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.registry.client")

_CHUNK_SIZE = 65536


@dataclass
class RegistryClientConfig:
    base_url: str = "https://localhost:9200"
    device_id: str = ""
    auth_token: str = ""
    ssl_cert: str = ""
    ssl_key: str = ""
    ssl_ca: str = ""
    verify_ssl: bool = True
    timeout_sec: float = 30.0
    retry_count: int = 3
    retry_backoff_sec: float = 2.0


class RegistryClient:
    """Client for WaveOS registry server with mTLS and resumable downloads."""

    def __init__(self, config: RegistryClientConfig) -> None:
        self.config = config
        self._ssl_context: Optional[ssl.SSLContext] = None
        if config.ssl_cert and config.ssl_key:
            self._ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            self._ssl_context.load_cert_chain(config.ssl_cert, config.ssl_key)
            if config.ssl_ca:
                self._ssl_context.load_verify_locations(config.ssl_ca)
            if not config.verify_ssl:
                self._ssl_context.check_hostname = False
                self._ssl_context.verify_mode = ssl.CERT_NONE
        elif not config.verify_ssl:
            self._ssl_context = ssl.create_default_context()
            self._ssl_context.check_hostname = False
            self._ssl_context.verify_mode = ssl.CERT_NONE

    def _request(self, method: str, path: str, body: Optional[bytes] = None,
                 headers: Optional[Dict[str, str]] = None) -> tuple[int, bytes]:
        url = f"{self.config.base_url.rstrip('/')}{path}"
        hdrs = {"X-Device-ID": self.config.device_id}
        if self.config.auth_token:
            hdrs["Authorization"] = f"Bearer {self.config.auth_token}"
        if headers:
            hdrs.update(headers)
        req = urllib.request.Request(url, data=body, headers=hdrs, method=method)
        for attempt in range(self.config.retry_count):
            try:
                ctx = self._ssl_context if self._ssl_context else None
                with urllib.request.urlopen(req, timeout=self.config.timeout_sec, context=ctx) as resp:
                    return resp.status, resp.read()
            except urllib.error.HTTPError as exc:
                return exc.code, exc.read()
            except (urllib.error.URLError, OSError) as exc:
                if attempt < self.config.retry_count - 1:
                    import time
                    time.sleep(self.config.retry_backoff_sec * (2 ** attempt))
                else:
                    raise

    def list_bundles(self, channel: Optional[str] = None) -> List[Dict[str, Any]]:
        path = "/v1/bundles"
        if channel:
            path += f"?channel={channel}"
        code, data = self._request("GET", path)
        if code == 200:
            return json.loads(data)
        return []

    def get_entry(self, bundle_id: str) -> Optional[Dict[str, Any]]:
        code, data = self._request("GET", f"/v1/bundles/{bundle_id}")
        if code == 200:
            return json.loads(data)
        return None

    def download_file(self, bundle_id: str, filename: str, dest: Path,
                      expected_sha256: str = "") -> Dict[str, Any]:
        """Download a file from a bundle with resumable support and integrity check."""
        dest.parent.mkdir(parents=True, exist_ok=True)
        existing_size = dest.stat().st_size if dest.exists() else 0
        headers = {}
        if existing_size > 0:
            headers["Range"] = f"bytes={existing_size}-"

        url = f"{self.config.base_url.rstrip('/')}/v1/bundles/{bundle_id}/{filename}"
        hdrs = {"X-Device-ID": self.config.device_id}
        if self.config.auth_token:
            hdrs["Authorization"] = f"Bearer {self.config.auth_token}"
        hdrs.update(headers)

        req = urllib.request.Request(url, headers=hdrs, method="GET")
        ctx = self._ssl_context if self._ssl_context else None

        try:
            with urllib.request.urlopen(req, timeout=self.config.timeout_sec, context=ctx) as resp:
                mode = "ab" if resp.status == 206 else "wb"
                sha256 = hashlib.sha256()
                downloaded = 0
                with dest.open(mode) as f:
                    while True:
                        chunk = resp.read(_CHUNK_SIZE)
                        if not chunk:
                            break
                        f.write(chunk)
                        sha256.update(chunk)
                        downloaded += len(chunk)

                actual_hash = sha256.hexdigest()
                if expected_sha256 and mode == "wb" and actual_hash != expected_sha256:
                    return {"ok": False, "error": "checksum mismatch",
                            "expected": expected_sha256, "actual": actual_hash}

                return {"ok": True, "bytes": downloaded, "resumed": mode == "ab",
                        "sha256": actual_hash}
        except (urllib.error.HTTPError, urllib.error.URLError, OSError) as exc:
            return {"ok": False, "error": str(exc)}

    def download_bundle(self, bundle_id: str, dest_dir: Path) -> Dict[str, Any]:
        """Download all bundle files to a local directory."""
        entry = self.get_entry(bundle_id)
        if not entry:
            return {"ok": False, "error": "bundle not found"}
        dest_dir.mkdir(parents=True, exist_ok=True)
        manifest_result = self.download_file(bundle_id, "bundle.json", dest_dir / "bundle.json")
        if not manifest_result.get("ok"):
            return manifest_result
        try:
            manifest = json.loads((dest_dir / "bundle.json").read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            return {"ok": False, "error": f"cannot read manifest: {exc}"}

        results = [manifest_result]
        for artifact in manifest.get("artifacts", []):
            art_path = artifact.get("path", "")
            art_sha = artifact.get("sha256", "")
            if art_path and art_path != "bundle.json":
                r = self.download_file(bundle_id, art_path, dest_dir / art_path, expected_sha256=art_sha)
                results.append(r)
                if not r.get("ok"):
                    return {"ok": False, "error": f"failed to download {art_path}", "details": r}

        for extra in ["bundle.sig", "attestation.json", "sbom.json", "checksums.txt"]:
            r = self.download_file(bundle_id, extra, dest_dir / extra)
            if r.get("ok"):
                results.append(r)

        return {"ok": True, "bundle_id": bundle_id, "files": len(results)}

    def publish(self, bundle_path: str, channel: str = "dev") -> Dict[str, Any]:
        body = json.dumps({"bundle_path": bundle_path, "channel": channel}).encode()
        code, data = self._request("POST", "/v1/bundles", body=body,
                                    headers={"Content-Type": "application/json"})
        if code in (200, 201):
            return json.loads(data)
        return {"ok": False, "code": code, "error": data.decode(errors="replace")}

    def promote(self, bundle_id: str, target_channel: str, approver: str = "") -> Dict[str, Any]:
        body = json.dumps({"channel": target_channel, "approver": approver}).encode()
        code, data = self._request("POST", f"/v1/bundles/{bundle_id}/promote", body=body,
                                    headers={"Content-Type": "application/json"})
        if code == 200:
            return json.loads(data)
        return {"ok": False, "code": code, "error": data.decode(errors="replace")}

    def health(self) -> Dict[str, Any]:
        try:
            code, data = self._request("GET", "/v1/health")
            if code == 200:
                return json.loads(data)
        except Exception:
            pass
        return {"status": "unreachable"}
