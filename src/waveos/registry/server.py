"""WaveOS Registry Server — HTTP registry with mTLS, auth, rate limiting, and resumable downloads."""

from __future__ import annotations

import hashlib
import json
import os
import ssl
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

from waveos.registry.store import RegistryStore, RegistryEntry
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
    registry_root: Path = Path("out/registry")
    tls_cert: str = ""
    tls_key: str = ""
    tls_ca: str = ""
    require_client_cert: bool = False
    rate_limit_per_minute: int = 60
    rate_limit_downloads_per_minute: int = 30
    allowed_publishers: List[str] = field(default_factory=list)
    require_ci_for_prod: bool = True
    auth_tokens: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> RegistryServerConfig:
        tokens_raw = os.getenv("WAVEOS_REGISTRY_AUTH_TOKENS", "")
        tokens = {}
        if tokens_raw:
            for pair in tokens_raw.split(","):
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    tokens[k.strip()] = v.strip()
        publishers_raw = os.getenv("WAVEOS_REGISTRY_ALLOWED_PUBLISHERS", "")
        publishers = [p.strip() for p in publishers_raw.split(",") if p.strip()] if publishers_raw else []
        return cls(
            host=os.getenv("WAVEOS_REGISTRY_HOST", "0.0.0.0"),
            port=int(os.getenv("WAVEOS_REGISTRY_PORT", "9200")),
            registry_root=Path(os.getenv("WAVEOS_REGISTRY_ROOT", "out/registry")),
            tls_cert=os.getenv("WAVEOS_REGISTRY_TLS_CERT", ""),
            tls_key=os.getenv("WAVEOS_REGISTRY_TLS_KEY", ""),
            tls_ca=os.getenv("WAVEOS_REGISTRY_TLS_CA", ""),
            require_client_cert=os.getenv("WAVEOS_REGISTRY_REQUIRE_CLIENT_CERT", "").lower() in ("1", "true"),
            rate_limit_per_minute=int(os.getenv("WAVEOS_REGISTRY_RATE_LIMIT", "60")),
            allowed_publishers=publishers,
            require_ci_for_prod=os.getenv("WAVEOS_REGISTRY_REQUIRE_CI_FOR_PROD", "true").lower() in ("1", "true"),
            auth_tokens=tokens,
        )


class _RateLimiter:
    def __init__(self, max_per_minute: int = 60) -> None:
        self._max = max_per_minute
        self._clients: Dict[str, RateLimitEntry] = {}
        self._lock = threading.Lock()

    def check(self, client_id: str) -> bool:
        now = time.monotonic()
        with self._lock:
            entry = self._clients.get(client_id)
            if not entry or now - entry.window_start > 60:
                self._clients[client_id] = RateLimitEntry(count=1, window_start=now)
                return True
            if entry.count >= self._max:
                return False
            entry.count += 1
            return True


class RegistryHandler(BaseHTTPRequestHandler):
    server: RegistryHTTPServer

    def log_message(self, format: str, *args: Any) -> None:
        logger.debug("registry-http %s", format % args)

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

    def _authenticate(self) -> Optional[str]:
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:].strip()
            identity = self.server.config.auth_tokens.get(token)
            if identity:
                return identity
        client_cn = self._client_id()
        if client_cn and client_cn != "unknown":
            return client_cn
        return None

    def _check_rate_limit(self) -> bool:
        client = self._client_id()
        return self.server.rate_limiter.check(client)

    def _send_json(self, code: int, data: Any) -> None:
        body = json.dumps(data, indent=2, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error_json(self, code: int, message: str) -> None:
        self._send_json(code, {"error": message})

    def do_GET(self) -> None:
        if not self._check_rate_limit():
            self._send_error_json(429, "Rate limit exceeded")
            return
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path == "/v1/bundles":
            params = parse_qs(parsed.query)
            channel = params.get("channel", [None])[0]
            entries = self.server.store.list_bundles(channel=channel)
            self._send_json(200, [e.to_dict() for e in entries])

        elif path.startswith("/v1/bundles/") and "/download" not in path:
            bundle_id = path.split("/v1/bundles/")[1]
            entry = self.server.store.get_entry(bundle_id)
            if entry:
                self._send_json(200, entry.to_dict())
            else:
                self._send_error_json(404, f"Bundle not found: {bundle_id}")

        elif path.startswith("/v1/bundles/") and path.endswith("/download"):
            parts = path.split("/")
            bundle_id = parts[3] if len(parts) > 3 else ""
            self._handle_download(bundle_id)

        elif path == "/v1/health":
            self._send_json(200, {"status": "ok", "timestamp": utc_now().isoformat()})

        else:
            self._send_error_json(404, "Not found")

    def _handle_download(self, bundle_id: str) -> None:
        bundle_path = self.server.store.get_bundle(bundle_id)
        if not bundle_path:
            self._send_error_json(404, f"Bundle not found: {bundle_id}")
            return
        manifest_path = bundle_path / "bundle.json"
        if not manifest_path.exists():
            self._send_error_json(404, "Bundle manifest missing")
            return

        file_param = parse_qs(urlparse(self.path).query).get("file", [None])[0]
        target = manifest_path
        if file_param:
            target = bundle_path / file_param
            if not target.exists() or not str(target.resolve()).startswith(str(bundle_path.resolve())):
                self._send_error_json(404, "File not found in bundle")
                return

        data = target.read_bytes()
        total = len(data)
        sha256 = hashlib.sha256(data).hexdigest()

        range_header = self.headers.get("Range", "")
        if range_header.startswith("bytes="):
            try:
                spec = range_header[6:]
                start_str, end_str = spec.split("-", 1)
                start = int(start_str) if start_str else 0
                end = int(end_str) if end_str else total - 1
                end = min(end, total - 1)
                chunk = data[start:end + 1]
                self.send_response(206)
                self.send_header("Content-Range", f"bytes {start}-{end}/{total}")
                self.send_header("Content-Length", str(len(chunk)))
                self.send_header("X-Content-SHA256", sha256)
                self.send_header("Accept-Ranges", "bytes")
                self.end_headers()
                self.wfile.write(chunk)
                return
            except (ValueError, IndexError):
                pass

        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(total))
        self.send_header("X-Content-SHA256", sha256)
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self) -> None:
        if not self._check_rate_limit():
            self._send_error_json(429, "Rate limit exceeded")
            return
        identity = self._authenticate()
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path == "/v1/bundles":
            params = parse_qs(parsed.query)
            channel = params.get("channel", ["dev"])[0]
            if channel in ("prod", "mission-critical") and self.server.config.require_ci_for_prod:
                if not identity:
                    self._send_error_json(403, "Authentication required for prod channel")
                    return
                if self.server.config.allowed_publishers and identity not in self.server.config.allowed_publishers:
                    self._send_error_json(403, f"Publisher '{identity}' not authorized for {channel}")
                    return
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length) if content_length > 0 else b""
            try:
                payload = json.loads(body) if body else {}
            except json.JSONDecodeError:
                self._send_error_json(400, "Invalid JSON")
                return
            bundle_dir_str = payload.get("bundle_dir", "")
            if not bundle_dir_str:
                self._send_error_json(400, "bundle_dir required")
                return
            bundle_dir = Path(bundle_dir_str)
            if not bundle_dir.is_dir():
                self._send_error_json(400, f"Not a directory: {bundle_dir}")
                return
            try:
                entry = self.server.store.publish(bundle_dir, channel=channel, publisher=identity or "anonymous")
                self._send_json(201, entry.to_dict())
            except ValueError as exc:
                self._send_error_json(400, str(exc))

        elif path == "/v1/promote":
            if not identity:
                self._send_error_json(403, "Authentication required")
                return
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length) if content_length > 0 else b""
            try:
                payload = json.loads(body) if body else {}
            except json.JSONDecodeError:
                self._send_error_json(400, "Invalid JSON")
                return
            bundle_id = payload.get("bundle_id", "")
            target_channel = payload.get("target_channel", "")
            if not bundle_id or not target_channel:
                self._send_error_json(400, "bundle_id and target_channel required")
                return
            entry = self.server.store.get_entry(bundle_id)
            if not entry:
                self._send_error_json(404, f"Bundle not found: {bundle_id}")
                return
            bundle_path = self.server.store.get_bundle(bundle_id)
            if not bundle_path:
                self._send_error_json(404, "Bundle files not found")
                return
            new_entry = self.server.store.publish(bundle_path, channel=target_channel, publisher=identity)
            promotion = {
                "event": "promote",
                "bundle_id": bundle_id,
                "from_channel": entry.channel,
                "to_channel": target_channel,
                "promoted_by": identity,
                "timestamp": utc_now().isoformat(),
            }
            self._log_audit(promotion)
            self._send_json(200, {"promotion": promotion, "entry": new_entry.to_dict()})

        else:
            self._send_error_json(404, "Not found")

    def _log_audit(self, event: Dict[str, Any]) -> None:
        audit_path = self.server.config.registry_root / "audit.jsonl"
        try:
            with audit_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(event, default=str) + "\n")
        except OSError:
            logger.warning("Failed to write audit log")


class RegistryHTTPServer(HTTPServer):
    def __init__(self, config: RegistryServerConfig) -> None:
        self.config = config
        self.store = RegistryStore(config.registry_root)
        self.rate_limiter = _RateLimiter(config.rate_limit_per_minute)
        super().__init__((config.host, config.port), RegistryHandler)

    def setup_tls(self) -> None:
        if not self.config.tls_cert or not self.config.tls_key:
            return
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(self.config.tls_cert, self.config.tls_key)
        if self.config.tls_ca:
            ctx.load_verify_locations(self.config.tls_ca)
        if self.config.require_client_cert:
            ctx.verify_mode = ssl.CERT_REQUIRED
        else:
            ctx.verify_mode = ssl.CERT_OPTIONAL
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        self.socket = ctx.wrap_socket(self.socket, server_side=True)
        logger.info("TLS enabled (client_cert=%s)", "required" if self.config.require_client_cert else "optional")


def run_registry_server(config: Optional[RegistryServerConfig] = None) -> None:
    cfg = config or RegistryServerConfig.from_env()
    server = RegistryHTTPServer(cfg)
    server.setup_tls()
    logger.info("Registry server listening on %s:%d", cfg.host, cfg.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Registry server stopped")
    finally:
        server.server_close()
