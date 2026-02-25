"""WaveOS Registry Client — secure bundle download with mTLS, resumable transfers, and integrity verification."""

from __future__ import annotations

import hashlib
import json
import os
import ssl
import tarfile
import tempfile
import io
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.registry.client")


class RegistryClient:
    """Client for the WaveOS registry server."""

    def __init__(
        self,
        base_url: str = "https://localhost:9200",
        token: str = "",
        tls_cert: str = "",
        tls_key: str = "",
        tls_ca: str = "",
        timeout: float = 30.0,
        chunk_size: int = 1024 * 1024,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token or os.getenv("WAVEOS_REGISTRY_TOKEN", "")
        self.timeout = timeout
        self.chunk_size = chunk_size
        self._ssl_ctx: Optional[ssl.SSLContext] = None
        tls_cert = tls_cert or os.getenv("WAVEOS_REGISTRY_CLIENT_CERT", "")
        tls_key = tls_key or os.getenv("WAVEOS_REGISTRY_CLIENT_KEY", "")
        tls_ca = tls_ca or os.getenv("WAVEOS_REGISTRY_CLIENT_CA", "")
        if tls_cert and tls_key:
            self._ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            self._ssl_ctx.load_cert_chain(tls_cert, tls_key)
            if tls_ca:
                self._ssl_ctx.load_verify_locations(tls_ca)
            else:
                self._ssl_ctx.check_hostname = False
                self._ssl_ctx.verify_mode = ssl.CERT_NONE
        elif self.base_url.startswith("https"):
            self._ssl_ctx = ssl.create_default_context()
            if tls_ca:
                self._ssl_ctx.load_verify_locations(tls_ca)

    def _headers(self) -> Dict[str, str]:
        h: Dict[str, str] = {"User-Agent": "waveos-agent/1.0"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    def _request(self, method: str, path: str, data: Optional[bytes] = None, extra_headers: Optional[Dict[str, str]] = None) -> tuple:
        url = f"{self.base_url}{path}"
        headers = {**self._headers(), **(extra_headers or {})}
        req = Request(url, data=data, headers=headers, method=method)
        try:
            ctx = self._ssl_ctx if self.base_url.startswith("https") else None
            resp = urlopen(req, timeout=self.timeout, context=ctx)
            return resp.status, resp.read(), dict(resp.headers)
        except HTTPError as exc:
            return exc.code, exc.read(), dict(exc.headers)
        except (URLError, OSError) as exc:
            logger.warning("Registry request failed: %s", exc)
            return 0, b"", {}

    def list_bundles(self, channel: Optional[str] = None) -> List[Dict[str, Any]]:
        path = "/v1/bundles"
        if channel:
            path += f"?channel={channel}"
        status, body, _ = self._request("GET", path)
        if status == 200:
            return json.loads(body)
        return []

    def get_entry(self, bundle_id: str) -> Optional[Dict[str, Any]]:
        status, body, _ = self._request("GET", f"/v1/bundles/{bundle_id}")
        if status == 200:
            return json.loads(body)
        return None

    def download_bundle(self, bundle_id: str, output_dir: Path, resumable: bool = True) -> Optional[Path]:
        """Download a bundle with optional resumable transfer and integrity verification."""
        output_dir.mkdir(parents=True, exist_ok=True)
        cache_path = output_dir / f"{bundle_id}.tar.gz"

        existing_size = cache_path.stat().st_size if cache_path.exists() else 0

        if resumable and existing_size > 0:
            status, chunk, headers = self._request(
                "GET", f"/v1/bundles/{bundle_id}/download",
                extra_headers={"Range": f"bytes={existing_size}-"},
            )
            if status == 206:
                with cache_path.open("ab") as f:
                    f.write(chunk)
                logger.info("Resumed download for %s from byte %d", bundle_id, existing_size)
            elif status == 200:
                cache_path.write_bytes(chunk)
        else:
            status, content, headers = self._request("GET", f"/v1/bundles/{bundle_id}/download")
            if status != 200:
                logger.warning("Download failed: status=%d", status)
                return None
            cache_path.write_bytes(content)

        expected_hash = ""
        if isinstance(headers, dict):
            expected_hash = headers.get("X-Content-SHA256", headers.get("x-content-sha256", ""))

        actual_hash = hashlib.sha256(cache_path.read_bytes()).hexdigest()
        if expected_hash and actual_hash != expected_hash:
            logger.error("Integrity check failed for %s: expected %s, got %s", bundle_id, expected_hash[:16], actual_hash[:16])
            cache_path.unlink(missing_ok=True)
            return None

        extract_dir = output_dir / bundle_id
        extract_dir.mkdir(parents=True, exist_ok=True)
        try:
            with tarfile.open(str(cache_path), "r:gz") as tar:
                tar.extractall(str(extract_dir), filter="data")
        except (tarfile.TarError, OSError) as exc:
            logger.error("Extract failed for %s: %s", bundle_id, exc)
            return None

        subdirs = [d for d in extract_dir.iterdir() if d.is_dir()]
        return subdirs[0] if subdirs else extract_dir

    def publish_bundle(self, bundle_dir: Path, channel: str = "dev") -> Optional[Dict[str, Any]]:
        """Publish a bundle to the registry."""
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            tar.add(str(bundle_dir), arcname=bundle_dir.name)
        data = buf.getvalue()
        status, body, _ = self._request(
            "POST", "/v1/bundles/publish",
            data=data,
            extra_headers={"Content-Type": "application/gzip", "X-Channel": channel},
        )
        if status in (200, 201):
            return json.loads(body)
        logger.warning("Publish failed: status=%d", status)
        return None

    def health(self) -> Dict[str, Any]:
        status, body, _ = self._request("GET", "/v1/health")
        if status == 200:
            return json.loads(body)
        return {"status": "unreachable", "code": status}
