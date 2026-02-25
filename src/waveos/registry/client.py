"""Registry client — mTLS, resumable downloads, chunk verification."""

from __future__ import annotations

import hashlib
import json
import os
import ssl
import tempfile
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any, Dict, List, Optional

from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.registry.client")


class RegistryClient:
    """HTTP client for WaveOS registry with mTLS and resumable downloads."""

    def __init__(self, base_url: str, token: Optional[str] = None,
                 cert_path: Optional[str] = None, key_path: Optional[str] = None,
                 ca_path: Optional[str] = None, timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self._ssl_context: Optional[ssl.SSLContext] = None
        if cert_path and key_path:
            self._ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            self._ssl_context.load_cert_chain(cert_path, key_path)
            if ca_path:
                self._ssl_context.load_verify_locations(ca_path)
            else:
                self._ssl_context.check_hostname = False
                self._ssl_context.verify_mode = ssl.CERT_NONE

    def _build_request(self, path: str, method: str = "GET", data: Optional[bytes] = None,
                       headers: Optional[Dict[str, str]] = None) -> urllib.request.Request:
        url = f"{self.base_url}{path}"
        req = urllib.request.Request(url, data=data, method=method)
        if self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        if headers:
            for k, v in headers.items():
                req.add_header(k, v)
        return req

    def _do_request(self, req: urllib.request.Request) -> tuple[int, bytes, Dict[str, str]]:
        try:
            ctx = self._ssl_context if self.base_url.startswith("https") else None
            with urllib.request.urlopen(req, timeout=self.timeout, context=ctx) as resp:
                headers = {k.lower(): v for k, v in resp.getheaders()}
                return resp.status, resp.read(), headers
        except urllib.error.HTTPError as e:
            return e.code, e.read(), {}
        except (urllib.error.URLError, OSError) as e:
            logger.warning("Registry request failed: %s", e)
            return 0, b"", {}

    def health(self) -> Dict[str, Any]:
        req = self._build_request("/v1/health")
        status, body, _ = self._do_request(req)
        if status == 200:
            return json.loads(body)
        return {"status": "error", "code": status}

    def list_bundles(self, channel: Optional[str] = None) -> List[Dict[str, Any]]:
        path = "/v1/bundles"
        if channel:
            path += f"?channel={channel}"
        req = self._build_request(path)
        status, body, _ = self._do_request(req)
        if status == 200:
            return json.loads(body)
        return []

    def get_entry(self, bundle_id: str) -> Optional[Dict[str, Any]]:
        req = self._build_request(f"/v1/bundles/{bundle_id}")
        status, body, _ = self._do_request(req)
        if status == 200:
            return json.loads(body)
        return None

    def download_file(self, bundle_id: str, file_path: str = "", output_path: Optional[Path] = None,
                      chunk_size: int = 65536, resume: bool = True) -> Optional[Path]:
        """Download a file with resumable support and integrity verification."""
        url_path = f"/v1/download/{bundle_id}"
        if file_path:
            url_path += f"/{file_path}"
        if output_path is None:
            output_path = Path(tempfile.mktemp(suffix=f"_{file_path or 'bundle.json'}"))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        existing_size = 0
        if resume and output_path.exists():
            existing_size = output_path.stat().st_size
        headers: Dict[str, str] = {}
        if existing_size > 0:
            headers["Range"] = f"bytes={existing_size}-"
        req = self._build_request(url_path, headers=headers)
        try:
            ctx = self._ssl_context if self.base_url.startswith("https") else None
            with urllib.request.urlopen(req, timeout=self.timeout, context=ctx) as resp:
                expected_hash = resp.headers.get("X-Content-SHA256", "")
                mode = "ab" if existing_size > 0 and resp.status == 206 else "wb"
                hasher = hashlib.sha256()
                if mode == "ab" and output_path.exists():
                    hasher.update(output_path.read_bytes())
                with output_path.open(mode) as f:
                    while True:
                        chunk = resp.read(chunk_size)
                        if not chunk:
                            break
                        f.write(chunk)
                        hasher.update(chunk)
                if expected_hash:
                    actual_hash = hasher.hexdigest()
                    if actual_hash != expected_hash:
                        logger.error("Integrity check failed for %s: expected %s got %s",
                                   file_path, expected_hash[:16], actual_hash[:16])
                        return None
                return output_path
        except (urllib.error.HTTPError, urllib.error.URLError, OSError) as e:
            logger.warning("Download failed: %s", e)
            return None

    def download_bundle(self, bundle_id: str, output_dir: Path, resume: bool = True) -> Optional[Path]:
        """Download a complete bundle (manifest + all artifacts)."""
        output_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = self.download_file(bundle_id, "", output_dir / "bundle.json", resume=resume)
        if not manifest_path or not manifest_path.exists():
            return None
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        for artifact in manifest.get("artifacts", []):
            art_path = artifact.get("path", "")
            if art_path and art_path != "bundle.json":
                result = self.download_file(bundle_id, art_path, output_dir / art_path, resume=resume)
                if not result:
                    logger.warning("Failed to download artifact: %s", art_path)
        for extra in ["bundle.sig", "attestation.json", "sbom.json", "checksums.txt"]:
            self.download_file(bundle_id, extra, output_dir / extra, resume=resume)
        return output_dir
