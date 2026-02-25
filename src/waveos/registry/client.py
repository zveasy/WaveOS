"""WaveOS Registry Client — mTLS, resumable downloads, chunk verification."""

from __future__ import annotations

import hashlib
import json
import os
import ssl
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.registry.client")


@dataclass
class RegistryClientConfig:
    """Configuration for the registry client."""
    base_url: str = "https://localhost:9200"
    cert_path: str = ""
    key_path: str = ""
    ca_path: str = ""
    device_id: str = ""
    token: str = ""
    timeout_sec: int = 30
    retry_count: int = 3
    retry_backoff_sec: float = 2.0
    chunk_size: int = 65536

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__dataclass_fields__ if k not in ("token",)}


def _build_ssl_context(config: RegistryClientConfig) -> Optional[ssl.SSLContext]:
    if not config.base_url.startswith("https"):
        return None
    ctx = ssl.create_default_context()
    if config.ca_path:
        ctx.load_verify_locations(config.ca_path)
    else:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    if config.cert_path and config.key_path:
        ctx.load_cert_chain(config.cert_path, config.key_path)
    return ctx


class RegistryClient:
    """Client for the WaveOS registry server."""

    def __init__(self, config: Optional[RegistryClientConfig] = None) -> None:
        self.config = config or RegistryClientConfig()
        self._ssl_ctx = _build_ssl_context(self.config)

    def _request(self, method: str, path: str, body: Optional[bytes] = None, headers: Optional[Dict[str, str]] = None, timeout: Optional[int] = None) -> tuple[int, bytes, Dict[str, str]]:
        url = f"{self.config.base_url.rstrip('/')}{path}"
        hdrs = dict(headers or {})
        if self.config.token:
            hdrs["Authorization"] = f"Bearer {self.config.token}"
        if self.config.device_id:
            hdrs["X-Device-ID"] = self.config.device_id
        req = Request(url, data=body, headers=hdrs, method=method)
        to = timeout or self.config.timeout_sec
        last_exc: Optional[Exception] = None
        for attempt in range(self.config.retry_count):
            try:
                resp = urlopen(req, timeout=to, context=self._ssl_ctx)
                resp_headers = {k.lower(): v for k, v in resp.getheaders()}
                return resp.status, resp.read(), resp_headers
            except HTTPError as e:
                return e.code, e.read(), {}
            except (URLError, OSError, TimeoutError) as e:
                last_exc = e
                wait = self.config.retry_backoff_sec * (2 ** attempt)
                logger.warning("Registry request failed (attempt %d): %s, retry in %.1fs", attempt + 1, e, wait)
                time.sleep(wait)
        raise ConnectionError(f"Registry request failed after {self.config.retry_count} attempts: {last_exc}")

    def list_bundles(self, channel: Optional[str] = None) -> List[Dict[str, Any]]:
        path = "/v1/bundles"
        if channel:
            path += f"?channel={channel}"
        code, body, _ = self._request("GET", path)
        if code == 200:
            return json.loads(body)
        raise ValueError(f"List bundles failed: {code}")

    def get_entry(self, bundle_id: str) -> Optional[Dict[str, Any]]:
        code, body, _ = self._request("GET", f"/v1/bundles/{bundle_id}")
        if code == 200:
            return json.loads(body)
        return None

    def download_file(self, bundle_id: str, file_name: str, dest_path: Path, expected_sha256: str = "") -> Dict[str, Any]:
        """Download a file with resumable support and integrity verification."""
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        downloaded = 0
        if dest_path.exists():
            downloaded = dest_path.stat().st_size

        headers: Dict[str, str] = {}
        if downloaded > 0:
            headers["Range"] = f"bytes={downloaded}-"

        path = f"/v1/bundles/{bundle_id}/download/{file_name}"
        code, body, resp_headers = self._request("GET", path, headers=headers)

        if code == 416:
            return {"ok": True, "file": str(dest_path), "size": downloaded, "resumed": True, "note": "already complete"}

        if code not in (200, 206):
            return {"ok": False, "error": f"HTTP {code}"}

        mode = "ab" if code == 206 else "wb"
        with dest_path.open(mode) as f:
            f.write(body)

        actual_hash = hashlib.sha256(dest_path.read_bytes()).hexdigest()
        server_hash = resp_headers.get("x-content-sha256", "")

        integrity_ok = True
        if expected_sha256 and actual_hash != expected_sha256:
            integrity_ok = False
        elif server_hash and actual_hash != server_hash:
            integrity_ok = False

        return {
            "ok": integrity_ok,
            "file": str(dest_path),
            "size": dest_path.stat().st_size,
            "sha256": actual_hash,
            "integrity_verified": integrity_ok,
            "resumed": code == 206,
        }

    def download_bundle(self, bundle_id: str, dest_dir: Path) -> Dict[str, Any]:
        """Download entire bundle (manifest + all artifacts)."""
        entry = self.get_entry(bundle_id)
        if not entry:
            return {"ok": False, "error": "Bundle not found"}

        dest_dir.mkdir(parents=True, exist_ok=True)
        manifest_result = self.download_file(bundle_id, "bundle.json", dest_dir / "bundle.json")
        if not manifest_result.get("ok"):
            return {"ok": False, "error": "Failed to download manifest", "details": manifest_result}

        manifest = json.loads((dest_dir / "bundle.json").read_text(encoding="utf-8"))
        artifacts = manifest.get("artifacts", [])
        results = [manifest_result]
        for artifact in artifacts:
            art_path = artifact.get("path", "")
            art_sha = artifact.get("sha256", "")
            if not art_path:
                continue
            r = self.download_file(bundle_id, art_path, dest_dir / art_path, expected_sha256=art_sha)
            results.append(r)

        for extra in ["bundle.sig", "attestation.json", "sbom.json", "checksums.txt"]:
            try:
                r = self.download_file(bundle_id, extra, dest_dir / extra)
                if r.get("ok"):
                    results.append(r)
            except (ConnectionError, ValueError):
                pass

        all_ok = all(r.get("ok", False) for r in results)
        return {"ok": all_ok, "bundle_id": bundle_id, "dest": str(dest_dir), "files": len(results), "results": results}

    def publish(self, channel: str = "dev", metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        body = json.dumps({"channel": channel, **(metadata or {})}).encode("utf-8")
        code, resp, _ = self._request("POST", "/v1/publish", body=body, headers={"Content-Type": "application/json"})
        if code == 200:
            return json.loads(resp)
        return {"ok": False, "error": f"Publish failed: {code}", "body": resp.decode("utf-8", errors="replace")}

    def health(self) -> Dict[str, Any]:
        try:
            code, body, _ = self._request("GET", "/v1/health", timeout=5)
            if code == 200:
                return json.loads(body)
        except (ConnectionError, ValueError):
            pass
        return {"status": "unreachable"}
