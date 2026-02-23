"""
Coordinator v1 store: node registry, heartbeats, policy versions, run references.
Supports in-memory and optional SQLite backend for persistence.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from waveos.utils import get_logger

logger = get_logger("waveos.coordinator")


def _init_sqlite(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS coordinator_nodes (
            node_id TEXT PRIMARY KEY,
            site_id TEXT,
            role TEXT DEFAULT 'edge',
            endpoint TEXT,
            capabilities_json TEXT,
            meta_json TEXT,
            joined_at TEXT NOT NULL,
            last_seen_at TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_coordinator_nodes_site ON coordinator_nodes(site_id);

        CREATE TABLE IF NOT EXISTS coordinator_heartbeats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            node_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            payload_json TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (node_id) REFERENCES coordinator_nodes(node_id)
        );
        CREATE INDEX IF NOT EXISTS idx_heartbeats_node_time ON coordinator_heartbeats(node_id, timestamp);

        CREATE TABLE IF NOT EXISTS coordinator_policy (
            policy_id TEXT PRIMARY KEY,
            version TEXT NOT NULL,
            content_json TEXT,
            created_at TEXT NOT NULL,
            created_by TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_coordinator_policy_version ON coordinator_policy(version);

        CREATE TABLE IF NOT EXISTS coordinator_runs (
            run_id TEXT PRIMARY KEY,
            node_id TEXT NOT NULL,
            policy_version TEXT,
            summary_json TEXT,
            uploaded_at TEXT NOT NULL,
            FOREIGN KEY (node_id) REFERENCES coordinator_nodes(node_id)
        );
        CREATE INDEX IF NOT EXISTS idx_coordinator_runs_node ON coordinator_runs(node_id);

        CREATE TABLE IF NOT EXISTS coordinator_rollouts (
            rollout_id TEXT PRIMARY KEY,
            deployment_id TEXT NOT NULL,
            bundle_id TEXT NOT NULL,
            policy_version TEXT NOT NULL,
            node_ids_json TEXT,
            canary_percent INTEGER DEFAULT 0,
            canary_node_ids_json TEXT,
            status TEXT NOT NULL,
            started_at TEXT NOT NULL,
            promoted_at TEXT,
            rolled_back_at TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_rollouts_status ON coordinator_rollouts(status);
    """)


class CoordinatorStore:
    """In-memory or SQLite-backed store for coordinator state."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = Path(db_path) if db_path else None
        self._nodes: Dict[str, Dict[str, Any]] = {}
        self._heartbeats: Dict[str, List[Dict[str, Any]]] = {}
        self._policy: Dict[str, Dict[str, Any]] = {}
        self._runs: Dict[str, Dict[str, Any]] = {}
        if self.db_path:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            with self._conn() as conn:
                _init_sqlite(conn)

    def _conn(self) -> sqlite3.Connection:
        if not self.db_path:
            raise RuntimeError("CoordinatorStore initialized without db_path")
        return sqlite3.connect(str(self.db_path), timeout=10.0)

    # ---- Node registry ----
    def node_join(
        self,
        node_id: str,
        site_id: Optional[str] = None,
        role: str = "edge",
        endpoint: Optional[str] = None,
        capabilities: Optional[Dict[str, Any]] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        now = __import__("datetime").datetime.utcnow().isoformat() + "Z"
        node = {
            "node_id": node_id,
            "site_id": site_id,
            "role": role,
            "endpoint": endpoint,
            "capabilities": capabilities or {},
            "meta": meta or {},
            "joined_at": now,
            "last_seen_at": now,
        }
        self._nodes[node_id] = node
        if self.db_path:
            with self._conn() as conn:
                conn.execute(
                    """INSERT OR REPLACE INTO coordinator_nodes
                       (node_id, site_id, role, endpoint, capabilities_json, meta_json, joined_at, last_seen_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (node_id, site_id, role, endpoint, json.dumps(node["capabilities"]), json.dumps(node["meta"]), now, now),
                )
                conn.commit()
        return node

    def node_leave(self, node_id: str) -> bool:
        if node_id not in self._nodes:
            return False
        del self._nodes[node_id]
        if self.db_path:
            with self._conn() as conn:
                conn.execute("DELETE FROM coordinator_nodes WHERE node_id = ?", (node_id,))
                conn.commit()
        return True

    def node_update_seen(self, node_id: str) -> None:
        now = __import__("datetime").datetime.utcnow().isoformat() + "Z"
        if node_id in self._nodes:
            self._nodes[node_id]["last_seen_at"] = now
        if self.db_path:
            with self._conn() as conn:
                conn.execute("UPDATE coordinator_nodes SET last_seen_at = ? WHERE node_id = ?", (now, node_id))
                conn.commit()

    def list_nodes(self, site_id: Optional[str] = None) -> List[Dict[str, Any]]:
        if self.db_path:
            with self._conn() as conn:
                conn.row_factory = sqlite3.Row
                if site_id:
                    cur = conn.execute("SELECT * FROM coordinator_nodes WHERE site_id = ?", (site_id,))
                else:
                    cur = conn.execute("SELECT * FROM coordinator_nodes")
                rows = cur.fetchall()
            out = []
            for r in rows:
                out.append({
                    "node_id": r["node_id"],
                    "site_id": r["site_id"],
                    "role": r["role"],
                    "endpoint": r["endpoint"],
                    "capabilities": json.loads(r["capabilities_json"] or "{}"),
                    "meta": json.loads(r["meta_json"] or "{}"),
                    "joined_at": r["joined_at"],
                    "last_seen_at": r["last_seen_at"],
                })
            return out
        if site_id:
            return [n for n in self._nodes.values() if n.get("site_id") == site_id]
        return list(self._nodes.values())

    # ---- Heartbeats ----
    def heartbeat_ingest(self, node_id: str, payload: Optional[Dict[str, Any]] = None) -> None:
        now = __import__("datetime").datetime.utcnow().isoformat() + "Z"
        rec = {"node_id": node_id, "timestamp": now, "payload": payload or {}}
        self._heartbeats.setdefault(node_id, []).append(rec)
        if len(self._heartbeats[node_id]) > 1000:
            self._heartbeats[node_id] = self._heartbeats[node_id][-500:]
        self.node_update_seen(node_id)
        if self.db_path:
            with self._conn() as conn:
                conn.execute(
                    "INSERT INTO coordinator_heartbeats (node_id, timestamp, payload_json) VALUES (?, ?, ?)",
                    (node_id, now, json.dumps(payload or {})),
                )
                conn.execute("UPDATE coordinator_nodes SET last_seen_at = ? WHERE node_id = ?", (now, node_id))
                conn.commit()

    def is_online(self, node_id: str, max_age_seconds: float = 120.0) -> bool:
        from datetime import datetime, timezone, timedelta
        node = self._nodes.get(node_id) if not self.db_path else None
        if not self.db_path:
            last = (self._heartbeats.get(node_id) or [{}])[-1].get("timestamp") or (node or {}).get("last_seen_at")
        else:
            with self._conn() as conn:
                cur = conn.execute("SELECT last_seen_at FROM coordinator_nodes WHERE node_id = ?", (node_id,))
                row = cur.fetchone()
                last = row[0] if row else None
        if not last:
            return False
        try:
            dt = datetime.fromisoformat(str(last).replace("Z", "+00:00"))
            return (datetime.now(timezone.utc) - dt).total_seconds() <= max_age_seconds
        except (ValueError, TypeError):
            return False

    # ---- Policy ----
    def policy_put(self, version: str, content: Dict[str, Any], created_by: Optional[str] = None) -> str:
        now = __import__("datetime").datetime.utcnow().isoformat() + "Z"
        policy_id = f"policy-{uuid.uuid4().hex[:12]}"
        self._policy[policy_id] = {"policy_id": policy_id, "version": version, "content": content, "created_at": now, "created_by": created_by}
        if self.db_path:
            with self._conn() as conn:
                conn.execute(
                    "INSERT INTO coordinator_policy (policy_id, version, content_json, created_at, created_by) VALUES (?, ?, ?, ?, ?)",
                    (policy_id, version, json.dumps(content), now, created_by),
                )
                conn.commit()
        return policy_id

    def policy_get(self, version: str) -> Optional[Dict[str, Any]]:
        if self.db_path:
            with self._conn() as conn:
                cur = conn.execute("SELECT policy_id, version, content_json, created_at FROM coordinator_policy WHERE version = ? ORDER BY created_at DESC LIMIT 1", (version,))
                row = cur.fetchone()
            if not row:
                return None
            return {"policy_id": row[0], "version": row[1], "content": json.loads(row[2] or "{}"), "created_at": row[3]}
        for p in self._policy.values():
            if p["version"] == version:
                return p
        return None

    def policy_list_versions(self) -> List[str]:
        if self.db_path:
            with self._conn() as conn:
                cur = conn.execute("SELECT DISTINCT version FROM coordinator_policy ORDER BY version DESC")
                return [r[0] for r in cur.fetchall()]
        return list({p["version"] for p in self._policy.values()})

    # ---- Run ingestion ----
    def run_ingest(self, node_id: str, run_id: str, summary: Dict[str, Any], policy_version: Optional[str] = None) -> None:
        now = __import__("datetime").datetime.utcnow().isoformat() + "Z"
        self._runs[run_id] = {"run_id": run_id, "node_id": node_id, "policy_version": policy_version, "summary": summary, "uploaded_at": now}
        if self.db_path:
            with self._conn() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO coordinator_runs (run_id, node_id, policy_version, summary_json, uploaded_at) VALUES (?, ?, ?, ?, ?)",
                    (run_id, node_id, policy_version, json.dumps(summary), now),
                )
                conn.commit()

    def run_list(self, node_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        if self.db_path:
            with self._conn() as conn:
                if node_id:
                    cur = conn.execute("SELECT run_id, node_id, policy_version, summary_json, uploaded_at FROM coordinator_runs WHERE node_id = ? ORDER BY uploaded_at DESC LIMIT ?", (node_id, limit))
                else:
                    cur = conn.execute("SELECT run_id, node_id, policy_version, summary_json, uploaded_at FROM coordinator_runs ORDER BY uploaded_at DESC LIMIT ?", (limit,))
                rows = cur.fetchall()
            return [{"run_id": r[0], "node_id": r[1], "policy_version": r[2], "summary": json.loads(r[3] or "{}"), "uploaded_at": r[4]} for r in rows]
        out = list(self._runs.values())
        if node_id:
            out = [r for r in out if r["node_id"] == node_id]
        return sorted(out, key=lambda r: r["uploaded_at"], reverse=True)[:limit]

    # ---- Rollouts ----
    def rollout_start(
        self,
        rollout_id: str,
        deployment_id: str,
        bundle_id: str,
        policy_version: str,
        node_ids: List[str],
        canary_percent: int = 0,
        canary_node_ids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        now = __import__("datetime").datetime.utcnow().isoformat() + "Z"
        canary = canary_node_ids or []
        rec = {
            "rollout_id": rollout_id,
            "deployment_id": deployment_id,
            "bundle_id": bundle_id,
            "policy_version": policy_version,
            "node_ids": node_ids,
            "canary_percent": canary_percent,
            "canary_node_ids": canary,
            "status": "canary",
            "started_at": now,
            "promoted_at": None,
            "rolled_back_at": None,
        }
        if self.db_path:
            with self._conn() as conn:
                conn.execute(
                    """INSERT INTO coordinator_rollouts
                       (rollout_id, deployment_id, bundle_id, policy_version, node_ids_json, canary_percent, canary_node_ids_json, status, started_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (rollout_id, deployment_id, bundle_id, policy_version, json.dumps(node_ids), canary_percent, json.dumps(canary), "canary", now),
                )
                conn.commit()
        rec["rollout_id"] = rollout_id
        rec["canary_node_ids"] = canary
        return rec

    def rollout_promote(self, rollout_id: str) -> Optional[Dict[str, Any]]:
        now = __import__("datetime").datetime.utcnow().isoformat() + "Z"
        if self.db_path:
            with self._conn() as conn:
                conn.execute("UPDATE coordinator_rollouts SET status = ?, promoted_at = ? WHERE rollout_id = ?", ("completed", now, rollout_id))
                conn.commit()
                cur = conn.execute("SELECT rollout_id, status, promoted_at FROM coordinator_rollouts WHERE rollout_id = ?", (rollout_id,))
                row = cur.fetchone()
            return {"rollout_id": rollout_id, "status": row[1], "promoted_at": row[2]} if row else None
        return {"rollout_id": rollout_id, "status": "completed", "promoted_at": now}

    def rollout_rollback(self, rollout_id: str) -> Optional[Dict[str, Any]]:
        now = __import__("datetime").datetime.utcnow().isoformat() + "Z"
        if self.db_path:
            with self._conn() as conn:
                conn.execute("UPDATE coordinator_rollouts SET status = ?, rolled_back_at = ? WHERE rollout_id = ?", ("rolled_back", now, rollout_id))
                conn.commit()
                cur = conn.execute("SELECT rollout_id, status, rolled_back_at FROM coordinator_rollouts WHERE rollout_id = ?", (rollout_id,))
                row = cur.fetchone()
            return {"rollout_id": rollout_id, "status": row[1], "rolled_back_at": row[2]} if row else None
        return {"rollout_id": rollout_id, "status": "rolled_back", "rolled_back_at": now}

    def rollout_get(self, rollout_id: str) -> Optional[Dict[str, Any]]:
        if self.db_path:
            with self._conn() as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.execute("SELECT * FROM coordinator_rollouts WHERE rollout_id = ?", (rollout_id,))
                row = cur.fetchone()
            if not row:
                return None
            return {
                "rollout_id": row["rollout_id"],
                "deployment_id": row["deployment_id"],
                "bundle_id": row["bundle_id"],
                "policy_version": row["policy_version"],
                "node_ids": json.loads(row["node_ids_json"] or "[]"),
                "canary_percent": row["canary_percent"],
                "canary_node_ids": json.loads(row["canary_node_ids_json"] or "[]"),
                "status": row["status"],
                "started_at": row["started_at"],
                "promoted_at": row["promoted_at"],
                "rolled_back_at": row["rolled_back_at"],
            }
        return None

    def rollout_list(self, limit: int = 20) -> List[Dict[str, Any]]:
        if self.db_path:
            with self._conn() as conn:
                cur = conn.execute("SELECT rollout_id, status, policy_version, started_at FROM coordinator_rollouts ORDER BY started_at DESC LIMIT ?", (limit,))
                rows = cur.fetchall()
            return [dict(r) for r in rows]
        return []

    # ---- Fleet status API ----
    def fleet_status(self, max_age_seconds: float = 120.0) -> Dict[str, Any]:
        nodes = self.list_nodes()
        online = [n["node_id"] for n in nodes if self.is_online(n["node_id"], max_age_seconds)]
        return {
            "nodes": nodes,
            "online": online,
            "offline": [n["node_id"] for n in nodes if n["node_id"] not in online],
            "total": len(nodes),
            "online_count": len(online),
        }
