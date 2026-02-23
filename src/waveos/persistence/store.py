"""
Persistent storage for runs, scores, events, and actions.

Phase 1: SQLite backend (local). When persistence_enabled and persistence_db_path are set,
run data is written to the DB in addition to (or instead of) file outputs. Enables
searchable history, audit, and future fleet/coordinator use.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from waveos.utils import get_logger

logger = get_logger("waveos.persistence")

SCHEMA_VERSION = 1


@dataclass
class RunRecord:
    """Minimal run record for storage."""
    run_id: str
    output_dir: str
    started_at: str
    completed_at: str
    waveos_version: Optional[str] = None
    policy_version: Optional[str] = None
    sample_count: int = 0
    score_count: int = 0
    event_count: int = 0
    action_count: int = 0
    enforce_actions: bool = False
    run_meta_json: Optional[str] = None


def _init_sqlite(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY);
        INSERT OR IGNORE INTO schema_version (version) VALUES (1);
        INSERT OR IGNORE INTO schema_version (version) VALUES (2);
        INSERT OR IGNORE INTO schema_version (version) VALUES (3);

        CREATE TABLE IF NOT EXISTS runs (
            run_id TEXT PRIMARY KEY,
            output_dir TEXT NOT NULL,
            started_at TEXT NOT NULL,
            completed_at TEXT NOT NULL,
            waveos_version TEXT,
            policy_version TEXT,
            sample_count INTEGER DEFAULT 0,
            score_count INTEGER DEFAULT 0,
            event_count INTEGER DEFAULT 0,
            action_count INTEGER DEFAULT 0,
            enforce_actions INTEGER DEFAULT 0,
            run_meta_json TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS run_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            seq INTEGER NOT NULL,
            event_json TEXT NOT NULL,
            FOREIGN KEY (run_id) REFERENCES runs(run_id)
        );
        CREATE INDEX IF NOT EXISTS idx_run_events_run_id ON run_events(run_id);

        CREATE TABLE IF NOT EXISTS run_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            seq INTEGER NOT NULL,
            action_json TEXT NOT NULL,
            FOREIGN KEY (run_id) REFERENCES runs(run_id)
        );
        CREATE INDEX IF NOT EXISTS idx_run_actions_run_id ON run_actions(run_id);

        CREATE TABLE IF NOT EXISTS run_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            score REAL NOT NULL,
            status TEXT NOT NULL,
            drivers_json TEXT,
            FOREIGN KEY (run_id) REFERENCES runs(run_id)
        );
        CREATE INDEX IF NOT EXISTS idx_run_scores_run_id ON run_scores(run_id);

        CREATE TABLE IF NOT EXISTS incidents (
            incident_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            severity TEXT NOT NULL,
            summary TEXT,
            timeline_json TEXT,
            actions_taken_json TEXT,
            outcomes_json TEXT,
            recommended_next_steps_json TEXT,
            run_meta_snapshot TEXT,
            FOREIGN KEY (run_id) REFERENCES runs(run_id)
        );
        CREATE INDEX IF NOT EXISTS idx_incidents_run_id ON incidents(run_id);
        CREATE INDEX IF NOT EXISTS idx_incidents_created_at ON incidents(created_at);

        CREATE TABLE IF NOT EXISTS action_transactions (
            action_id TEXT PRIMARY KEY,
            idempotency_key TEXT NOT NULL,
            state TEXT NOT NULL,
            run_id TEXT NOT NULL,
            action_type TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            rationale TEXT,
            parameters_json TEXT,
            proposed_at TEXT,
            dispatched_at TEXT,
            acked_at TEXT,
            verified_at TEXT,
            outcome TEXT,
            verification_summary TEXT,
            ack_message TEXT,
            actual_state_json TEXT,
            error_message TEXT,
            details_json TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_action_transactions_idempotency ON action_transactions(idempotency_key);
        CREATE INDEX IF NOT EXISTS idx_action_transactions_run_id ON action_transactions(run_id);
        CREATE INDEX IF NOT EXISTS idx_action_transactions_entity ON action_transactions(entity_type, entity_id);
        CREATE INDEX IF NOT EXISTS idx_action_transactions_dispatched_at ON action_transactions(dispatched_at);

        CREATE TABLE IF NOT EXISTS deployments (
            deployment_id TEXT PRIMARY KEY,
            bundle_id TEXT NOT NULL,
            policy_version TEXT,
            started_at TEXT NOT NULL,
            completed_at TEXT,
            status TEXT NOT NULL,
            node_ids_json TEXT,
            canary_percent INTEGER,
            promoted_at TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_deployments_bundle ON deployments(bundle_id);
        CREATE INDEX IF NOT EXISTS idx_deployments_status ON deployments(status);

        CREATE TABLE IF NOT EXISTS policy_versions_applied (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            node_id TEXT NOT NULL,
            policy_version TEXT NOT NULL,
            applied_at TEXT NOT NULL,
            run_id TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_policy_versions_node ON policy_versions_applied(node_id);
    """)
    for col, default in [
        ("status", "DEFAULT 'open'"),
        ("closed_at", ""),
        ("escalated_at", ""),
        ("escalation_reason", ""),
        ("postmortem_path", ""),
    ]:
        try:
            conn.execute(f"ALTER TABLE incidents ADD COLUMN {col} TEXT {default}".strip())
        except sqlite3.OperationalError:
            pass
    try:
        conn.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (4)")
    except sqlite3.OperationalError:
        pass


class SQLiteStore:
    """SQLite-backed store for runs, events, actions, scores."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            _init_sqlite(conn)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def save_run(
        self,
        run_id: str,
        output_dir: str,
        run_meta: Dict[str, Any],
        scores: List[Dict[str, Any]],
        events: List[Dict[str, Any]],
        actions: List[Dict[str, Any]],
    ) -> None:
        started_at = run_meta.get("started_at", "")
        completed_at = run_meta.get("completed_at", "")
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO runs (
                    run_id, output_dir, started_at, completed_at,
                    waveos_version, policy_version,
                    sample_count, score_count, event_count, action_count,
                    enforce_actions, run_meta_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    output_dir,
                    started_at,
                    completed_at,
                    run_meta.get("waveos_version"),
                    run_meta.get("policy_version"),
                    run_meta.get("sample_count", 0),
                    run_meta.get("score_count", 0),
                    run_meta.get("event_count", 0),
                    run_meta.get("action_count", 0),
                    1 if run_meta.get("enforce_actions") else 0,
                    json.dumps(run_meta, default=str),
                ),
            )
            conn.execute("DELETE FROM run_events WHERE run_id = ?", (run_id,))
            for seq, ev in enumerate(events):
                conn.execute(
                    "INSERT INTO run_events (run_id, seq, event_json) VALUES (?, ?, ?)",
                    (run_id, seq, json.dumps(ev, default=str)),
                )
            conn.execute("DELETE FROM run_actions WHERE run_id = ?", (run_id,))
            for seq, ac in enumerate(actions):
                conn.execute(
                    "INSERT INTO run_actions (run_id, seq, action_json) VALUES (?, ?, ?)",
                    (run_id, seq, json.dumps(ac, default=str)),
                )
            conn.execute("DELETE FROM run_scores WHERE run_id = ?", (run_id,))
            for sc in scores:
                conn.execute(
                    "INSERT INTO run_scores (run_id, entity_type, entity_id, score, status, drivers_json) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        run_id,
                        sc.get("entity_type", ""),
                        sc.get("entity_id", ""),
                        float(sc.get("score", 0)),
                        sc.get("status", ""),
                        json.dumps(sc.get("drivers", []), default=str),
                    ),
                )
            conn.commit()
        logger.debug("Persisted run %s to %s", run_id, self.db_path)

    def get_recent_runs(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return most recent runs (for admin/fleet views)."""
        with self._conn() as conn:
            cur = conn.execute(
                """
                SELECT run_id, output_dir, started_at, completed_at,
                       waveos_version, sample_count, score_count, event_count, action_count, enforce_actions
                FROM runs ORDER BY completed_at DESC LIMIT ?
                """,
                (limit,),
            )
            rows = cur.fetchall()
        return [dict(r) for r in rows]

    def get_run_meta(self, run_id: str) -> Optional[Dict[str, Any]]:
        with self._conn() as conn:
            cur = conn.execute("SELECT run_meta_json FROM runs WHERE run_id = ?", (run_id,))
            row = cur.fetchone()
        if not row or not row[0]:
            return None
        return json.loads(row[0])

    def save_incident(
        self,
        incident_id: str,
        run_id: str,
        created_at: str,
        severity: str,
        summary: str,
        timeline_json: str,
        actions_taken_json: str,
        outcomes_json: str,
        recommended_next_steps_json: str,
        run_meta_snapshot: Optional[str] = None,
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO incidents (
                    incident_id, run_id, created_at, severity, summary,
                    timeline_json, actions_taken_json, outcomes_json,
                    recommended_next_steps_json, run_meta_snapshot
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    incident_id,
                    run_id,
                    created_at,
                    severity,
                    summary,
                    timeline_json,
                    actions_taken_json,
                    outcomes_json,
                    recommended_next_steps_json,
                    run_meta_snapshot,
                ),
            )
            conn.commit()
        logger.debug("Persisted incident %s for run %s", incident_id, run_id)

    def get_recent_incidents(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._conn() as conn:
            cur = conn.execute(
                "SELECT incident_id, run_id, created_at, severity, summary FROM incidents ORDER BY created_at DESC LIMIT ?",
                (limit,),
            )
            rows = cur.fetchall()
        return [dict(r) for r in rows]

    def save_action_transaction(self, txn: Dict[str, Any]) -> None:
        """Insert or replace one action transaction (lifecycle state)."""
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO action_transactions (
                    action_id, idempotency_key, state, run_id, action_type, entity_type, entity_id,
                    rationale, parameters_json, proposed_at, dispatched_at, acked_at, verified_at,
                    outcome, verification_summary, ack_message, actual_state_json, error_message, details_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                """,
                (
                    txn.get("action_id"),
                    txn.get("idempotency_key"),
                    txn.get("state"),
                    txn.get("run_id", ""),
                    txn.get("action_type", ""),
                    txn.get("entity_type", ""),
                    txn.get("entity_id", ""),
                    txn.get("rationale", ""),
                    json.dumps(txn.get("parameters", {}), default=str),
                    txn.get("proposed_at"),
                    txn.get("dispatched_at"),
                    txn.get("acked_at"),
                    txn.get("verified_at"),
                    txn.get("outcome"),
                    txn.get("verification_summary"),
                    txn.get("ack_message"),
                    json.dumps(txn.get("actual_state"), default=str) if txn.get("actual_state") is not None else None,
                    txn.get("error_message"),
                    json.dumps(txn.get("details", {}), default=str),
                ),
            )
            conn.commit()
        logger.debug("Persisted action_transaction %s state=%s", txn.get("action_id"), txn.get("state"))

    def get_action_by_idempotency_key(self, idempotency_key: str) -> Optional[Dict[str, Any]]:
        """Return existing transaction if idempotency key was already applied (within TTL)."""
        with self._conn() as conn:
            cur = conn.execute(
                "SELECT action_id, state, run_id, acked_at, outcome FROM action_transactions WHERE idempotency_key = ?",
                (idempotency_key,),
            )
            row = cur.fetchone()
        if not row:
            return None
        return {"action_id": row[0], "state": row[1], "run_id": row[2], "acked_at": row[3], "outcome": row[4]}

    def update_action_transaction_state(
        self,
        action_id: str,
        state: str,
        dispatched_at: Optional[str] = None,
        acked_at: Optional[str] = None,
        verified_at: Optional[str] = None,
        outcome: Optional[str] = None,
        verification_summary: Optional[str] = None,
        ack_message: Optional[str] = None,
        actual_state: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
    ) -> None:
        """Update lifecycle state of an action transaction."""
        with self._conn() as conn:
            updates = ["state = ?", "updated_at = datetime('now')"]
            args: List[Any] = [state]
            if dispatched_at is not None:
                updates.append("dispatched_at = ?")
                args.append(dispatched_at)
            if acked_at is not None:
                updates.append("acked_at = ?")
                args.append(acked_at)
            if verified_at is not None:
                updates.append("verified_at = ?")
                args.append(verified_at)
            if outcome is not None:
                updates.append("outcome = ?")
                args.append(outcome)
            if verification_summary is not None:
                updates.append("verification_summary = ?")
                args.append(verification_summary)
            if ack_message is not None:
                updates.append("ack_message = ?")
                args.append(ack_message)
            if actual_state is not None:
                updates.append("actual_state_json = ?")
                args.append(json.dumps(actual_state, default=str))
            if error_message is not None:
                updates.append("error_message = ?")
                args.append(error_message)
            args.append(action_id)
            conn.execute(f"UPDATE action_transactions SET {', '.join(updates)} WHERE action_id = ?", args)
            conn.commit()
        logger.debug("Updated action_transaction %s -> %s", action_id, state)

    def get_last_dispatched_at(self, entity_type: str, entity_id: str) -> Optional[str]:
        """Return ISO timestamp of last dispatched action for this entity (for cooldown)."""
        with self._conn() as conn:
            cur = conn.execute(
                "SELECT dispatched_at FROM action_transactions WHERE entity_type = ? AND entity_id = ? AND dispatched_at IS NOT NULL ORDER BY dispatched_at DESC LIMIT 1",
                (entity_type, entity_id),
            )
            row = cur.fetchone()
        return row[0] if row and row[0] else None

    def get_recent_action_transactions(self, run_id: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """List recent action transactions, optionally filtered by run_id."""
        with self._conn() as conn:
            if run_id:
                cur = conn.execute(
                    "SELECT action_id, idempotency_key, state, run_id, entity_id, outcome, dispatched_at, verified_at FROM action_transactions WHERE run_id = ? ORDER BY dispatched_at DESC LIMIT ?",
                    (run_id, limit),
                )
            else:
                cur = conn.execute(
                    "SELECT action_id, idempotency_key, state, run_id, entity_id, outcome, dispatched_at, verified_at FROM action_transactions ORDER BY dispatched_at DESC LIMIT ?",
                    (limit,),
                )
            rows = cur.fetchall()
        return [dict(r) for r in rows]

    def save_deployment(
        self,
        deployment_id: str,
        bundle_id: str,
        policy_version: Optional[str],
        started_at: str,
        status: str,
        completed_at: Optional[str] = None,
        node_ids_json: Optional[str] = None,
        canary_percent: Optional[int] = None,
        promoted_at: Optional[str] = None,
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO deployments
                   (deployment_id, bundle_id, policy_version, started_at, completed_at, status, node_ids_json, canary_percent, promoted_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (deployment_id, bundle_id, policy_version or "", started_at, completed_at, status, node_ids_json, canary_percent, promoted_at),
            )
            conn.commit()

    def list_deployments(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._conn() as conn:
            cur = conn.execute(
                "SELECT deployment_id, bundle_id, policy_version, started_at, completed_at, status, canary_percent FROM deployments ORDER BY started_at DESC LIMIT ?",
                (limit,),
            )
            rows = cur.fetchall()
        return [dict(r) for r in rows]

    def save_policy_version_applied(self, node_id: str, policy_version: str, applied_at: str, run_id: Optional[str] = None) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO policy_versions_applied (node_id, policy_version, applied_at, run_id) VALUES (?, ?, ?, ?)",
                (node_id, policy_version, applied_at, run_id or ""),
            )
            conn.commit()

    def get_policy_versions_applied(self, node_id: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        with self._conn() as conn:
            if node_id:
                cur = conn.execute(
                    "SELECT node_id, policy_version, applied_at, run_id FROM policy_versions_applied WHERE node_id = ? ORDER BY applied_at DESC LIMIT ?",
                    (node_id, limit),
                )
            else:
                cur = conn.execute(
                    "SELECT node_id, policy_version, applied_at, run_id FROM policy_versions_applied ORDER BY applied_at DESC LIMIT ?",
                    (limit,),
                )
            rows = cur.fetchall()
        return [dict(r) for r in rows]

    def retention_cleanup(self, retention_days: int) -> int:
        """Delete runs and related data older than retention_days. Returns number of runs deleted."""
        if retention_days <= 0:
            return 0
        with self._conn() as conn:
            cur = conn.execute(
                "DELETE FROM runs WHERE date(completed_at) < date('now', ?)",
                (f"-{retention_days} days",),
            )
            deleted = cur.rowcount
            conn.commit()
        logger.info("Retention cleanup: removed %s runs older than %s days", deleted, retention_days)
        return deleted


_store: Optional[SQLiteStore] = None


def get_store(db_path: Optional[Path] = None) -> Optional[SQLiteStore]:
    """Return the global SQLite store if db_path was set and DB exists or was created."""
    global _store
    if db_path is None:
        return _store
    if _store is None and db_path:
        _store = SQLiteStore(db_path)
    return _store


def build_incident_from_run(
    run_id: str,
    run_meta: Dict[str, Any],
    scores: List[Dict[str, Any]],
    actions: List[Dict[str, Any]],
    action_outcomes: Optional[Dict[str, int]] = None,
) -> Optional[Dict[str, Any]]:
    """Build an incident record if run has FAIL scores or failed action outcomes. Otherwise return None."""
    has_fail = any(s.get("status") == "FAIL" for s in scores)
    outcomes = action_outcomes or {}
    has_failed_actions = outcomes.get("failed", 0) > 0
    if not has_fail and not has_failed_actions:
        return None
    severity = "high" if (has_fail or has_failed_actions) else "medium"
    fail_entities = [s.get("entity_id") for s in scores if s.get("status") == "FAIL"]
    summary_parts = []
    if has_fail:
        summary_parts.append(f"Run had FAIL health: {', '.join(fail_entities)}")
    if has_failed_actions:
        summary_parts.append(f"Action outcomes: {outcomes.get('failed', 0)} failed")
    summary = "; ".join(summary_parts) or "Incident"
    timeline = [
        {"at": run_meta.get("started_at"), "event": "run_started"},
        {"at": run_meta.get("completed_at"), "event": "run_completed", "scores": len(scores), "actions": len(actions)},
    ]
    recommended = []
    if has_fail:
        recommended.append("Review FAIL entities and baseline; consider reroute or rate limit.")
    if has_failed_actions:
        recommended.append("Check actuator connectivity and action_outcomes.jsonl; retry or rollback.")
    return {
        "incident_id": f"inc-{uuid.uuid4().hex[:12]}",
        "run_id": run_id,
        "created_at": run_meta.get("completed_at", ""),
        "severity": severity,
        "summary": summary,
        "timeline": timeline,
        "actions_taken": actions,
        "outcomes": outcomes,
        "recommended_next_steps": recommended,
        "run_meta_snapshot": run_meta,
    }


def persist_incident_if_enabled(
    db_path: Optional[Path],
    incident: Dict[str, Any],
) -> None:
    """If db_path is set, persist incident to SQLite."""
    if not db_path or not incident:
        return
    try:
        store = get_store(db_path)
        if store:
            store.save_incident(
                incident_id=incident["incident_id"],
                run_id=incident["run_id"],
                created_at=incident["created_at"],
                severity=incident["severity"],
                summary=incident["summary"],
                timeline_json=json.dumps(incident.get("timeline", []), default=str),
                actions_taken_json=json.dumps(incident.get("actions_taken", []), default=str),
                outcomes_json=json.dumps(incident.get("outcomes", {}), default=str),
                recommended_next_steps_json=json.dumps(incident.get("recommended_next_steps", []), default=str),
                run_meta_snapshot=json.dumps(incident.get("run_meta_snapshot", {}), default=str),
            )
    except Exception as exc:
        logger.warning("Incident persist failed for %s: %s", incident.get("incident_id"), exc)


def persist_run_if_enabled(
    db_path: Optional[Path],
    run_id: str,
    output_dir: str,
    run_meta: Dict[str, Any],
    scores: List[Dict[str, Any]],
    events: List[Dict[str, Any]],
    actions: List[Dict[str, Any]],
) -> None:
    """If db_path is set, persist run to SQLite."""
    if not db_path:
        return
    try:
        store = get_store(db_path)
        if store:
            store.save_run(run_id, output_dir, run_meta, scores, events, actions)
    except Exception as exc:
        logger.warning("Persistence save failed for run %s: %s", run_id, exc)
