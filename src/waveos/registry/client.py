"""WaveOS Registry Client — mTLS, resumable downloads, chunk integrity."""

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


@dataclass
class RegistryClientConfig:
    base_url: str = "https://localhost:9200"
    auth_token: str = ""
    tls_cert: str = ""
    tls_key: str = ""
    tls_ca: str = ""
    verify_ssl: bool = True
    chunk_size: int = 1024 * 1024  # 1MB chunks for resumable downloads
    max_retries: int = 3
    timeout_sec: float = 30.0

    @classmethod
    def from_env(cls) -> RegistryClientConfig:
        return cls(
            base_url=os.getenv("WAVEOS_REGISTRY_URL", "https://localhost:9200"),
            auth_token=os.getenv("WAVEOS_REGISTRY_TOKEN", ""),
            tls_cert=os.getenv("WAVEOS_REGISTRY_CLIENT_CERT", ""),
            tls_key=os.getenv("WAVEOS_REGISTRY_CLIENT_KEY", ""),
            tls_ca=os.getenv("WAVEOS_REGISTRY_CA", ""),
            verify_ssl=os.getenv("WAVEOS_REGISTRY_VERIFY_SSL", "true").lower() in ("1", "true"),
            timeout_sec=float(os.getenv("WAVEOS_REGISTRY_TIMEOUT", "30")),
        )


class RegistryClient:
    """HTTP client for WaveOS registry with mTLS and resumable downloads."""

    def __init__(self, config: Optional[RegistryClientConfig] = None) -> None:
        self.config = config or RegistryClientConfig.from_env()
        self._ssl_ctx = self._build_ssl_context()

    def _build_ssl_context(self) -> Optional[ssl.SSLContext]:
        if not self.config.base_url.startswith("https"):
            return None
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        if self.config.tls_cert and self.config.tls_key:
            ctx.load_cert_chain(self.config.tls_cert, self.config.tls_key)
        if self.config.tls_ca:
            ctx.load_verify_locations(self.config.tls_ca)
        elif not self.config.verify_ssl:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        return ctx

    def _request(self, method: str, path: str, body: Optional[bytes] = None, headers: Optional[Dict[str, str]] = None) -> tuple[int, bytes, Dict[str, str]]:
        url = f"{self.config.base_url.rstrip('/')}{path}"
        req = urllib.request.Request(url, data=body, method=method)
        req.add_header("Content-Type", "application/json")
        if self.config.auth_token:
            req.add_header("Authorization", f"Bearer {self.config.auth_token}")
        if headers:
            for k, v in headers.items():
                req.add_header(k, v)
        try:
            resp = urllib.request.urlopen(req, timeout=self.config.timeout_sec, context=self._ssl_ctx)
            resp_headers = {k.lower(): v for k, v in resp.getheaders()}
            return resp.status, resp.read(), resp_headers
        except urllib.error.HTTPError as e:
            return e.code, e.read(), {}
        except (urllib.error.URLError, OSError) as e:
            logger.warning("Registry request failed: %s", e)
            return 0, str(e).encode(), {}

    def list_bundles(self, channel: Optional[str] = None) -> List[Dict[str, Any]]:
        path = "/v1/bundles"
        if channel:
            path += f"?channel={channel}"
        code, body, _ = self._request("GET", path)
        if code == 200:
            return json.loads(body)
        return []

    def get_entry(self, bundle_id: str) -> Optional[Dict[str, Any]]:
        code, body, _ = self._request("GET", f"/v1/bundles/{bundle_id}")
        if code == 200:
            return json.loads(body)
        return None

    def download_bundle(self, bundle_id: str, dest_dir: Path, file_name: str = "bundle.json") -> Optional[Path]:
        """Download a bundle file with resumable support and integrity verification."""
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / file_name
        downloaded = 0
        if dest_path.exists():
            downloaded = dest_path.stat().st_size

        for attempt in range(self.config.max_retries):
            headers: Dict[str, str] = {}
            if downloaded > 0:
                headers["Range"] = f"bytes={downloaded}-"
                logger.info("Resuming download from byte %d (attempt %d)", downloaded, attempt + 1)

            code, data, resp_headers = self._request(
                "GET",
                f"/v1/bundles/{bundle_id}/download?file={file_name}",
                headers=headers,
            )

            if code == 206:
                with dest_path.open("ab") as f:
                    f.write(data)
                downloaded += len(data)
                content_range = resp_headers.get("content-range", "")
                if content_range:
                    total_str = content_range.split("/")[-1]
                    if total_str.isdigit() and downloaded >= int(total_str):
                        break
            elif code == 200:
                dest_path.write_bytes(data)
                break
            else:
                if attempt < self.config.max_retries - 1:
                    logger.warning("Download failed (code=%d), retrying...", code)
                    continue
                return None

        expected_sha = resp_headers.get("x-content-sha256", "")
        if expected_sha:
            actual_sha = hashlib.sha256(dest_path.read_bytes()).hexdigest()
            if actual_sha != expected_sha:
                logger.error("Integrity check failed: expected %s, got %s", expected_sha[:16], actual_sha[:16])
                dest_path.unlink(missing_ok=True)
                return None
            logger.info("Integrity verified: %s", actual_sha[:16])

        return dest_path

    def publish(self, bundle_dir: str, channel: str = "dev") -> Optional[Dict[str, Any]]:
        body = json.dumps({"bundle_dir": bundle_dir}).encode()
        code, resp, _ = self._request("POST", f"/v1/bundles?channel={channel}", body=body)
        if code in (200, 201):
            return json.loads(resp)
        logger.warning("Publish failed: code=%d body=%s", code, resp[:200])
        return None

    def promote(self, bundle_id: str, target_channel: str) -> Optional[Dict[str, Any]]:
        body = json.dumps({"bundle_id": bundle_id, "target_channel": target_channel}).encode()
        code, resp, _ = self._request("POST", "/v1/promote", body=body)
        if code == 200:
            return json.loads(resp)
        return None

    def health(self) -> bool:
        code, _, _ = self._request("GET", "/v1/health")
        return code == 200
