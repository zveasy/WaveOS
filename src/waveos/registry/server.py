"""WaveOS Registry HTTP Server — mTLS, auth, rate limiting, resumable downloads."""

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
class RateLimitEntry:
    count: int = 0
    window_start: float = 0.0


@dataclass
class RegistryServerConfig:
    host: str = "0.0.0.0"
    port: int = 9200
    registry_root: str = "out/registry"
    tls_cert: str = ""
    tls_key: str = ""
    tls_ca: str = ""
    require_client_cert: bool = False
    auth_tokens: Dict[str, str] = field(default_factory=dict)
    rate_limit_per_minute: int = 60
    rate_limit_per_site: int = 300
    max_upload_bytes: int = 500 * 1024 * 1024

    @classmethod
    def from_env(cls) -> RegistryServerConfig:
        tokens = {}
        raw = os.getenv("WAVEOS_REGISTRY_AUTH_TOKENS", "")
        for pair in raw.split(","):
            if "=" in pair:
                k, v = pair.split("=", 1)
                tokens[k.strip()] = v.strip()
        return cls(
            host=os.getenv("WAVEOS_REGISTRY_HOST", "0.0.0.0"),
            port=int(os.getenv("WAVEOS_REGISTRY_PORT", "9200")),
            registry_root=os.getenv("WAVEOS_REGISTRY_ROOT", "out/registry"),
            tls_cert=os.getenv("WAVEOS_REGISTRY_TLS_CERT", ""),
            tls_key=os.getenv("WAVEOS_REGISTRY_TLS_KEY", ""),
            tls_ca=os.getenv("WAVEOS_REGISTRY_TLS_CA", ""),
            require_client_cert=os.getenv("WAVEOS_REGISTRY_REQUIRE_CLIENT_CERT", "").lower() in ("1", "true"),
            auth_tokens=tokens,
            rate_limit_per_minute=int(os.getenv("WAVEOS_REGISTRY_RATE_LIMIT", "60")),
        )


class _RateLimiter:
    def __init__(self, per_minute: int = 60) -> None:
        self._per_minute = per_minute
        self._clients: Dict[str, RateLimitEntry] = {}
        self._lock = threading.Lock()

    def allow(self, client_id: str) -> bool:
        now = time.monotonic()
        with self._lock:
            entry = self._clients.get(client_id)
            if entry is None or (now - entry.window_start) > 60:
                self._clients[client_id] = RateLimitEntry(count=1, window_start=now)
                return True
            if entry.count >= self._per_minute:
                return False
            entry.count += 1
            return True


class _RegistryHandler(BaseHTTPRequestHandler):
    server: _RegistryHTTPServer

    def log_message(self, format: str, *args: Any) -> None:
        logger.debug(format, *args)

    def _client_id(self) -> str:
        peer = getattr(self.connection, "getpeername", lambda: ("unknown", 0))()
        cn = ""
        if hasattr(self.connection, "getpeercert"):
            cert = self.connection.getpeercert()
            if cert:
                for rdn in cert.get("subject", ()):
                    for attr, val in rdn:
                        if attr == "commonName":
                            cn = val
        return cn or (peer[0] if isinstance(peer, tuple) else "unknown")

    def _check_auth(self) -> Optional[str]:
        tokens = self.server.config.auth_tokens
        if not tokens:
            return self._client_id()
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:].strip()
            identity = tokens.get(token)
            if identity:
                return identity
        return None

    def _check_rate_limit(self, client_id: str) -> bool:
        return self.server.rate_limiter.allow(client_id)

    def _send_json(self, code: int, data: Any) -> None:
        body = json.dumps(data, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error_json(self, code: int, message: str) -> None:
        self._send_json(code, {"error": message})

    def do_GET(self) -> None:
        identity = self._check_auth()
        if identity is None:
            self._send_error_json(401, "Unauthorized")
            return
        if not self._check_rate_limit(identity):
            self._send_error_json(429, "Rate limit exceeded")
            return

        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path == "/v1/bundles":
            self._handle_list_bundles(parsed)
        elif path.startswith("/v1/bundles/") and path.count("/") == 3:
            bundle_id = path.split("/")[3]
            self._handle_get_bundle_meta(bundle_id)
        elif path.startswith("/v1/bundles/") and "/download/" in path:
            parts = path.split("/")
            bundle_id = parts[3]
            filename = "/".join(parts[5:]) if len(parts) > 5 else ""
            self._handle_download(bundle_id, filename)
        elif path == "/v1/health":
            self._send_json(200, {"status": "ok", "timestamp": utc_now().isoformat()})
        else:
            self._send_error_json(404, "Not found")

    def do_POST(self) -> None:
        identity = self._check_auth()
        if identity is None:
            self._send_error_json(401, "Unauthorized")
            return
        if not self._check_rate_limit(identity):
            self._send_error_json(429, "Rate limit exceeded")
            return

        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path == "/v1/bundles":
            self._handle_publish(identity)
        else:
            self._send_error_json(404, "Not found")

    def _handle_list_bundles(self, parsed) -> None:
        from waveos.registry.store import RegistryStore
        store = RegistryStore(Path(self.server.config.registry_root))
        qs = parse_qs(parsed.query)
        channel = qs.get("channel", [None])[0]
        entries = store.list_bundles(channel=channel)
        self._send_json(200, [e.to_dict() for e in entries])

    def _handle_get_bundle_meta(self, bundle_id: str) -> None:
        from waveos.registry.store import RegistryStore
        store = RegistryStore(Path(self.server.config.registry_root))
        entry = store.get_entry(bundle_id)
        if entry:
            self._send_json(200, entry.to_dict())
        else:
            self._send_error_json(404, f"Bundle {bundle_id} not found")

    def _handle_download(self, bundle_id: str, filename: str) -> None:
        from waveos.registry.store import RegistryStore
        store = RegistryStore(Path(self.server.config.registry_root))
        bundle_path = store.get_bundle(bundle_id)
        if not bundle_path:
            self._send_error_json(404, f"Bundle {bundle_id} not found")
            return
        if not filename:
            filename = "bundle.json"
        file_path = bundle_path / filename
        try:
            file_path.resolve().relative_to(bundle_path.resolve())
        except ValueError:
            self._send_error_json(403, "Path traversal denied")
            return
        if not file_path.is_file():
            self._send_error_json(404, f"File {filename} not found")
            return
        file_size = file_path.stat().st_size
        range_header = self.headers.get("Range")
        start = 0
        end = file_size - 1
        if range_header and range_header.startswith("bytes="):
            try:
                r = range_header[6:]
                if r.endswith("-"):
                    start = int(r[:-1])
                elif r.startswith("-"):
                    start = file_size - int(r[1:])
                else:
                    parts = r.split("-")
                    start = int(parts[0])
                    end = int(parts[1])
            except (ValueError, IndexError):
                pass
        sha256 = hashlib.sha256()
        with file_path.open("rb") as f:
            while True:
                chunk = f.read(8192)
                if not chunk:
                    break
                sha256.update(chunk)
        digest = sha256.hexdigest()
        length = end - start + 1
        if range_header:
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
        else:
            self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(length))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("X-Content-SHA256", digest)
        self.send_header("ETag", f'"{digest[:16]}"')
        self.end_headers()
        with file_path.open("rb") as f:
            f.seek(start)
            remaining = length
            while remaining > 0:
                chunk = f.read(min(8192, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)

    def _handle_publish(self, publisher: str) -> None:
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length > self.server.config.max_upload_bytes:
            self._send_error_json(413, "Bundle too large")
            return
        body = self.rfile.read(content_length)
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self._send_error_json(400, "Invalid JSON")
            return
        channel = data.get("channel", "dev")
        bundle_id = data.get("bundle_id", "")
        if not bundle_id:
            self._send_error_json(400, "Missing bundle_id")
            return
        from waveos.registry.store import RegistryStore
        store = RegistryStore(Path(self.server.config.registry_root))
        bundle_path = store.get_bundle(bundle_id)
        if bundle_path:
            entry = store.get_entry(bundle_id)
            if entry:
                entries = store._load_index()
                entries = [e for e in entries if e.bundle_id != bundle_id]
                from waveos.registry.store import RegistryEntry
                entry.channel = channel
                entry.published_at = utc_now().isoformat()
                entry.publisher = publisher
                entries.append(entry)
                store._save_index(entries)
            self._send_json(200, {"ok": True, "bundle_id": bundle_id, "channel": channel, "publisher": publisher})
        else:
            self._send_error_json(404, f"Bundle {bundle_id} not found in store; publish via file-system first")


class _RegistryHTTPServer(HTTPServer):
    def __init__(self, config: RegistryServerConfig) -> None:
        self.config = config
        self.rate_limiter = _RateLimiter(config.rate_limit_per_minute)
        super().__init__((config.host, config.port), _RegistryHandler)


def create_ssl_context(config: RegistryServerConfig) -> Optional[ssl.SSLContext]:
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
    cfg = config or RegistryServerConfig.from_env()
    Path(cfg.registry_root).mkdir(parents=True, exist_ok=True)
    server = _RegistryHTTPServer(cfg)
    ctx = create_ssl_context(cfg)
    if ctx:
        server.socket = ctx.wrap_socket(server.socket, server_side=True)
        logger.info("Registry server starting with TLS on %s:%d", cfg.host, cfg.port)
    else:
        logger.info("Registry server starting (no TLS) on %s:%d", cfg.host, cfg.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Registry server stopping")
    finally:
        server.server_close()
