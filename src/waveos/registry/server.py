"""WaveOS Registry Server — HTTP API with mTLS, auth, rate limiting, resumable downloads."""

from __future__ import annotations

import hashlib
import json
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse, parse_qs

from waveos.registry.auth import (
    CredentialStore, RateLimiter, build_ssl_context,
)
from waveos.registry.store import RegistryStore
from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.registry.server")


class RegistryHandler(BaseHTTPRequestHandler):
    """HTTP handler for the registry API."""

    store: RegistryStore
    cred_store: CredentialStore
    limiter: RateLimiter
    publish_requires_ci: bool = True

    def log_message(self, format, *args):
        logger.debug(format, *args)

    def _authenticate(self) -> Optional[str]:
        auth = self.headers.get("Authorization", "")
        device_id = self.headers.get("X-Device-ID", "")
        if auth.startswith("Bearer ") and device_id:
            token = auth[7:]
            cred = self.cred_store.authenticate_token(device_id, token)
            if cred:
                return device_id
        if hasattr(self.connection, "getpeercert"):
            try:
                cert = self.connection.getpeercert()
                if cert:
                    import ssl
                    fp = hashlib.sha256(ssl.DER_cert_to_PEM_cert(
                        self.connection.getpeercert(binary_form=True) or b""
                    ).encode()).hexdigest()
                    cred = self.cred_store.authenticate_cert(fp)
                    if cred:
                        return cred.device_id
            except Exception:
                pass
        if not device_id and not auth:
            return "__anonymous__"
        return None

    def _check_rate(self, device_id: str) -> bool:
        return self.limiter.allow(device_id)

    def _send_json(self, code: int, data: Any) -> None:
        body = json.dumps(data, indent=2, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, code: int, msg: str) -> None:
        self._send_json(code, {"error": msg})

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        device_id = self._authenticate()
        if device_id is None:
            self._send_error(401, "Unauthorized")
            return
        if not self._check_rate(device_id):
            self._send_error(429, "Rate limit exceeded")
            return

        if path == "/v1/bundles":
            params = parse_qs(parsed.query)
            channel = params.get("channel", [None])[0]
            entries = self.store.list_bundles(channel=channel)
            self._send_json(200, [e.to_dict() for e in entries])

        elif path.startswith("/v1/bundles/") and "/download" not in path:
            bundle_id = path.split("/v1/bundles/")[1]
            entry = self.store.get_entry(bundle_id)
            if entry:
                if not self.cred_store.authorize_channel(device_id, entry.channel) and device_id != "__anonymous__":
                    self._send_error(403, f"Not authorized for channel {entry.channel}")
                    return
                self._send_json(200, entry.to_dict())
            else:
                self._send_error(404, "Bundle not found")

        elif "/download/" in path:
            parts = path.split("/download/")
            bundle_id = parts[0].split("/v1/bundles/")[1] if len(parts) > 1 else ""
            file_name = parts[1] if len(parts) > 1 else ""
            bundle_path = self.store.get_bundle(bundle_id)
            if not bundle_path:
                self._send_error(404, "Bundle not found")
                return
            file_path = bundle_path / file_name
            if not file_path.is_file():
                self._send_error(404, f"File not found: {file_name}")
                return
            try:
                file_path.relative_to(bundle_path)
            except ValueError:
                self._send_error(403, "Path traversal rejected")
                return
            file_size = file_path.stat().st_size
            range_header = self.headers.get("Range")
            start = 0
            end = file_size - 1
            if range_header and range_header.startswith("bytes="):
                try:
                    rng = range_header[6:].split("-")
                    start = int(rng[0]) if rng[0] else 0
                    end = int(rng[1]) if rng[1] else file_size - 1
                    end = min(end, file_size - 1)
                except (ValueError, IndexError):
                    pass
            length = end - start + 1
            sha256_hash = hashlib.sha256()
            with file_path.open("rb") as f:
                f.seek(start)
                data = f.read(length)
                sha256_hash.update(data)
            code = 206 if range_header else 200
            self.send_response(code)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(length))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("X-Content-SHA256", sha256_hash.hexdigest())
            if range_header:
                self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
            self.end_headers()
            self.wfile.write(data)

        elif path == "/v1/health":
            self._send_json(200, {"status": "ok", "timestamp": utc_now().isoformat()})

        else:
            self._send_error(404, "Not found")

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        device_id = self._authenticate()
        if device_id is None:
            self._send_error(401, "Unauthorized")
            return
        if not self._check_rate(device_id):
            self._send_error(429, "Rate limit exceeded")
            return

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else b""

        if path == "/v1/publish":
            if self.publish_requires_ci:
                publisher_type = self.headers.get("X-Publisher-Type", "")
                if publisher_type != "ci":
                    self._send_error(403, "Only CI/CD can publish to prod channels")
                    return
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                self._send_error(400, "Invalid JSON")
                return
            bundle_dir_str = data.get("bundle_dir", "")
            channel = data.get("channel", "dev")
            publisher = data.get("publisher", device_id)
            if not bundle_dir_str:
                self._send_error(400, "bundle_dir required")
                return
            bundle_dir = Path(bundle_dir_str)
            if not bundle_dir.is_dir():
                self._send_error(400, f"Not a directory: {bundle_dir}")
                return
            try:
                entry = self.store.publish(bundle_dir, channel=channel, publisher=publisher)
                self._send_json(201, entry.to_dict())
            except ValueError as exc:
                self._send_error(400, str(exc))

        elif path == "/v1/devices/register":
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                self._send_error(400, "Invalid JSON")
                return
            from waveos.registry.auth import DeviceCredential, hash_token
            token = data.get("token", "")
            cred = DeviceCredential(
                device_id=data.get("device_id", ""),
                site_id=data.get("site_id", ""),
                clearance=data.get("clearance", "unclassified"),
                allowed_channels=data.get("allowed_channels", ["dev"]),
                token_hash=hash_token(token) if token else "",
                cert_fingerprint=data.get("cert_fingerprint", ""),
            )
            self.cred_store.register(cred)
            self._send_json(201, {"device_id": cred.device_id, "registered": True})

        else:
            self._send_error(404, "Not found")


def run_registry_server(
    host: str = "0.0.0.0",
    port: int = 9200,
    registry_root: Path = Path("out/registry"),
    cred_store_path: Path = Path("out/registry/credentials.json"),
    cert_path: Optional[str] = None,
    key_path: Optional[str] = None,
    ca_path: Optional[str] = None,
    require_client_cert: bool = False,
    max_requests_per_min: int = 120,
    publish_requires_ci: bool = True,
) -> None:
    """Start the registry HTTP server."""
    store = RegistryStore(registry_root)
    cred_store = CredentialStore(cred_store_path)
    limiter = RateLimiter(max_requests=max_requests_per_min)

    RegistryHandler.store = store
    RegistryHandler.cred_store = cred_store
    RegistryHandler.limiter = limiter
    RegistryHandler.publish_requires_ci = publish_requires_ci

    server = HTTPServer((host, port), RegistryHandler)

    ssl_ctx = build_ssl_context(cert_path, key_path, ca_path, require_client_cert)
    if ssl_ctx:
        server.socket = ssl_ctx.wrap_socket(server.socket, server_side=True)
        logger.info("Registry server TLS enabled (client cert required: %s)", require_client_cert)

    logger.info("Registry server listening on %s:%d", host, port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Registry server stopped")
    finally:
        server.server_close()
