"""WaveOS Registry Server — secure HTTP distribution with mTLS, auth, rate limiting, and resumable downloads."""

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
from typing import Any, Dict, List, Optional, Tuple

from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.registry.server")


@dataclass
class DeviceIdentity:
    """Identity extracted from mTLS client certificate."""
    device_id: str
    site_id: str = ""
    clearance: str = "unclassified"
    roles: List[str] = field(default_factory=list)

    def can_access_channel(self, channel: str) -> bool:
        channel_clearance = {
            "dev": ["unclassified", "confidential", "secret", "top_secret"],
            "staging": ["confidential", "secret", "top_secret"],
            "prod": ["secret", "top_secret"],
            "mission-critical": ["top_secret"],
        }
        return self.clearance in channel_clearance.get(channel, [])

    def can_publish(self) -> bool:
        return "ci_publisher" in self.roles or "admin" in self.roles


class TokenBucket:
    """Thread-safe token bucket rate limiter."""

    def __init__(self, rate: float = 10.0, capacity: float = 50.0) -> None:
        self._rate = rate
        self._capacity = capacity
        self._tokens = capacity
        self._last = time.monotonic()
        self._lock = threading.Lock()

    def consume(self, tokens: float = 1.0) -> bool:
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last
            self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
            self._last = now
            if self._tokens >= tokens:
                self._tokens -= tokens
                return True
            return False


class RateLimiter:
    """Per-device and per-site rate limiter."""

    def __init__(self, device_rate: float = 10.0, site_rate: float = 100.0) -> None:
        self._device_buckets: Dict[str, TokenBucket] = {}
        self._site_buckets: Dict[str, TokenBucket] = {}
        self._device_rate = device_rate
        self._site_rate = site_rate
        self._lock = threading.Lock()

    def allow(self, device_id: str, site_id: str = "") -> bool:
        with self._lock:
            if device_id not in self._device_buckets:
                self._device_buckets[device_id] = TokenBucket(rate=self._device_rate)
            if site_id and site_id not in self._site_buckets:
                self._site_buckets[site_id] = TokenBucket(rate=self._site_rate, capacity=self._site_rate * 10)
        if not self._device_buckets[device_id].consume():
            return False
        if site_id and not self._site_buckets[site_id].consume():
            return False
        return True


@dataclass
class RegistryServerConfig:
    host: str = "0.0.0.0"
    port: int = 9200
    registry_root: Path = Path("out/registry")
    tls_cert: str = ""
    tls_key: str = ""
    tls_ca: str = ""
    require_client_cert: bool = False
    device_rate_per_sec: float = 10.0
    site_rate_per_sec: float = 100.0
    publish_requires_ci: bool = True
    auth_tokens: Dict[str, DeviceIdentity] = field(default_factory=dict)


def _extract_device_identity(handler: BaseHTTPRequestHandler, config: RegistryServerConfig) -> Optional[DeviceIdentity]:
    """Extract device identity from mTLS client cert or auth token."""
    auth_header = handler.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
        if token in config.auth_tokens:
            return config.auth_tokens[token]
        identity_json = handler.headers.get("X-WaveOS-Identity", "")
        if identity_json:
            try:
                d = json.loads(identity_json)
                return DeviceIdentity(
                    device_id=d.get("device_id", token[:16]),
                    site_id=d.get("site_id", ""),
                    clearance=d.get("clearance", "unclassified"),
                    roles=d.get("roles", []),
                )
            except (json.JSONDecodeError, KeyError):
                pass
        return DeviceIdentity(device_id=token[:16])
    if hasattr(handler, "connection") and hasattr(handler.connection, "getpeercert"):
        cert = handler.connection.getpeercert()
        if cert:
            subject = dict(x[0] for x in cert.get("subject", []))
            cn = subject.get("commonName", "")
            ou = subject.get("organizationalUnitName", "")
            return DeviceIdentity(
                device_id=cn,
                site_id=ou,
                clearance="secret",
                roles=["device"],
            )
    return DeviceIdentity(device_id="anonymous")


def _create_handler(config: RegistryServerConfig, rate_limiter: RateLimiter):
    from waveos.registry.store import RegistryStore
    store = RegistryStore(config.registry_root)

    class RegistryHandler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            logger.debug(format, *args)

        def _send_json(self, status: int, data: Any) -> None:
            body = json.dumps(data, indent=2, default=str).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _get_identity(self) -> DeviceIdentity:
            return _extract_device_identity(self, config) or DeviceIdentity(device_id="anonymous")

        def _check_rate_limit(self, identity: DeviceIdentity) -> bool:
            if not rate_limiter.allow(identity.device_id, identity.site_id):
                self._send_json(429, {"error": "rate_limit_exceeded", "device_id": identity.device_id})
                return False
            return True

        def do_GET(self) -> None:
            identity = self._get_identity()
            if not self._check_rate_limit(identity):
                return

            if self.path == "/v1/bundles":
                channel = ""
                if "?" in self.path:
                    qs = self.path.split("?", 1)[1]
                    for param in qs.split("&"):
                        if param.startswith("channel="):
                            channel = param.split("=", 1)[1]
                entries = store.list_bundles(channel=channel or None)
                filtered = [e.to_dict() for e in entries if identity.can_access_channel(e.channel)]
                self._send_json(200, {"bundles": filtered})
                return

            if self.path.startswith("/v1/bundles/"):
                parts = self.path.split("/")
                if len(parts) >= 4:
                    bundle_id = parts[3]
                    entry = store.get_entry(bundle_id)
                    if not entry:
                        self._send_json(404, {"error": "not_found"})
                        return
                    if not identity.can_access_channel(entry.channel):
                        self._send_json(403, {"error": "channel_access_denied", "channel": entry.channel})
                        return

                    if len(parts) == 4:
                        self._send_json(200, entry.to_dict())
                        return

                    if len(parts) >= 5 and parts[4] == "download":
                        file_name = "/".join(parts[5:]) if len(parts) > 5 else ""
                        bundle_path = store.get_bundle(bundle_id)
                        if not bundle_path:
                            self._send_json(404, {"error": "bundle_dir_not_found"})
                            return
                        target = bundle_path / file_name if file_name else bundle_path / "bundle.json"
                        if not target.is_file():
                            self._send_json(404, {"error": "file_not_found", "file": file_name})
                            return
                        file_size = target.stat().st_size
                        file_hash = hashlib.sha256(target.read_bytes()).hexdigest()
                        range_header = self.headers.get("Range", "")
                        start = 0
                        end = file_size - 1
                        if range_header.startswith("bytes="):
                            try:
                                range_spec = range_header[6:]
                                if "-" in range_spec:
                                    s, e = range_spec.split("-", 1)
                                    start = int(s) if s else 0
                                    end = int(e) if e else file_size - 1
                            except ValueError:
                                pass
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
                                chunk_size = min(65536, remaining)
                                chunk = f.read(chunk_size)
                                if not chunk:
                                    break
                                self.wfile.write(chunk)
                                remaining -= len(chunk)
                        return

            if self.path == "/v1/health":
                self._send_json(200, {"status": "ok", "timestamp": utc_now().isoformat()})
                return

            self._send_json(404, {"error": "not_found"})

        def do_POST(self) -> None:
            identity = self._get_identity()
            if not self._check_rate_limit(identity):
                return

            if self.path == "/v1/bundles/publish":
                if config.publish_requires_ci and not identity.can_publish():
                    self._send_json(403, {"error": "publish_denied", "reason": "Only CI/admin identities can publish"})
                    return
                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length)
                try:
                    data = json.loads(body)
                except json.JSONDecodeError:
                    self._send_json(400, {"error": "invalid_json"})
                    return
                channel = data.get("channel", "dev")
                bundle_path_str = data.get("bundle_path", "")
                if not bundle_path_str:
                    self._send_json(400, {"error": "missing_bundle_path"})
                    return
                bundle_path = Path(bundle_path_str)
                if not bundle_path.is_dir():
                    self._send_json(400, {"error": "bundle_path_not_found"})
                    return
                try:
                    entry = store.publish(bundle_path, channel=channel, publisher=identity.device_id)
                    self._send_json(201, {"published": entry.to_dict()})
                except Exception as exc:
                    self._send_json(500, {"error": str(exc)})
                return

            self._send_json(404, {"error": "not_found"})

    return RegistryHandler


def create_ssl_context(config: RegistryServerConfig) -> Optional[ssl.SSLContext]:
    """Create SSL context for mTLS."""
    if not config.tls_cert or not config.tls_key:
        return None
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(config.tls_cert, config.tls_key)
    if config.tls_ca:
        ctx.load_verify_locations(config.tls_ca)
    if config.require_client_cert:
        ctx.verify_mode = ssl.CERT_REQUIRED
    else:
        ctx.verify_mode = ssl.CERT_OPTIONAL
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    return ctx


def run_registry_server(config: Optional[RegistryServerConfig] = None) -> None:
    """Start the registry HTTP server."""
    cfg = config or RegistryServerConfig()
    rate_limiter = RateLimiter(device_rate=cfg.device_rate_per_sec, site_rate=cfg.site_rate_per_sec)
    handler_class = _create_handler(cfg, rate_limiter)
    server = HTTPServer((cfg.host, cfg.port), handler_class)
    ssl_ctx = create_ssl_context(cfg)
    if ssl_ctx:
        server.socket = ssl_ctx.wrap_socket(server.socket, server_side=True)
        logger.info("Registry server starting with TLS on %s:%d", cfg.host, cfg.port)
    else:
        logger.info("Registry server starting (no TLS) on %s:%d", cfg.host, cfg.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Registry server stopped")
    finally:
        server.server_close()
