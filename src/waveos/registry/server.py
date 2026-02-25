"""WaveOS Registry Server — HTTP distribution plane with mTLS, auth, rate limiting, resumable downloads."""

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

_CHUNK_SIZE = 65536


@dataclass
class DeviceCredential:
    device_id: str
    channels: List[str] = field(default_factory=lambda: ["dev"])
    clearance: str = "operator"
    rate_limit_per_min: int = 60
    site_id: str = ""
    enabled: bool = True

    def to_dict(self) -> dict:
        return {"device_id": self.device_id, "channels": self.channels, "clearance": self.clearance,
                "rate_limit_per_min": self.rate_limit_per_min, "site_id": self.site_id, "enabled": self.enabled}

    @classmethod
    def from_dict(cls, d: dict) -> DeviceCredential:
        return cls(**{k: d[k] for k in d if k in cls.__dataclass_fields__})


class DeviceAuthStore:
    """Manages device identity and authorization for registry access."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self._devices: Dict[str, DeviceCredential] = {}
        self._path = path
        if path and path.exists():
            self._load()

    def _load(self) -> None:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            for d in data:
                cred = DeviceCredential.from_dict(d)
                self._devices[cred.device_id] = cred
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to load device auth store: %s", exc)

    def save(self) -> None:
        if self._path:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps([c.to_dict() for c in self._devices.values()], indent=2) + "\n", encoding="utf-8")

    def register(self, cred: DeviceCredential) -> None:
        self._devices[cred.device_id] = cred
        self.save()

    def revoke(self, device_id: str) -> bool:
        if device_id in self._devices:
            self._devices[device_id].enabled = False
            self.save()
            return True
        return False

    def get(self, device_id: str) -> Optional[DeviceCredential]:
        return self._devices.get(device_id)

    def authorize(self, device_id: str, channel: str) -> tuple[bool, str]:
        cred = self._devices.get(device_id)
        if not cred:
            return False, "unknown device"
        if not cred.enabled:
            return False, "device revoked"
        if channel not in cred.channels and "*" not in cred.channels:
            return False, f"device not authorized for channel {channel}"
        return True, "ok"

    def list_devices(self) -> List[DeviceCredential]:
        return list(self._devices.values())


class RateLimiter:
    """Token-bucket rate limiter per device and per site."""

    def __init__(self) -> None:
        self._buckets: Dict[str, List[float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str, max_per_min: int = 60) -> bool:
        now = time.monotonic()
        with self._lock:
            bucket = self._buckets.setdefault(key, [])
            bucket[:] = [t for t in bucket if now - t < 60.0]
            if len(bucket) >= max_per_min:
                return False
            bucket.append(now)
            return True


class RegistryHandler(BaseHTTPRequestHandler):
    """HTTP handler for registry server with auth, rate limiting, and resumable downloads."""

    registry_root: Path
    auth_store: DeviceAuthStore
    rate_limiter: RateLimiter
    publish_tokens: Dict[str, str] = {}

    def log_message(self, format, *args):
        logger.debug("Registry %s %s", self.client_address[0], format % args)

    def _device_id(self) -> str:
        token = self.headers.get("Authorization", "").replace("Bearer ", "").strip()
        device_id = self.headers.get("X-Device-ID", "").strip()
        if device_id:
            return device_id
        if hasattr(self.connection, "getpeercert"):
            cert = self.connection.getpeercert()
            if cert:
                for field_set in cert.get("subject", ()):
                    for key, val in field_set:
                        if key == "commonName":
                            return val
        return token or "anonymous"

    def _check_auth(self, channel: str = "dev") -> bool:
        device_id = self._device_id()
        ok, reason = self.server._auth_store.authorize(device_id, channel)
        if not ok:
            self._json_response(403, {"error": reason, "device_id": device_id})
            return False
        cred = self.server._auth_store.get(device_id)
        rate_limit = cred.rate_limit_per_min if cred else 60
        if not self.server._rate_limiter.check(device_id, rate_limit):
            self._json_response(429, {"error": "rate limit exceeded", "device_id": device_id})
            return False
        return True

    def _json_response(self, code: int, body: Any) -> None:
        payload = json.dumps(body, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _check_publish_auth(self) -> bool:
        token = self.headers.get("Authorization", "").replace("Bearer ", "").strip()
        valid_tokens = self.server._publish_tokens
        if not valid_tokens:
            return True
        if token in valid_tokens:
            return True
        self._json_response(403, {"error": "publish requires CI token"})
        return False

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        params = parse_qs(parsed.query)

        if path == "/v1/bundles":
            channel = params.get("channel", [None])[0]
            if channel and not self._check_auth(channel):
                return
            elif not channel and not self._check_auth("dev"):
                return
            from waveos.registry.store import RegistryStore
            store = RegistryStore(self.server._registry_root)
            entries = store.list_bundles(channel=channel)
            self._json_response(200, [e.to_dict() for e in entries])

        elif path.startswith("/v1/bundles/"):
            parts = path.split("/")
            if len(parts) < 4:
                self._json_response(400, {"error": "missing bundle_id"})
                return
            bundle_id = parts[3]
            remaining = "/".join(parts[4:]) if len(parts) > 4 else ""

            from waveos.registry.store import RegistryStore
            store = RegistryStore(self.server._registry_root)
            entry = store.get_entry(bundle_id)
            if not entry:
                self._json_response(404, {"error": f"bundle {bundle_id} not found"})
                return
            if not self._check_auth(entry.channel):
                return

            if not remaining:
                self._json_response(200, entry.to_dict())
                return

            bundle_path = store.get_bundle(bundle_id)
            if not bundle_path:
                self._json_response(404, {"error": "bundle files not found"})
                return
            file_path = bundle_path / remaining
            if not file_path.is_file():
                self._json_response(404, {"error": f"file not found: {remaining}"})
                return

            file_size = file_path.stat().st_size
            range_header = self.headers.get("Range")
            start, end = 0, file_size - 1

            if range_header and range_header.startswith("bytes="):
                try:
                    range_spec = range_header[6:]
                    if range_spec.endswith("-"):
                        start = int(range_spec[:-1])
                    elif range_spec.startswith("-"):
                        start = file_size - int(range_spec[1:])
                    else:
                        s, e = range_spec.split("-", 1)
                        start, end = int(s), int(e)
                except (ValueError, IndexError):
                    self._json_response(416, {"error": "invalid range"})
                    return

                if start >= file_size or end >= file_size or start > end:
                    self._json_response(416, {"error": "range not satisfiable"})
                    return

                content_length = end - start + 1
                self.send_response(206)
                self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
            else:
                content_length = file_size
                self.send_response(200)

            sha256 = hashlib.sha256()
            self.send_header("Content-Length", str(content_length))
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()

            with file_path.open("rb") as f:
                f.seek(start)
                remaining_bytes = content_length
                while remaining_bytes > 0:
                    chunk = f.read(min(_CHUNK_SIZE, remaining_bytes))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    sha256.update(chunk)
                    remaining_bytes -= len(chunk)

        elif path == "/v1/health":
            self._json_response(200, {"status": "ok", "timestamp": utc_now().isoformat()})

        else:
            self._json_response(404, {"error": "not found"})

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path == "/v1/bundles":
            if not self._check_publish_auth():
                return
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length > 0 else {}
            bundle_path = body.get("bundle_path", "")
            channel = body.get("channel", "dev")
            publisher = body.get("publisher", self._device_id())
            if not bundle_path or not Path(bundle_path).is_dir():
                self._json_response(400, {"error": "bundle_path required and must be a directory"})
                return
            from waveos.registry.store import RegistryStore
            store = RegistryStore(self.server._registry_root)
            try:
                entry = store.publish(Path(bundle_path), channel=channel, publisher=publisher)
                self._json_response(201, entry.to_dict())
            except Exception as exc:
                self._json_response(500, {"error": str(exc)})

        elif path.startswith("/v1/bundles/") and path.endswith("/promote"):
            if not self._check_publish_auth():
                return
            parts = path.split("/")
            bundle_id = parts[3]
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length > 0 else {}
            target_channel = body.get("channel", "staging")
            approver = body.get("approver", self._device_id())
            from waveos.registry.store import RegistryStore
            store = RegistryStore(self.server._registry_root)
            entry = store.get_entry(bundle_id)
            if not entry:
                self._json_response(404, {"error": f"bundle {bundle_id} not found"})
                return
            entries = store._load_index()
            for e in entries:
                if e.bundle_id == bundle_id:
                    e.channel = target_channel
                    e.metadata["promoted_at"] = utc_now().isoformat()
                    e.metadata["promoted_by"] = approver
                    e.metadata["promoted_from"] = entry.channel
            store._save_index(entries)
            self._json_response(200, {"bundle_id": bundle_id, "channel": target_channel, "promoted_by": approver})

        else:
            self._json_response(404, {"error": "not found"})


class WaveOSRegistryServer(HTTPServer):
    def __init__(self, addr, handler_class, registry_root: Path,
                 auth_store: DeviceAuthStore, rate_limiter: Optional[RateLimiter] = None,
                 publish_tokens: Optional[Dict[str, str]] = None,
                 ssl_cert: Optional[str] = None, ssl_key: Optional[str] = None,
                 ssl_ca: Optional[str] = None, require_client_cert: bool = False):
        super().__init__(addr, handler_class)
        self._registry_root = registry_root
        self._auth_store = auth_store
        self._rate_limiter = rate_limiter or RateLimiter()
        self._publish_tokens = publish_tokens or {}
        if ssl_cert and ssl_key:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.load_cert_chain(ssl_cert, ssl_key)
            if ssl_ca:
                ctx.load_verify_locations(ssl_ca)
            if require_client_cert:
                ctx.verify_mode = ssl.CERT_REQUIRED
            else:
                ctx.verify_mode = ssl.CERT_OPTIONAL
            self.socket = ctx.wrap_socket(self.socket, server_side=True)


def run_registry_server(
    host: str = "0.0.0.0", port: int = 9200,
    registry_root: Path = Path("out/registry"),
    auth_store_path: Optional[Path] = None,
    publish_tokens: Optional[Dict[str, str]] = None,
    ssl_cert: Optional[str] = None, ssl_key: Optional[str] = None,
    ssl_ca: Optional[str] = None, require_client_cert: bool = False,
) -> None:
    auth_store = DeviceAuthStore(auth_store_path)
    server = WaveOSRegistryServer(
        (host, port), RegistryHandler, registry_root, auth_store,
        publish_tokens=publish_tokens, ssl_cert=ssl_cert, ssl_key=ssl_key,
        ssl_ca=ssl_ca, require_client_cert=require_client_cert,
    )
    logger.info("Registry server on %s:%d (mTLS=%s)", host, port, bool(ssl_cert))
    server.serve_forever()
