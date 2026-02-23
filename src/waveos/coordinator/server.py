"""
Coordinator v1 HTTP server: node registry, heartbeat ingestion, policy distribution,
run ingestion, central fleet status API. AuthN: optional Authorization bearer token or mTLS (scaffolding).
"""

from __future__ import annotations

import json
import os
import ssl
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlparse

from waveos.coordinator.store import CoordinatorStore
from waveos.utils import get_logger

logger = get_logger("waveos.coordinator")

# Defaults
DEFAULT_COORDINATOR_PORT = 9100
COORDINATOR_TOKEN_ENV = "WAVEOS_COORDINATOR_AGENT_TOKEN"
COORDINATOR_REQUIRE_MTLS_ENV = "WAVEOS_COORDINATOR_REQUIRE_MTLS"
COORDINATOR_AUDIT_PATH_ENV = "WAVEOS_COORDINATOR_AUDIT_PATH"


def _client_identity(handler: BaseHTTPRequestHandler) -> Optional[str]:
    """Extract client identity: mTLS cert CN or Bearer token (opaque)."""
    try:
        if hasattr(handler, "connection") and hasattr(handler.connection, "getpeercert"):
            cert = handler.connection.getpeercert()
            if cert and isinstance(cert, dict):
                for k, v in cert.get("subject", []):
                    if k == "commonName":
                        return f"mtls:{v}"
    except Exception:
        pass
    auth = handler.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return f"bearer:{auth[7:12]}..."
    return None


def _auth_ok(handler: BaseHTTPRequestHandler, node_id: Optional[str] = None, site_id: Optional[str] = None) -> bool:
    """Check auth: if require_mtls, need client cert; else Bearer or mTLS. Optionally check node/site RBAC."""
    require_mtls = os.getenv(COORDINATOR_REQUIRE_MTLS_ENV, "").strip().lower() in ("1", "true", "yes")
    identity = _client_identity(handler)
    if require_mtls and (not identity or not identity.startswith("mtls:")):
        return False
    token_env = os.getenv(COORDINATOR_TOKEN_ENV, "").strip()
    if token_env and (not identity or not (identity.startswith("mtls:") or handler.headers.get("Authorization", "").startswith("Bearer "))):
        return False
    if token_env and identity and not identity.startswith("mtls:"):
        auth = handler.headers.get("Authorization", "")
        if not (auth.startswith("Bearer ") and auth[7:].strip() == token_env):
            return False
    return True


def _audit_log(method: str, path: str, identity: Optional[str], allowed: bool, node_id: Optional[str] = None) -> None:
    """Append auth decision to audit log (who/what allowed or denied)."""
    audit_path = os.getenv(COORDINATOR_AUDIT_PATH_ENV, "").strip()
    if not audit_path:
        return
    try:
        import json as _json
        from pathlib import Path as _Path
        rec = {"ts": __import__("datetime").datetime.utcnow().isoformat() + "Z", "method": method, "path": path, "identity": identity, "allowed": allowed, "node_id": node_id}
        p = _Path(audit_path).expanduser()
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(_json.dumps(rec, default=str) + "\n")
    except Exception as e:
        logger.debug("Audit log write failed: %s", e)


def _send_json(handler: BaseHTTPRequestHandler, code: int, body: Any) -> None:
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json")
    handler.end_headers()
    handler.wfile.write(json.dumps(body, default=str).encode("utf-8"))


def _read_json(handler: BaseHTTPRequestHandler) -> Optional[Dict[str, Any]]:
    length = int(handler.headers.get("Content-Length", 0))
    if length <= 0:
        return None
    raw = handler.rfile.read(length).decode("utf-8", errors="replace")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _make_handler(store: CoordinatorStore) -> type:
    class CoordinatorHandler(BaseHTTPRequestHandler):
        store_instance = store

        def log_message(self, format: str, *args: Any) -> None:
            logger.debug(format, *args)

        def do_POST(self) -> None:
            path = urlparse(self.path).path
            if path in ("/heartbeat", "/heartbeat/"):
                self._post_heartbeat()
                return
            if path in ("/nodes/join", "/nodes/join/"):
                self._post_nodes_join()
                return
            if path.startswith("/runs") and path.strip("/") == "runs":
                self._post_runs()
                return
            if path in ("/policy", "/policy/"):
                self._post_policy()
                return
            if path in ("/actions/signed", "/actions/signed/"):
                self._post_actions_signed()
                return
            if path in ("/rollout", "/rollout/"):
                self._post_rollout()
                return
            if path.startswith("/rollout/"):
                parts = path.strip("/").split("/")
                if len(parts) == 3 and parts[0] == "rollout":
                    rollout_id, action = parts[1], parts[2]
                    if not self._auth_and_audit():
                        _send_json(self, 401, {"error": "unauthorized"})
                        return
                    if action == "promote":
                        r = self.store_instance.rollout_promote(rollout_id)
                        _send_json(self, 200, r if r else {"error": "rollout not found"})
                        return
                    if action == "rollback":
                        r = self.store_instance.rollout_rollback(rollout_id)
                        _send_json(self, 200, r if r else {"error": "rollout not found"})
                        return
            self.send_response(404)
            self.end_headers()

        def _auth_and_audit(self, node_id: Optional[str] = None) -> bool:
            identity = _client_identity(self)
            ok = _auth_ok(self, node_id=node_id)
            _audit_log(self.command, urlparse(self.path).path, identity, ok, node_id=node_id)
            return ok

        def _post_heartbeat(self) -> None:
            body = _read_json(self)
            node_id = (body or {}).get("node_id")
            if not self._auth_and_audit(node_id):
                _send_json(self, 401, {"error": "unauthorized"})
                return
            if not node_id:
                _send_json(self, 400, {"error": "node_id required"})
                return
            self.store_instance.heartbeat_ingest(node_id, body)
            _send_json(self, 202, {"ok": True, "node_id": node_id})

        def _post_nodes_join(self) -> None:
            body = _read_json(self)
            node_id = (body or {}).get("node_id")
            if not self._auth_and_audit(node_id):
                _send_json(self, 401, {"error": "unauthorized"})
                return
            if not node_id:
                _send_json(self, 400, {"error": "node_id required"})
                return
            node = self.store_instance.node_join(
                node_id=node_id,
                site_id=(body or {}).get("site_id"),
                role=(body or {}).get("role", "edge"),
                endpoint=(body or {}).get("endpoint"),
                capabilities=(body or {}).get("capabilities"),
                meta=(body or {}).get("meta"),
            )
            _send_json(self, 201, node)

        def _post_runs(self) -> None:
            body = _read_json(self)
            node_id = (body or {}).get("node_id")
            if not self._auth_and_audit(node_id):
                _send_json(self, 401, {"error": "unauthorized"})
                return
            run_id = (body or {}).get("run_id")
            summary = (body or {}).get("summary", body or {})
            if not node_id or not run_id:
                _send_json(self, 400, {"error": "node_id and run_id required"})
                return
            self.store_instance.run_ingest(node_id, run_id, summary, (body or {}).get("policy_version"))
            _send_json(self, 202, {"ok": True, "run_id": run_id})

        def _post_policy(self) -> None:
            if not self._auth_and_audit():
                _send_json(self, 401, {"error": "unauthorized"})
                return
            body = _read_json(self)
            version = (body or {}).get("version")
            content = (body or {}).get("content", body or {})
            if not version:
                _send_json(self, 400, {"error": "version required"})
                return
            policy_id = self.store_instance.policy_put(version, content, (body or {}).get("created_by"))
            _send_json(self, 201, {"policy_id": policy_id, "version": version})

        def _post_actions_signed(self) -> None:
            if not self._auth_and_audit():
                _send_json(self, 401, {"error": "unauthorized"})
                return
            from waveos.action_signing import sign_action_batch
            body = _read_json(self)
            actions = (body or {}).get("actions", [])
            scope = (body or {}).get("scope", "default")
            if not actions:
                _send_json(self, 400, {"error": "actions required"})
                return
            signed, err = sign_action_batch(actions, scope=scope)
            if err:
                _send_json(self, 500, {"error": err})
                return
            _send_json(self, 201, signed)

        def _post_rollout(self) -> None:
            if not self._auth_and_audit():
                _send_json(self, 401, {"error": "unauthorized"})
                return
            body = _read_json(self)
            policy_version = (body or {}).get("policy_version")
            node_ids = (body or {}).get("node_ids", [])
            canary_percent = int((body or {}).get("canary_percent", 0))
            site_id = (body or {}).get("site_id")
            if not policy_version or not node_ids:
                _send_json(self, 400, {"error": "policy_version and node_ids required"})
                return
            from waveos.coordinator.rollout import select_canary_nodes
            rollout_id = f"roll-{__import__('uuid').uuid4().hex[:12]}"
            canary_node_ids = select_canary_nodes(node_ids, canary_percent, canary_site_ids=[site_id] if site_id else None)
            rec = self.store_instance.rollout_start(
                rollout_id=rollout_id,
                deployment_id=(body or {}).get("deployment_id", rollout_id),
                bundle_id=(body or {}).get("bundle_id", ""),
                policy_version=policy_version,
                node_ids=node_ids,
                canary_percent=canary_percent,
                canary_node_ids=canary_node_ids if canary_node_ids else None,
            )
            _send_json(self, 201, rec)

        def do_GET(self) -> None:
            path = urlparse(self.path).path
            qs = parse_qs(urlparse(self.path).query)
            if path in ("/fleet/status", "/fleet/status/"):
                max_age = float(qs.get("max_age_seconds", [120])[0])
                status = self.store_instance.fleet_status(max_age_seconds=max_age)
                _send_json(self, 200, status)
                return
            if path in ("/nodes", "/nodes/"):
                site_id = qs.get("site_id", [None])[0]
                nodes = self.store_instance.list_nodes(site_id=site_id)
                _send_json(self, 200, {"nodes": nodes})
                return
            if path.startswith("/policy/"):
                version = path.split("/policy/")[-1].strip("/")
                policy = self.store_instance.policy_get(version)
                if not policy:
                    _send_json(self, 404, {"error": "policy version not found"})
                    return
                _send_json(self, 200, policy)
                return
            if path in ("/policy", "/policy/"):
                versions = self.store_instance.policy_list_versions()
                _send_json(self, 200, {"versions": versions})
                return
            if path in ("/runs", "/runs/"):
                node_id = qs.get("node_id", [None])[0]
                limit = int(qs.get("limit", [50])[0])
                runs = self.store_instance.run_list(node_id=node_id, limit=limit)
                _send_json(self, 200, {"runs": runs})
                return
            if path in ("/health", "/health/"):
                _send_json(self, 200, {"status": "ok", "service": "waveos-coordinator"})
                return
            if path.startswith("/rollout/"):
                parts = path.strip("/").split("/")
                if len(parts) == 2 and parts[0] == "rollout":
                    rollout_id = parts[1]
                    r = self.store_instance.rollout_get(rollout_id)
                    if not r:
                        _send_json(self, 404, {"error": "rollout not found"})
                        return
                    _send_json(self, 200, r)
                    return
            if path in ("/rollouts", "/rollouts/"):
                limit = int(qs.get("limit", [20])[0])
                _send_json(self, 200, {"rollouts": self.store_instance.rollout_list(limit=limit)})
                return
            self.send_response(404)
            self.end_headers()

        def do_PUT(self) -> None:
            path = urlparse(self.path).path
            parts = path.strip("/").split("/")
            if len(parts) >= 3 and parts[0] == "rollout":
                rollout_id = parts[1]
                action = parts[2]
                if not self._auth_and_audit():
                    _send_json(self, 401, {"error": "unauthorized"})
                    return
                if action == "promote":
                    r = self.store_instance.rollout_promote(rollout_id)
                    _send_json(self, 200, r if r else {"error": "rollout not found"})
                    return
                if action == "rollback":
                    r = self.store_instance.rollout_rollback(rollout_id)
                    _send_json(self, 200, r if r else {"error": "rollout not found"})
                    return
            self.send_response(404)
            self.end_headers()

        def do_DELETE(self) -> None:
            path = urlparse(self.path).path
            if path.startswith("/nodes/"):
                node_id = path.split("/nodes/")[-1].strip("/")
                if not node_id:
                    _send_json(self, 400, {"error": "node_id required"})
                    return
                if not self._auth_and_audit(node_id):
                    _send_json(self, 401, {"error": "unauthorized"})
                    return
                ok = self.store_instance.node_leave(node_id)
                _send_json(self, 200 if ok else 404, {"ok": ok})
                return
            self.send_response(404)
            self.end_headers()
    return CoordinatorHandler


def run_coordinator_server(
    host: str = "0.0.0.0",
    port: Optional[int] = None,
    db_path: Optional[Path] = None,
    use_ssl: bool = False,
    cert_path: Optional[str] = None,
    key_path: Optional[str] = None,
) -> None:
    """Run the coordinator HTTP server (blocking)."""
    port = port or int(os.getenv("WAVEOS_COORDINATOR_PORT", str(DEFAULT_COORDINATOR_PORT)))
    db_path = db_path or (Path(os.getenv("WAVEOS_COORDINATOR_DB", "out/coordinator/coordinator.db")).expanduser())
    store = CoordinatorStore(db_path=db_path)
    handler_class = _make_handler(store)
    server = HTTPServer((host, port), handler_class)
    if use_ssl or (cert_path and key_path):
        cert_path = cert_path or os.getenv("WAVEOS_COORDINATOR_TLS_CERT")
        key_path = key_path or os.getenv("WAVEOS_COORDINATOR_TLS_KEY")
        if cert_path and key_path and Path(cert_path).exists() and Path(key_path).exists():
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.load_cert_chain(cert_path, key_path)
            server.socket = ctx.wrap_socket(server.socket, server_side=True)
            logger.info("Coordinator TLS enabled")
    logger.info("Coordinator listening on %s:%s (DB: %s)", host, port, db_path)
    server.serve_forever()
