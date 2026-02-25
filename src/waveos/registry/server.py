"""WaveOS Registry Server — secure HTTP artifact distribution with mTLS, auth, rate limiting, and resumable downloads."""

from __future__ import annotations

import hashlib
import json
import os
import ssl
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse, parse_qs

from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.registry.server")


class RateLimiter:
    """Token-bucket rate limiter per client identity."""

    def __init__(self, rate: float = 10.0, burst: int = 50) -> None:
        self._rate = rate
        self._burst = burst
        self._buckets: Dict[str, tuple] = {}
        self._lock = threading.Lock()

    def allow(self, client_id: str) -> bool:
        now = time.monotonic()
        with self._lock:
            if client_id not in self._buckets:
                self._buckets[client_id] = (self._burst - 1, now)
                return True
            tokens, last = self._buckets[client_id]
            elapsed = now - last
            tokens = min(self._burst, tokens + elapsed * self._rate)
            if tokens < 1:
                return False
            self._buckets[client_id] = (tokens - 1, now)
            return True


class DeviceAuthenticator:
    """Authenticate devices via mTLS client certificate or bearer token."""

    def __init__(self, allowed_devices_path: Optional[Path] = None, token_map: Optional[Dict[str, str]] = None) -> None:
        self._allowed: Dict[str, Dict[str, Any]] = {}
        self._tokens = token_map or {}
        if allowed_devices_path and allowed_devices_path.exists():
            try:
                data = json.loads(allowed_devices_path.read_text(encoding="utf-8"))
                for device in data.get("devices", []):
                    self._allowed[device["device_id"]] = device
            except (json.JSONDecodeError, KeyError):
                pass
        env_tokens = os.getenv("WAVEOS_REGISTRY_AUTH_TOKENS", "")
        if env_tokens:
            for pair in env_tokens.split(","):
                if "=" in pair:
                    tok, dev = pair.strip().split("=", 1)
                    self._tokens[tok.strip()] = dev.strip()

    def authenticate_token(self, auth_header: str) -> Optional[str]:
        if not auth_header.startswith("Bearer "):
            return None
        token = auth_header[7:].strip()
        return self._tokens.get(token)

    def authenticate_cert(self, cert_cn: str) -> Optional[str]:
        if cert_cn in self._allowed:
            return cert_cn
        for dev_id, info in self._allowed.items():
            if info.get("cert_cn") == cert_cn:
                return dev_id
        return cert_cn if cert_cn else None

    def get_device_channels(self, device_id: str) -> List[str]:
        info = self._allowed.get(device_id, {})
        return info.get("channels", ["dev", "staging", "prod", "mission-critical"])

    def can_publish(self, device_id: str, channel: str) -> bool:
        info = self._allowed.get(device_id, {})
        role = info.get("role", "agent")
        if role == "ci" or role == "admin":
            return True
        if channel in ("prod", "mission-critical"):
            return False
        return True


class RegistryRequestHandler(BaseHTTPRequestHandler):
    """HTTP handler for registry operations."""

    server: RegistryHTTPServer

    def log_message(self, format, *args):
        logger.debug("Registry HTTP: %s", format % args)

    def _get_device_id(self) -> Optional[str]:
        auth = self.headers.get("Authorization", "")
        if auth:
            device_id = self.server.authenticator.authenticate_token(auth)
            if device_id:
                return device_id
        if hasattr(self.connection, "getpeercert"):
            cert = self.connection.getpeercert()
            if cert:
                for rdn in cert.get("subject", ()):
                    for attr, val in rdn:
                        if attr == "commonName":
                            return self.server.authenticator.authenticate_cert(val)
        return os.getenv("WAVEOS_REGISTRY_DEFAULT_DEVICE", "anonymous")

    def _check_rate(self, device_id: str) -> bool:
        if not self.server.rate_limiter.allow(device_id):
            self.send_error(429, "Rate limit exceeded")
            return False
        return True

    def _json_response(self, code: int, data: Any) -> None:
        body = json.dumps(data, indent=2, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        device_id = self._get_device_id()
        if not device_id:
            self.send_error(401, "Unauthorized")
            return
        if not self._check_rate(device_id):
            return

        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        params = parse_qs(parsed.query)

        if path == "/v1/bundles":
            channel = params.get("channel", [None])[0]
            from waveos.registry.store import RegistryStore
            store = RegistryStore(self.server.registry_root)
            entries = store.list_bundles(channel=channel)
            allowed_channels = self.server.authenticator.get_device_channels(device_id)
            entries = [e for e in entries if e.channel in allowed_channels]
            self._json_response(200, [e.to_dict() for e in entries])

        elif path.startswith("/v1/bundles/") and "/download" in path:
            parts = path.split("/")
            bundle_id = parts[3] if len(parts) > 3 else ""
            self._handle_download(bundle_id, device_id)

        elif path.startswith("/v1/bundles/"):
            bundle_id = path.split("/")[3] if len(path.split("/")) > 3 else ""
            from waveos.registry.store import RegistryStore
            store = RegistryStore(self.server.registry_root)
            entry = store.get_entry(bundle_id)
            if entry:
                self._json_response(200, entry.to_dict())
            else:
                self.send_error(404, "Bundle not found")

        elif path == "/v1/health":
            self._json_response(200, {"status": "ok", "timestamp": utc_now().isoformat()})

        else:
            self.send_error(404, "Not found")

    def _handle_download(self, bundle_id: str, device_id: str) -> None:
        from waveos.registry.store import RegistryStore
        store = RegistryStore(self.server.registry_root)
        bundle_path = store.get_bundle(bundle_id)
        if not bundle_path:
            self.send_error(404, "Bundle not found")
            return

        import tarfile
        import io
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            tar.add(str(bundle_path), arcname=bundle_id)
        content = buf.getvalue()
        total_size = len(content)

        content_hash = hashlib.sha256(content).hexdigest()

        range_header = self.headers.get("Range", "")
        if range_header.startswith("bytes="):
            try:
                range_spec = range_header[6:]
                start_str, end_str = range_spec.split("-", 1)
                start = int(start_str) if start_str else 0
                end = int(end_str) if end_str else total_size - 1
                end = min(end, total_size - 1)
                chunk = content[start:end + 1]
                chunk_hash = hashlib.sha256(chunk).hexdigest()
                self.send_response(206)
                self.send_header("Content-Type", "application/gzip")
                self.send_header("Content-Length", str(len(chunk)))
                self.send_header("Content-Range", f"bytes {start}-{end}/{total_size}")
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("X-Content-SHA256", content_hash)
                self.send_header("X-Chunk-SHA256", chunk_hash)
                self.end_headers()
                self.wfile.write(chunk)
                return
            except (ValueError, IndexError):
                pass

        self.send_response(200)
        self.send_header("Content-Type", "application/gzip")
        self.send_header("Content-Length", str(total_size))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("X-Content-SHA256", content_hash)
        self.end_headers()
        self.wfile.write(content)

    def do_POST(self) -> None:
        device_id = self._get_device_id()
        if not device_id:
            self.send_error(401, "Unauthorized")
            return
        if not self._check_rate(device_id):
            return

        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path == "/v1/bundles/publish":
            self._handle_publish(device_id)
        else:
            self.send_error(404, "Not found")

    def _handle_publish(self, device_id: str) -> None:
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length <= 0:
            self.send_error(400, "Missing content")
            return

        channel = self.headers.get("X-Channel", "dev")
        if not self.server.authenticator.can_publish(device_id, channel):
            self.send_error(403, f"Device {device_id} cannot publish to channel {channel}")
            return

        body = self.rfile.read(content_length)
        import tarfile
        import io
        import tempfile
        try:
            buf = io.BytesIO(body)
            with tarfile.open(fileobj=buf, mode="r:gz") as tar:
                tmpdir = Path(tempfile.mkdtemp(prefix="waveos_publish_"))
                tar.extractall(tmpdir, filter="data")
            subdirs = [d for d in tmpdir.iterdir() if d.is_dir()]
            bundle_dir = subdirs[0] if subdirs else tmpdir
            from waveos.registry.store import RegistryStore
            store = RegistryStore(self.server.registry_root)
            entry = store.publish(bundle_dir, channel=channel, publisher=device_id)
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)
            self._json_response(201, {"ok": True, "entry": entry.to_dict()})
        except Exception as exc:
            logger.warning("Publish failed: %s", exc)
            self.send_error(500, f"Publish failed: {exc}")


class RegistryHTTPServer(HTTPServer):
    def __init__(self, addr, handler, registry_root: Path, authenticator: DeviceAuthenticator, rate_limiter: RateLimiter):
        super().__init__(addr, handler)
        self.registry_root = registry_root
        self.authenticator = authenticator
        self.rate_limiter = rate_limiter


def run_registry_server(
    host: str = "0.0.0.0",
    port: int = 9200,
    registry_root: Path = Path("out/registry"),
    tls_cert: Optional[str] = None,
    tls_key: Optional[str] = None,
    tls_ca: Optional[str] = None,
    allowed_devices_path: Optional[Path] = None,
    rate: float = 10.0,
    burst: int = 50,
) -> None:
    """Start the registry HTTP server with optional mTLS."""
    tls_cert = tls_cert or os.getenv("WAVEOS_REGISTRY_TLS_CERT", "")
    tls_key = tls_key or os.getenv("WAVEOS_REGISTRY_TLS_KEY", "")
    tls_ca = tls_ca or os.getenv("WAVEOS_REGISTRY_TLS_CA", "")

    auth = DeviceAuthenticator(allowed_devices_path=allowed_devices_path)
    limiter = RateLimiter(rate=rate, burst=burst)
    server = RegistryHTTPServer((host, port), RegistryRequestHandler, registry_root, auth, limiter)

    if tls_cert and tls_key:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(tls_cert, tls_key)
        if tls_ca:
            ctx.load_verify_locations(tls_ca)
            ctx.verify_mode = ssl.CERT_REQUIRED
        else:
            ctx.verify_mode = ssl.CERT_OPTIONAL
        server.socket = ctx.wrap_socket(server.socket, server_side=True)
        logger.info("Registry server starting with TLS on %s:%d", host, port)
    else:
        logger.info("Registry server starting (no TLS) on %s:%d", host, port)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Registry server stopped")
    finally:
        server.server_close()
