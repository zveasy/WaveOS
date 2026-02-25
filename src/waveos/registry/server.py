"""WaveOS Registry Server — secure HTTP distribution with mTLS, auth, rate limiting, resumable downloads."""

from __future__ import annotations

import hashlib
import json
import os
import ssl
import threading
import time
from dataclasses import dataclass, field
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.registry.server")


@dataclass
class DeviceIdentityRecord:
    device_id: str
    clearance: str = "operator"
    channels: List[str] = field(default_factory=lambda: ["dev"])
    site_id: str = ""
    cert_fingerprint: str = ""
    revoked: bool = False

    def to_dict(self) -> dict:
        return {"device_id": self.device_id, "clearance": self.clearance, "channels": self.channels, "site_id": self.site_id, "cert_fingerprint": self.cert_fingerprint, "revoked": self.revoked}

    @classmethod
    def from_dict(cls, d: dict) -> DeviceIdentityRecord:
        return cls(**{k: d[k] for k in d if k in cls.__dataclass_fields__})


@dataclass
class RateLimitEntry:
    key: str
    requests: int = 0
    window_start: float = 0.0
    max_requests: int = 100
    window_seconds: float = 60.0

    def check(self) -> bool:
        now = time.time()
        if now - self.window_start > self.window_seconds:
            self.requests = 0
            self.window_start = now
        self.requests += 1
        return self.requests <= self.max_requests


class DeviceAuthStore:
    """Manages device identity, channel authorization, and cert fingerprints."""

    def __init__(self, store_path: Optional[Path] = None) -> None:
        self._devices: Dict[str, DeviceIdentityRecord] = {}
        self._store_path = store_path
        if store_path and store_path.exists():
            self._load()

    def _load(self) -> None:
        try:
            data = json.loads(self._store_path.read_text(encoding="utf-8"))
            for d in data:
                rec = DeviceIdentityRecord.from_dict(d)
                self._devices[rec.device_id] = rec
        except (json.JSONDecodeError, OSError):
            pass

    def save(self) -> None:
        if self._store_path:
            self._store_path.parent.mkdir(parents=True, exist_ok=True)
            self._store_path.write_text(json.dumps([d.to_dict() for d in self._devices.values()], indent=2) + "\n", encoding="utf-8")

    def register(self, record: DeviceIdentityRecord) -> None:
        self._devices[record.device_id] = record
        self.save()

    def get(self, device_id: str) -> Optional[DeviceIdentityRecord]:
        return self._devices.get(device_id)

    def authenticate(self, device_id: str, cert_fingerprint: str = "") -> Optional[DeviceIdentityRecord]:
        rec = self._devices.get(device_id)
        if not rec:
            return None
        if rec.revoked:
            return None
        if cert_fingerprint and rec.cert_fingerprint and rec.cert_fingerprint != cert_fingerprint:
            return None
        return rec

    def authorize_channel(self, device_id: str, channel: str) -> bool:
        rec = self._devices.get(device_id)
        if not rec or rec.revoked:
            return False
        return channel in rec.channels or "*" in rec.channels

    def revoke(self, device_id: str) -> bool:
        rec = self._devices.get(device_id)
        if not rec:
            return False
        rec.revoked = True
        self.save()
        return True

    def rotate_cert(self, device_id: str, new_fingerprint: str) -> bool:
        rec = self._devices.get(device_id)
        if not rec:
            return False
        rec.cert_fingerprint = new_fingerprint
        self.save()
        return True

    def list_devices(self) -> List[DeviceIdentityRecord]:
        return list(self._devices.values())


class RateLimiter:
    """Per-key rate limiter (per device/site)."""

    def __init__(self, max_requests: int = 100, window_seconds: float = 60.0) -> None:
        self._entries: Dict[str, RateLimitEntry] = {}
        self._max = max_requests
        self._window = window_seconds
        self._lock = threading.Lock()

    def check(self, key: str) -> bool:
        with self._lock:
            if key not in self._entries:
                self._entries[key] = RateLimitEntry(key=key, window_start=time.time(), max_requests=self._max, window_seconds=self._window)
            return self._entries[key].check()


class RegistryRequestHandler(BaseHTTPRequestHandler):
    """HTTP handler for registry API with resumable downloads."""

    def log_message(self, format, *args):
        logger.debug(format, *args)

    def _auth_device(self) -> Optional[DeviceIdentityRecord]:
        device_id = self.headers.get("X-Device-ID", "")
        token = self.headers.get("Authorization", "").replace("Bearer ", "")
        if not device_id and token:
            device_id = token
        if not device_id:
            return None
        cert_fp = ""
        if hasattr(self.connection, "getpeercert"):
            try:
                cert = self.connection.getpeercert(binary_form=True)
                if cert:
                    cert_fp = hashlib.sha256(cert).hexdigest()
            except Exception:
                pass
        auth_store = self.server.auth_store
        return auth_store.authenticate(device_id, cert_fp)

    def _check_rate_limit(self, key: str) -> bool:
        return self.server.rate_limiter.check(key)

    def _send_json(self, status: int, data: Any) -> None:
        body = json.dumps(data, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error_json(self, status: int, message: str) -> None:
        self._send_json(status, {"error": message})

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        params = parse_qs(parsed.query)

        if path == "/v1/bundles":
            device = self._auth_device()
            if not device:
                self._send_error_json(401, "Authentication required")
                return
            if not self._check_rate_limit(device.device_id):
                self._send_error_json(429, "Rate limit exceeded")
                return
            channel = params.get("channel", [None])[0]
            if channel and not self.server.auth_store.authorize_channel(device.device_id, channel):
                self._send_error_json(403, f"Not authorized for channel: {channel}")
                return
            from waveos.registry.store import RegistryStore
            store = RegistryStore(self.server.registry_root)
            entries = store.list_bundles(channel=channel)
            self._send_json(200, [e.to_dict() for e in entries])

        elif path.startswith("/v1/bundles/") and "/download" in path:
            device = self._auth_device()
            if not device:
                self._send_error_json(401, "Authentication required")
                return
            if not self._check_rate_limit(device.device_id):
                self._send_error_json(429, "Rate limit exceeded")
                return
            parts = path.split("/")
            bundle_id = parts[3] if len(parts) > 3 else ""
            file_path_str = "/".join(parts[5:]) if len(parts) > 5 else ""
            from waveos.registry.store import RegistryStore
            store = RegistryStore(self.server.registry_root)
            bundle_path = store.get_bundle(bundle_id)
            if not bundle_path:
                self._send_error_json(404, "Bundle not found")
                return
            target = bundle_path / file_path_str if file_path_str else bundle_path / "bundle.json"
            if not target.is_file():
                self._send_error_json(404, "File not found")
                return
            file_size = target.stat().st_size
            range_header = self.headers.get("Range", "")
            start = 0
            end = file_size - 1
            if range_header.startswith("bytes="):
                try:
                    r = range_header[6:].split("-")
                    start = int(r[0]) if r[0] else 0
                    end = int(r[1]) if r[1] else file_size - 1
                except (ValueError, IndexError):
                    pass
            length = end - start + 1
            with target.open("rb") as f:
                f.seek(start)
                data = f.read(length)
            chunk_hash = hashlib.sha256(data).hexdigest()
            if range_header:
                self.send_response(206)
                self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
            else:
                self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(length))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("X-Content-SHA256", chunk_hash)
            self.send_header("X-Full-Size", str(file_size))
            self.end_headers()
            self.wfile.write(data)

        elif path.startswith("/v1/bundles/"):
            bundle_id = path.split("/")[3] if len(path.split("/")) > 3 else ""
            from waveos.registry.store import RegistryStore
            store = RegistryStore(self.server.registry_root)
            entry = store.get_entry(bundle_id)
            if entry:
                self._send_json(200, entry.to_dict())
            else:
                self._send_error_json(404, "Bundle not found")

        elif path == "/v1/devices":
            self._send_json(200, [d.to_dict() for d in self.server.auth_store.list_devices()])

        elif path == "/health":
            self._send_json(200, {"status": "ok", "timestamp": utc_now().isoformat()})

        else:
            self._send_error_json(404, "Not found")

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length else b""

        if path == "/v1/devices/register":
            try:
                data = json.loads(body)
                rec = DeviceIdentityRecord.from_dict(data)
                self.server.auth_store.register(rec)
                self._send_json(201, rec.to_dict())
            except (json.JSONDecodeError, KeyError) as exc:
                self._send_error_json(400, str(exc))

        elif path.startswith("/v1/devices/") and path.endswith("/revoke"):
            device_id = path.split("/")[3]
            if self.server.auth_store.revoke(device_id):
                self._send_json(200, {"revoked": device_id})
            else:
                self._send_error_json(404, "Device not found")

        elif path.startswith("/v1/devices/") and path.endswith("/rotate-cert"):
            device_id = path.split("/")[3]
            try:
                data = json.loads(body)
                fp = data.get("cert_fingerprint", "")
                if self.server.auth_store.rotate_cert(device_id, fp):
                    self._send_json(200, {"rotated": device_id})
                else:
                    self._send_error_json(404, "Device not found")
            except json.JSONDecodeError:
                self._send_error_json(400, "Invalid JSON")

        elif path == "/v1/publish":
            device = self._auth_device()
            if not device:
                self._send_error_json(401, "Authentication required")
                return
            try:
                data = json.loads(body)
                channel = data.get("channel", "dev")
                if channel in ("prod", "mission-critical"):
                    if device.clearance not in ("admin", "ci"):
                        self._send_error_json(403, "Only CI/admin can publish to prod channels")
                        return
                self._send_json(200, {"accepted": True, "channel": channel, "publisher": device.device_id})
            except json.JSONDecodeError:
                self._send_error_json(400, "Invalid JSON")

        else:
            self._send_error_json(404, "Not found")


class RegistryServer(HTTPServer):
    """Extended HTTPServer with registry context."""

    def __init__(self, addr, handler, registry_root: Path, auth_store: DeviceAuthStore, rate_limiter: Optional[RateLimiter] = None):
        super().__init__(addr, handler)
        self.registry_root = registry_root
        self.auth_store = auth_store
        self.rate_limiter = rate_limiter or RateLimiter()


def create_ssl_context(cert_path: str, key_path: str, ca_path: str = "", require_client_cert: bool = True) -> ssl.SSLContext:
    """Create mTLS SSL context."""
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


def run_registry_server(
    host: str = "0.0.0.0",
    port: int = 9200,
    registry_root: Path = Path("out/registry"),
    auth_store_path: Optional[Path] = None,
    tls_cert: str = "",
    tls_key: str = "",
    tls_ca: str = "",
    max_requests_per_min: int = 100,
) -> None:
    """Start the registry HTTP server."""
    auth_store = DeviceAuthStore(auth_store_path)
    limiter = RateLimiter(max_requests=max_requests_per_min, window_seconds=60.0)
    server = RegistryServer((host, port), RegistryRequestHandler, registry_root, auth_store, limiter)
    if tls_cert and tls_key:
        ctx = create_ssl_context(tls_cert, tls_key, tls_ca, require_client_cert=bool(tls_ca))
        server.socket = ctx.wrap_socket(server.socket, server_side=True)
        logger.info("Registry server starting with mTLS on %s:%d", host, port)
    else:
        logger.info("Registry server starting (no TLS) on %s:%d", host, port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
