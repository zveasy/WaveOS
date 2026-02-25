"""WaveOS Registry Client — mTLS, resumable downloads, chunk verification."""

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
    token: str = ""
    tls_cert: str = ""
    tls_key: str = ""
    tls_ca: str = ""
    verify_ssl: bool = True
    timeout: int = 30
    chunk_size: int = 64 * 1024
    max_retries: int = 3

    @classmethod
    def from_env(cls) -> RegistryClientConfig:
        return cls(
            base_url=os.getenv("WAVEOS_REGISTRY_URL", "https://localhost:9200"),
            token=os.getenv("WAVEOS_REGISTRY_TOKEN", ""),
            tls_cert=os.getenv("WAVEOS_REGISTRY_CLIENT_CERT", ""),
            tls_key=os.getenv("WAVEOS_REGISTRY_CLIENT_KEY", ""),
            tls_ca=os.getenv("WAVEOS_REGISTRY_CA", ""),
            verify_ssl=os.getenv("WAVEOS_REGISTRY_VERIFY_SSL", "true").lower() != "false",
            timeout=int(os.getenv("WAVEOS_REGISTRY_TIMEOUT", "30")),
        )


class RegistryClient:
    """HTTP client for WaveOS registry with mTLS and resumable downloads."""

    def __init__(self, config: Optional[RegistryClientConfig] = None) -> None:
        self.config = config or RegistryClientConfig.from_env()
        self._ssl_ctx = self._build_ssl_context()

    def _build_ssl_context(self) -> Optional[ssl.SSLContext]:
        if self.config.base_url.startswith("http://"):
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

    def _headers(self) -> Dict[str, str]:
        h: Dict[str, str] = {"User-Agent": "waveos-registry-client/1.0"}
        if self.config.token:
            h["Authorization"] = f"Bearer {self.config.token}"
        return h

    def _request(self, method: str, path: str, data: Optional[bytes] = None) -> Dict[str, Any]:
        url = f"{self.config.base_url.rstrip('/')}{path}"
        headers = self._headers()
        if data:
            headers["Content-Type"] = "application/json"
            headers["Content-Length"] = str(len(data))
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            ctx = self._ssl_ctx
            with urllib.request.urlopen(req, timeout=self.config.timeout, context=ctx) as resp:
                body = resp.read()
                return json.loads(body) if body else {}
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            try:
                return json.loads(body)
            except json.JSONDecodeError:
                return {"error": body, "status": e.code}
        except (urllib.error.URLError, OSError) as e:
            return {"error": str(e), "status": 0}

    def health(self) -> Dict[str, Any]:
        return self._request("GET", "/v1/health")

    def list_bundles(self, channel: Optional[str] = None) -> List[Dict[str, Any]]:
        path = "/v1/bundles"
        if channel:
            path += f"?channel={channel}"
        result = self._request("GET", path)
        if isinstance(result, list):
            return result
        return []

    def get_bundle_meta(self, bundle_id: str) -> Dict[str, Any]:
        return self._request("GET", f"/v1/bundles/{bundle_id}")

    def download_file(
        self,
        bundle_id: str,
        filename: str,
        dest_path: Path,
        expected_sha256: str = "",
    ) -> Dict[str, Any]:
        """Download a file with resumable range requests and integrity verification."""
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        url = f"{self.config.base_url.rstrip('/')}/v1/bundles/{bundle_id}/download/{filename}"
        existing_size = 0
        if dest_path.exists():
            existing_size = dest_path.stat().st_size
        headers = self._headers()
        if existing_size > 0:
            headers["Range"] = f"bytes={existing_size}-"
        req = urllib.request.Request(url, headers=headers)
        retries = 0
        while retries <= self.config.max_retries:
            try:
                ctx = self._ssl_ctx
                with urllib.request.urlopen(req, timeout=self.config.timeout, context=ctx) as resp:
                    server_sha = resp.headers.get("X-Content-SHA256", "")
                    mode = "ab" if existing_size > 0 and resp.status == 206 else "wb"
                    sha256 = hashlib.sha256()
                    total = 0
                    with dest_path.open(mode) as f:
                        while True:
                            chunk = resp.read(self.config.chunk_size)
                            if not chunk:
                                break
                            f.write(chunk)
                            sha256.update(chunk)
                            total += len(chunk)
                    if mode == "wb":
                        actual_sha = sha256.hexdigest()
                    else:
                        full_sha = hashlib.sha256()
                        with dest_path.open("rb") as f:
                            while True:
                                c = f.read(8192)
                                if not c:
                                    break
                                full_sha.update(c)
                        actual_sha = full_sha.hexdigest()
                    if expected_sha256 and actual_sha != expected_sha256:
                        return {"ok": False, "error": f"SHA256 mismatch: expected {expected_sha256[:16]}..., got {actual_sha[:16]}...", "bytes": total}
                    if server_sha and actual_sha != server_sha:
                        return {"ok": False, "error": f"Server SHA256 mismatch", "bytes": total}
                    return {"ok": True, "bytes": total, "sha256": actual_sha, "path": str(dest_path)}
            except (urllib.error.URLError, OSError) as e:
                retries += 1
                if retries > self.config.max_retries:
                    return {"ok": False, "error": str(e), "retries": retries}
                logger.warning("Download retry %d/%d: %s", retries, self.config.max_retries, e)
                import time
                time.sleep(min(2 ** retries, 30))
        return {"ok": False, "error": "Max retries exceeded"}

    def download_bundle(self, bundle_id: str, dest_dir: Path) -> Dict[str, Any]:
        """Download complete bundle with all artifacts."""
        meta = self.get_bundle_meta(bundle_id)
        if "error" in meta:
            return {"ok": False, "error": meta.get("error")}
        dest_dir.mkdir(parents=True, exist_ok=True)
        manifest_result = self.download_file(bundle_id, "bundle.json", dest_dir / "bundle.json")
        if not manifest_result.get("ok"):
            return manifest_result
        manifest_path = dest_dir / "bundle.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        artifacts = manifest.get("artifacts", [])
        results = [manifest_result]
        for artifact in artifacts:
            art_path = artifact.get("path", "")
            art_sha = artifact.get("sha256", "")
            if art_path and art_path != "bundle.json":
                r = self.download_file(bundle_id, art_path, dest_dir / art_path, expected_sha256=art_sha)
                results.append(r)
                if not r.get("ok"):
                    return {"ok": False, "error": f"Failed to download {art_path}", "results": results}
        sig_result = self.download_file(bundle_id, "bundle.sig", dest_dir / "bundle.sig")
        results.append(sig_result)
        total_bytes = sum(r.get("bytes", 0) for r in results)
        return {"ok": True, "bundle_id": bundle_id, "artifacts": len(results), "total_bytes": total_bytes}

    def publish_channel(self, bundle_id: str, channel: str) -> Dict[str, Any]:
        data = json.dumps({"bundle_id": bundle_id, "channel": channel}).encode("utf-8")
        return self._request("POST", "/v1/bundles", data=data)
