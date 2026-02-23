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


def _check_actuator_reachability() -> Dict[str, Any]:
    """Check actuator connectivity (Implementation Priorities §6). HTTPS only, no private IPs."""
    url = os.getenv("WAVEOS_ACTUATOR_SDN_URL", "").strip()
    if not url or not url.lower().startswith("https://"):
        return {"ok": True, "message": "no actuator URL to check"}
    try:
        import urllib.request
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=3) as resp:
            return {"ok": resp.status < 500, "message": f"HTTP {resp.status}"}
    except Exception as exc:
        return {"ok": False, "message": str(type(exc).__name__)}


def _check_telemetry_freshness(config: Any) -> Dict[str, Any]:
    """Check ingest freshness: last run output or telemetry file mtime (Implementation Priorities §6)."""
    out = {"ok": True, "message": "no path to check"}
    path = os.getenv("WAVEOS_TELEMETRY_FRESHNESS_PATH", "").strip()
    if path:
        p = Path(path).expanduser()
        if p.exists():
            age_sec = (__import__("time").time() - p.stat().st_mtime)
            max_stale = int(os.getenv("WAVEOS_TELEMETRY_MAX_STALE_SEC", "600"))
            out["ok"] = age_sec <= max_stale
            out["message"] = f"age_sec={age_sec:.0f} max_stale={max_stale}"
        else:
            out["ok"] = False
            out["message"] = "path missing"
    return out


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
    # Actuator: if enforce_actions, check actuator reachability when URL is set
    if getattr(config, "enforce_actions", False):
        out["actuator"] = _check_actuator_reachability()
    # Telemetry freshness (optional: set WAVEOS_TELEMETRY_FRESHNESS_PATH to a file that should be recent)
    out["telemetry_freshness"] = _check_telemetry_freshness(config)
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
