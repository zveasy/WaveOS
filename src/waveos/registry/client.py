"""WaveOS Registry Client — mTLS, resumable downloads, chunk hash verification."""

from __future__ import annotations

import hashlib
import json
import os
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any, Dict, List, Optional

from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.registry.client")


class RegistryClient:
    """HTTP client for the WaveOS registry server."""

    def __init__(
        self,
        base_url: str = "http://localhost:9200",
        device_id: str = "",
        token: str = "",
        cert_path: Optional[str] = None,
        key_path: Optional[str] = None,
        ca_path: Optional[str] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.device_id = device_id
        self.token = token
        self.cert_path = cert_path
        self.key_path = key_path
        self.ca_path = ca_path
        self._ssl_ctx = self._build_ssl_context()

    def _build_ssl_context(self):
        if not self.base_url.startswith("https"):
            return None
        try:
            import ssl
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ctx.minimum_version = ssl.TLSVersion.TLSv1_2
            if self.cert_path and self.key_path:
                ctx.load_cert_chain(self.cert_path, self.key_path)
            if self.ca_path:
                ctx.load_verify_locations(self.ca_path)
            else:
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
            return ctx
        except Exception as exc:
            logger.warning("SSL context failed: %s", exc)
            return None

    def _headers(self) -> Dict[str, str]:
        h: Dict[str, str] = {"Content-Type": "application/json"}
        if self.device_id:
            h["X-Device-ID"] = self.device_id
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    def _request(self, method: str, path: str, data: Optional[bytes] = None, extra_headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        headers = self._headers()
        if extra_headers:
            headers.update(extra_headers)
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            handler = urllib.request.HTTPSHandler(context=self._ssl_ctx) if self._ssl_ctx else urllib.request.HTTPHandler()
            opener = urllib.request.build_opener(handler)
            with opener.open(req, timeout=30) as resp:
                body = resp.read()
                return {"status": resp.status, "data": json.loads(body) if body else {}, "headers": dict(resp.headers)}
        except urllib.error.HTTPError as exc:
            body = exc.read()
            return {"status": exc.code, "data": json.loads(body) if body else {"error": str(exc)}, "headers": {}}
        except (urllib.error.URLError, OSError) as exc:
            return {"status": 0, "data": {"error": str(exc)}, "headers": {}}

    def list_bundles(self, channel: Optional[str] = None) -> List[Dict[str, Any]]:
        path = "/v1/bundles"
        if channel:
            path += f"?channel={channel}"
        resp = self._request("GET", path)
        if resp["status"] == 200:
            return resp["data"]
        return []

    def get_entry(self, bundle_id: str) -> Optional[Dict[str, Any]]:
        resp = self._request("GET", f"/v1/bundles/{bundle_id}")
        if resp["status"] == 200:
            return resp["data"]
        return None

    def download_file(
        self,
        bundle_id: str,
        file_name: str,
        dest_path: Path,
        chunk_size: int = 1024 * 1024,
        expected_sha256: str = "",
    ) -> Dict[str, Any]:
        """Download a file with resumable range requests and chunk hash verification."""
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        downloaded = 0
        if dest_path.exists():
            downloaded = dest_path.stat().st_size

        url = f"{self.base_url}/v1/bundles/{bundle_id}/download/{file_name}"
        headers = self._headers()
        full_hash = hashlib.sha256()

        if downloaded > 0:
            with dest_path.open("rb") as f:
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    full_hash.update(chunk)

        while True:
            range_header = f"bytes={downloaded}-"
            headers["Range"] = range_header
            req = urllib.request.Request(url, headers=headers, method="GET")
            try:
                handler = urllib.request.HTTPSHandler(context=self._ssl_ctx) if self._ssl_ctx else urllib.request.HTTPHandler()
                opener = urllib.request.build_opener(handler)
                with opener.open(req, timeout=60) as resp:
                    chunk_data = resp.read()
                    if not chunk_data:
                        break
                    chunk_hash = hashlib.sha256(chunk_data).hexdigest()
                    server_hash = resp.headers.get("X-Content-SHA256", "")
                    if server_hash and server_hash != chunk_hash:
                        return {"ok": False, "error": f"Chunk hash mismatch at offset {downloaded}", "downloaded": downloaded}
                    full_hash.update(chunk_data)
                    with dest_path.open("ab") as f:
                        f.write(chunk_data)
                    downloaded += len(chunk_data)
                    if resp.status == 200:
                        break
            except (urllib.error.HTTPError, urllib.error.URLError, OSError) as exc:
                logger.warning("Download interrupted at %d bytes: %s", downloaded, exc)
                return {"ok": False, "error": str(exc), "downloaded": downloaded, "resumable": True}

        result: Dict[str, Any] = {"ok": True, "downloaded": downloaded, "path": str(dest_path)}
        if expected_sha256:
            actual = full_hash.hexdigest()
            if actual != expected_sha256:
                result["ok"] = False
                result["error"] = f"Full hash mismatch: expected {expected_sha256[:16]}..., got {actual[:16]}..."
        return result

    def download_bundle(self, bundle_id: str, dest_dir: Path) -> Dict[str, Any]:
        """Download all bundle files to a local directory."""
        entry = self.get_entry(bundle_id)
        if not entry:
            return {"ok": False, "error": "Bundle not found"}
        dest_dir.mkdir(parents=True, exist_ok=True)
        manifest_result = self.download_file(bundle_id, "bundle.json", dest_dir / "bundle.json")
        if not manifest_result.get("ok"):
            return manifest_result
        try:
            manifest_data = json.loads((dest_dir / "bundle.json").read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            return {"ok": False, "error": f"Cannot parse manifest: {exc}"}
        artifacts = manifest_data.get("artifacts", [])
        for artifact in artifacts:
            art_path = artifact.get("path", "")
            art_sha = artifact.get("sha256", "")
            if not art_path:
                continue
            result = self.download_file(bundle_id, art_path, dest_dir / art_path, expected_sha256=art_sha)
            if not result.get("ok"):
                return result
        for extra in ["bundle.sig", "attestation.json", "sbom.json", "checksums.txt"]:
            self.download_file(bundle_id, extra, dest_dir / extra)
        return {"ok": True, "bundle_id": bundle_id, "dest_dir": str(dest_dir), "artifact_count": len(artifacts)}

    def publish(self, bundle_dir: str, channel: str = "dev", publisher: str = "") -> Dict[str, Any]:
        data = json.dumps({"bundle_dir": bundle_dir, "channel": channel, "publisher": publisher or self.device_id}).encode()
        headers = {"X-Publisher-Type": "ci"}
        resp = self._request("POST", "/v1/publish", data=data, extra_headers=headers)
        return resp.get("data", {})

    def health(self) -> Dict[str, Any]:
        resp = self._request("GET", "/v1/health")
        return resp.get("data", {})
