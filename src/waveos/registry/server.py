"""Registry HTTP server — mTLS, auth, rate limiting, resumable downloads."""

from __future__ import annotations

import hashlib
import json
import os
import ssl
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlparse

from waveos.registry.auth import RegistryAuthenticator, DeviceIdentity
from waveos.registry.store import RegistryStore
from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.registry.server")


class RegistryHandler(BaseHTTPRequestHandler):
    """HTTP handler for registry operations with auth + range requests."""

    server: RegistryHTTPServer

    def log_message(self, format, *args) -> None:
        logger.debug("Registry HTTP: %s", format % args)

    def _get_device(self) -> Optional[DeviceIdentity]:
        auth_header = self.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
            return self.server.authenticator.authenticate_token(token)
        cert = getattr(self.connection, "getpeercert", lambda: None)()
        if cert:
            fp = hashlib.sha256(str(cert).encode()).hexdigest()
            return self.server.authenticator.authenticate_cert(fp)
        return DeviceIdentity(device_id="anonymous", clearance="dev")

    def _send_json(self, status: int, data: Any) -> None:
        body = json.dumps(data, indent=2, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error_json(self, status: int, message: str) -> None:
        self._send_json(status, {"error": message})

    def do_GET(self) -> None:
        device = self._get_device()
        if not device:
            self._send_error_json(401, "Authentication required")
            return
        if not self.server.authenticator.check_rate_limit(device.device_id):
            self._send_error_json(429, "Rate limit exceeded")
            return
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        if path == "/v1/bundles":
            self._handle_list(device, parsed)
        elif path.startswith("/v1/bundles/") and path.count("/") == 3:
            bundle_id = path.split("/")[3]
            self._handle_get_entry(device, bundle_id)
        elif path.startswith("/v1/download/"):
            parts = path.split("/")
            if len(parts) >= 4:
                bundle_id = parts[3]
                file_path = "/".join(parts[4:]) if len(parts) > 4 else ""
                self._handle_download(device, bundle_id, file_path)
            else:
                self._send_error_json(400, "Invalid download path")
        elif path == "/v1/health":
            self._send_json(200, {"status": "ok", "timestamp": utc_now().isoformat()})
        else:
            self._send_error_json(404, "Not found")

    def _handle_list(self, device: DeviceIdentity, parsed) -> None:
        qs = parse_qs(parsed.query)
        channel = qs.get("channel", [None])[0]
        entries = self.server.store.list_bundles(channel=channel)
        accessible = []
        for entry in entries:
            ok, _ = self.server.authenticator.authorize_download(device, entry.channel)
            if ok:
                accessible.append(entry.to_dict())
        self._send_json(200, accessible)

    def _handle_get_entry(self, device: DeviceIdentity, bundle_id: str) -> None:
        entry = self.server.store.get_entry(bundle_id)
        if not entry:
            self._send_error_json(404, f"Bundle {bundle_id} not found")
            return
        ok, reason = self.server.authenticator.authorize_download(device, entry.channel)
        if not ok:
            self._send_error_json(403, reason)
            return
        self._send_json(200, entry.to_dict())

    def _handle_download(self, device: DeviceIdentity, bundle_id: str, file_path: str) -> None:
        entry = self.server.store.get_entry(bundle_id)
        if not entry:
            self._send_error_json(404, f"Bundle {bundle_id} not found")
            return
        ok, reason = self.server.authenticator.authorize_download(device, entry.channel)
        if not ok:
            self._send_error_json(403, reason)
            return
        bundle_dir = self.server.store.get_bundle(bundle_id)
        if not bundle_dir:
            self._send_error_json(404, "Bundle files not found")
            return
        if file_path:
            target = bundle_dir / file_path
        else:
            target = bundle_dir / "bundle.json"
        if not target.is_file():
            self._send_error_json(404, f"File not found: {file_path or 'bundle.json'}")
            return
        try:
            target.resolve().relative_to(bundle_dir.resolve())
        except ValueError:
            self._send_error_json(403, "Path traversal denied")
            return
        file_size = target.stat().st_size
        file_hash = hashlib.sha256(target.read_bytes()).hexdigest()
        range_header = self.headers.get("Range", "")
        start = 0
        end = file_size - 1
        if range_header.startswith("bytes="):
            try:
                range_spec = range_header[6:]
                if range_spec.endswith("-"):
                    start = int(range_spec[:-1])
                elif "-" in range_spec:
                    parts = range_spec.split("-")
                    start = int(parts[0])
                    end = int(parts[1])
            except (ValueError, IndexError):
                pass
        start = max(0, min(start, file_size - 1))
        end = min(end, file_size - 1)
        length = end - start + 1
        if range_header:
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
        else:
            self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(length))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("X-Content-SHA256", file_hash)
        self.send_header("ETag", f'"{file_hash[:16]}"')
        self.end_headers()
        with target.open("rb") as f:
            f.seek(start)
            remaining = length
            while remaining > 0:
                chunk_size = min(8192, remaining)
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)

    def do_POST(self) -> None:
        device = self._get_device()
        if not device:
            self._send_error_json(401, "Authentication required")
            return
        if not self.server.authenticator.check_rate_limit(device.device_id):
            self._send_error_json(429, "Rate limit exceeded")
            return
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        if path == "/v1/publish":
            self._handle_publish_metadata(device)
        else:
            self._send_error_json(404, "Not found")

    def _handle_publish_metadata(self, device: DeviceIdentity) -> None:
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self._send_error_json(400, "Invalid JSON")
            return
        channel = data.get("channel", "dev")
        ok, reason = self.server.authenticator.authorize_publish(device, channel)
        if not ok:
            self._send_error_json(403, reason)
            return
        self._send_json(200, {"status": "accepted", "channel": channel, "publisher": device.device_id,
                               "timestamp": utc_now().isoformat()})


class RegistryHTTPServer(HTTPServer):
    def __init__(self, addr, store: RegistryStore, authenticator: RegistryAuthenticator,
                 ssl_context: Optional[ssl.SSLContext] = None, **kwargs) -> None:
        self.store = store
        self.authenticator = authenticator
        self.ssl_context = ssl_context
        super().__init__(addr, RegistryHandler, **kwargs)
        if ssl_context:
            self.socket = ssl_context.wrap_socket(self.socket, server_side=True)


def create_ssl_context(cert_path: str, key_path: str, ca_path: Optional[str] = None,
                       require_client_cert: bool = False) -> ssl.SSLContext:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(cert_path, key_path)
    if ca_path:
        ctx.load_verify_locations(ca_path)
    if require_client_cert:
        ctx.verify_mode = ssl.CERT_REQUIRED
    else:
        ctx.verify_mode = ssl.CERT_OPTIONAL
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    return ctx


def run_registry_server(host: str = "0.0.0.0", port: int = 9200, registry_root: str = "out/registry",
                        cert_path: Optional[str] = None, key_path: Optional[str] = None,
                        ca_path: Optional[str] = None, require_client_cert: bool = False,
                        device_store: Optional[str] = None) -> None:
    store = RegistryStore(Path(registry_root))
    dev_store_path = Path(device_store) if device_store else None
    authenticator = RegistryAuthenticator(device_store_path=dev_store_path)
    ssl_ctx = None
    if cert_path and key_path:
        ssl_ctx = create_ssl_context(cert_path, key_path, ca_path, require_client_cert)
        logger.info("Registry server with mTLS on %s:%d", host, port)
    else:
        logger.info("Registry server (no TLS) on %s:%d", host, port)
    server = RegistryHTTPServer((host, port), store, authenticator, ssl_context=ssl_ctx)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Registry server stopped")
    finally:
        server.server_close()
