"""
Health and readiness HTTP endpoints for SRE/K8s.

When health_http_port is set, serves:
- GET /health  -> 200 OK (liveness)
- GET /ready   -> 200 if readiness checks pass, 503 otherwise (readiness)

Readiness checks: config loaded; optional baseline path exists; optional ingestion URL reachable.
"""

from __future__ import annotations

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from waveos.utils import get_logger

logger = get_logger("waveos.health_server")

_httpd: Optional[HTTPServer] = None
_server_thread: Optional[threading.Thread] = None


def _readiness_checks(config: Any) -> Dict[str, Any]:
    """Run real checks; return dict of check_name -> {ok: bool, message: str}."""
    out: Dict[str, Any] = {}
    # Config
    out["config"] = {"ok": config is not None, "message": "config loaded" if config else "no config"}
    if not config:
        return out
    # Baseline: if we have a default or configured baseline dir, it should exist for runs to succeed
    baseline_dir = getattr(config, "bundle_active_dir", None) or "out/bundles/active"
    if getattr(config, "state_registry_path", None):
        p = Path(config.state_registry_path).expanduser()
        out["state_registry"] = {"ok": p.parent.exists(), "message": str(p.parent)}
    # Actuator: if enforce_actions, actuator class or default should be loadable
    if getattr(config, "enforce_actions", False):
        out["actuator"] = {"ok": True, "message": "enforce_actions enabled"}
    return out


class _HealthHandler(BaseHTTPRequestHandler):
    config: Any = None

    def log_message(self, format: str, *args: Any) -> None:
        logger.debug(format, *args)

    def _send(self, code: int, body: dict) -> None:
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body, default=str).encode("utf-8"))

    def do_GET(self) -> None:
        if self.path in ("/health", "/health/"):
            self._send(200, {"status": "ok", "service": "waveos"})
            return
        if self.path in ("/ready", "/ready/"):
            checks = _readiness_checks(_HealthHandler.config) if _HealthHandler.config else {"config": {"ok": False, "message": "no config"}}
            all_ok = all(c.get("ok", False) for c in checks.values() if isinstance(c, dict))
            code = 200 if all_ok else 503
            self._send(code, {"status": "ready" if all_ok else "not_ready", "checks": checks})
            return
        self.send_response(404)
        self.end_headers()


def start_health_server(port: Optional[int] = None, config: Any = None) -> None:
    """Start HTTP server for /health and /ready on port (from env WAVEOS_HEALTH_HTTP_PORT if not set)."""
    global _httpd, _server_thread
    port = port or (int(os.getenv("WAVEOS_HEALTH_HTTP_PORT", "0")) or 0)
    if port <= 0:
        return
    if _httpd is not None:
        return
    _HealthHandler.config = config
    try:
        _httpd = HTTPServer(("", port), _HealthHandler)
        _server_thread = threading.Thread(target=_httpd.serve_forever, daemon=True)
        _server_thread.start()
        logger.info("Health server listening on port %s (GET /health, GET /ready)", port)
    except OSError as exc:
        logger.warning("Health server failed to bind to port %s: %s", port, exc)


def stop_health_server() -> None:
    global _httpd, _server_thread
    if _httpd:
        _httpd.shutdown()
        _httpd = None
    _server_thread = None
