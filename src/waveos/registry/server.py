"""WaveOS Registry Server — HTTP distribution endpoint with mTLS, auth, rate limiting, and resumable downloads."""

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
    """Device identity for auth (CN from client cert or token)."""
    device_id: str
    clearance: str = "operator"
    allowed_channels: List[str] = field(default_factory=lambda: ["dev", "staging", "prod"])
    site_id: str = ""
    rate_limit_per_min: int = 60
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"device_id": self.device_id, "clearance": self.clearance, "allowed_channels": self.allowed_channels, "site_id": self.site_id, "rate_limit_per_min": self.rate_limit_per_min, "metadata": self.metadata}

    @classmethod
    def from_dict(cls, d: dict) -> DeviceIdentityRecord:
        return cls(**{k: d[k] for k in d if k in cls.__dataclass_fields__})


class DeviceAuthStore:
    """Manages device identity records and rate-limit counters."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self._devices: Dict[str, DeviceIdentityRecord] = {}
        self._rate_counters: Dict[str, List[float]] = {}
        if path and path.exists():
            self._load(path)

    def _load(self, path: Path) -> None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            for d in data:
                rec = DeviceIdentityRecord.from_dict(d)
                self._devices[rec.device_id] = rec
        except (json.JSONDecodeError, KeyError) as exc:
            logger.warning("Failed to load device auth store: %s", exc)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps([d.to_dict() for d in self._devices.values()], indent=2) + "\n", encoding="utf-8")

    def register(self, record: DeviceIdentityRecord) -> None:
        self._devices[record.device_id] = record

    def get(self, device_id: str) -> Optional[DeviceIdentityRecord]:
        return self._devices.get(device_id)

    def authenticate(self, device_id: str, channel: str = "") -> tuple[bool, str]:
        rec = self._devices.get(device_id)
        if not rec:
            if not self._devices:
                return True, "no auth store configured (open)"
            return False, f"unknown device: {device_id}"
        if channel and channel not in rec.allowed_channels:
            return False, f"device {device_id} not authorized for channel {channel}"
        return True, "ok"

    def check_rate_limit(self, device_id: str) -> tuple[bool, str]:
        rec = self._devices.get(device_id)
        limit = rec.rate_limit_per_min if rec else 60
        now = time.time()
        window = self._rate_counters.setdefault(device_id, [])
        window[:] = [t for t in window if now - t < 60]
        if len(window) >= limit:
            return False, f"rate limit exceeded ({limit}/min)"
        window.append(now)
        return True, "ok"

    def list_devices(self) -> List[DeviceIdentityRecord]:
        return list(self._devices.values())


class RegistryHTTPHandler(BaseHTTPRequestHandler):
    """HTTP handler for the registry server."""

    server: RegistryHTTPServer

    def log_message(self, fmt, *args):
        logger.debug("registry-http %s", fmt % args)

    def _device_id(self) -> str:
        if hasattr(self.connection, "getpeercert"):
            cert = self.connection.getpeercert()
            if cert:
                for rdn in cert.get("subject", ()):
                    for key, value in rdn:
                        if key == "commonName":
                            return value
        token = self.headers.get("Authorization", "").replace("Bearer ", "").strip()
        if token:
            return f"token:{token[:16]}"
        return self.headers.get("X-Device-ID", "anonymous")

    def _json_response(self, code: int, data: Any) -> None:
        body = json.dumps(data, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _check_auth(self, channel: str = "") -> Optional[str]:
        device_id = self._device_id()
        ok, msg = self.server.auth_store.authenticate(device_id, channel)
        if not ok:
            self._json_response(403, {"error": msg})
            return None
        ok, msg = self.server.auth_store.check_rate_limit(device_id)
        if not ok:
            self._json_response(429, {"error": msg})
            return None
        return device_id

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        params = parse_qs(parsed.query)

        if path == "/v1/bundles":
            channel = params.get("channel", [None])[0]
            device_id = self._check_auth(channel or "")
            if not device_id:
                return
            from waveos.registry.store import RegistryStore
            store = RegistryStore(self.server.registry_root)
            entries = store.list_bundles(channel=channel)
            self._json_response(200, [e.to_dict() for e in entries])

        elif path.startswith("/v1/bundles/") and "/download" not in path:
            bundle_id = path.split("/v1/bundles/")[1]
            device_id = self._check_auth()
            if not device_id:
                return
            from waveos.registry.store import RegistryStore
            store = RegistryStore(self.server.registry_root)
            entry = store.get_entry(bundle_id)
            if entry:
                self._json_response(200, entry.to_dict())
            else:
                self._json_response(404, {"error": "not found"})

        elif "/download/" in path:
            parts = path.split("/download/")
            bundle_id = parts[0].split("/v1/bundles/")[1] if "/v1/bundles/" in parts[0] else ""
            file_name = parts[1] if len(parts) > 1 else ""
            device_id = self._check_auth()
            if not device_id:
                return
            file_path = self.server.registry_root / "bundles" / bundle_id / file_name
            if not file_path.is_file():
                self._json_response(404, {"error": "file not found"})
                return
            self._serve_file_resumable(file_path)

        elif path == "/v1/health":
            self._json_response(200, {"status": "ok", "timestamp": utc_now().isoformat()})

        else:
            self._json_response(404, {"error": "not found"})

    def _serve_file_resumable(self, file_path: Path) -> None:
        """Serve a file with Range request support for resumable downloads."""
        file_size = file_path.stat().st_size
        file_hash = hashlib.sha256(file_path.read_bytes()).hexdigest()
        range_header = self.headers.get("Range")
        start = 0
        end = file_size - 1

        if range_header and range_header.startswith("bytes="):
            try:
                range_spec = range_header[6:]
                if range_spec.endswith("-"):
                    start = int(range_spec[:-1])
                elif "-" in range_spec:
                    parts = range_spec.split("-")
                    start = int(parts[0])
                    end = int(parts[1])
            except ValueError:
                self.send_response(416)
                self.end_headers()
                return
            if start >= file_size or end >= file_size:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{file_size}")
                self.end_headers()
                return
            content_length = end - start + 1
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
        else:
            content_length = file_size
            self.send_response(200)

        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(content_length))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("X-Content-SHA256", file_hash)
        self.send_header("ETag", f'"{file_hash[:16]}"')
        self.end_headers()

        with file_path.open("rb") as f:
            f.seek(start)
            remaining = content_length
            while remaining > 0:
                chunk = f.read(min(65536, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path == "/v1/publish":
            device_id = self._check_auth()
            if not device_id:
                return
            content_length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(content_length).decode("utf-8")) if content_length > 0 else {}
            channel = body.get("channel", "dev")
            policy = self.server.publish_policy
            if policy.get("require_ci_identity") and not device_id.startswith("ci:"):
                self._json_response(403, {"error": "only CI identities can publish to this channel"})
                return
            protected_channels = policy.get("protected_channels", ["prod", "mission-critical"])
            if channel in protected_channels and not device_id.startswith("ci:"):
                self._json_response(403, {"error": f"channel {channel} requires CI identity"})
                return
            self._json_response(200, {"status": "accepted", "channel": channel, "publisher": device_id})
        else:
            self._json_response(404, {"error": "not found"})


class RegistryHTTPServer(HTTPServer):
    """Registry HTTP server with mTLS and auth."""

    def __init__(self, addr, handler, registry_root: Path, auth_store: Optional[DeviceAuthStore] = None, publish_policy: Optional[Dict[str, Any]] = None):
        super().__init__(addr, handler)
        self.registry_root = registry_root
        self.auth_store = auth_store or DeviceAuthStore()
        self.publish_policy = publish_policy or {}


def create_ssl_context(cert_path: str = "", key_path: str = "", ca_path: str = "", require_client_cert: bool = False) -> Optional[ssl.SSLContext]:
    """Create SSL context for mTLS."""
    if not cert_path or not key_path:
        return None
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
    cert_path: str = "",
    key_path: str = "",
    ca_path: str = "",
    require_client_cert: bool = False,
    publish_policy: Optional[Dict[str, Any]] = None,
) -> None:
    """Start the registry HTTP server."""
    auth_store = DeviceAuthStore(auth_store_path) if auth_store_path else DeviceAuthStore()
    server = RegistryHTTPServer((host, port), RegistryHTTPHandler, registry_root, auth_store, publish_policy or {})
    ssl_ctx = create_ssl_context(cert_path, key_path, ca_path, require_client_cert)
    if ssl_ctx:
        server.socket = ssl_ctx.wrap_socket(server.socket, server_side=True)
        logger.info("Registry server with mTLS on %s:%d", host, port)
    else:
        logger.info("Registry server (no TLS) on %s:%d", host, port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Registry server stopped")
    finally:
        server.server_close()
