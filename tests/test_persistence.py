"""Tests for persistence layer: SQLite store for runs, events, actions, incidents."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from waveos.persistence.store import SQLiteStore, get_store, persist_run_if_enabled


def test_sqlite_store_save_and_get_recent(tmp_path: Path) -> None:
    db = tmp_path / "waveos.db"
    store = SQLiteStore(db)
    store.save_run(
        run_id="run-1",
        output_dir="/out",
        run_meta={
            "run_id": "run-1",
            "started_at": "2025-01-01T00:00:00Z",
            "completed_at": "2025-01-01T00:05:00Z",
            "sample_count": 10,
            "score_count": 2,
            "event_count": 1,
            "action_count": 1,
        },
        scores=[
            {"entity_type": "link", "entity_id": "link-1", "score": 85.0, "status": "PASS", "drivers": []},
        ],
        events=[{"level": "INFO", "message": "test event"}],
        actions=[{"action": "REROUTE", "entity_type": "link", "entity_id": "link-1"}],
    )
    recent = store.get_recent_runs(limit=5)
    assert len(recent) == 1
    assert recent[0]["run_id"] == "run-1"
    assert recent[0]["sample_count"] == 10


def test_sqlite_store_get_run_meta(tmp_path: Path) -> None:
    db = tmp_path / "waveos.db"
    store = SQLiteStore(db)
    run_meta = {"run_id": "run-2", "waveos_version": "0.1.0", "action_outcomes": {"succeeded": 2}}
    store.save_run("run-2", "/out", run_meta, [], [], [])
    meta = store.get_run_meta("run-2")
    assert meta is not None
    assert meta["run_id"] == "run-2"
    assert meta.get("action_outcomes") == {"succeeded": 2}


def test_persist_run_if_enabled_no_path() -> None:
    persist_run_if_enabled(None, "run-x", "/out", {}, [], [], [])
    # No exception; no-op when path is None


def test_build_incident_from_run_no_incident() -> None:
    from waveos.persistence.store import build_incident_from_run
    incident = build_incident_from_run(
        "run-1",
        {"completed_at": "2025-01-01"},
        [{"status": "PASS"}, {"status": "WARN"}],
        [],
        action_outcomes={"succeeded": 2},
    )
    assert incident is None


def test_build_incident_from_run_has_fail() -> None:
    from waveos.persistence.store import build_incident_from_run
    incident = build_incident_from_run(
        "run-2",
        {"completed_at": "2025-01-01", "started_at": "2025-01-01"},
        [{"entity_id": "link-1", "status": "FAIL"}, {"status": "PASS"}],
        [{"action": "REROUTE", "entity_id": "link-1"}],
        action_outcomes=None,
    )
    assert incident is not None
    assert incident["run_id"] == "run-2"
    assert incident["severity"] == "high"
    assert "FAIL" in incident["summary"]
    assert "inc-" in incident["incident_id"]


def test_save_incident(tmp_path: Path) -> None:
    from waveos.persistence.store import SQLiteStore, build_incident_from_run
    db = tmp_path / "i.db"
    store = SQLiteStore(db)
    incident = build_incident_from_run(
        "run-i",
        {"completed_at": "2025-01-01"},
        [{"entity_id": "link-1", "status": "FAIL"}],
        [],
        action_outcomes={"failed": 1},
    )
    assert incident is not None
    store.save_incident(
        incident["incident_id"],
        incident["run_id"],
        incident["created_at"],
        incident["severity"],
        incident["summary"],
        json.dumps(incident.get("timeline", [])),
        json.dumps(incident.get("actions_taken", [])),
        json.dumps(incident.get("outcomes", {})),
        json.dumps(incident.get("recommended_next_steps", [])),
        json.dumps(incident.get("run_meta_snapshot", {})),
    )
    recent = store.get_recent_incidents(5)
    assert len(recent) == 1
    assert recent[0]["run_id"] == "run-i"
    assert recent[0]["severity"] == "high"


def test_persist_run_if_enabled_with_path(tmp_path: Path) -> None:
    db = tmp_path / "p.db"
    persist_run_if_enabled(
        db,
        run_id="run-p",
        output_dir="/out",
        run_meta={"run_id": "run-p", "started_at": "2025-01-01", "completed_at": "2025-01-01"},
        scores=[],
        events=[],
        actions=[],
    )
    store = get_store(db)
    assert store is not None
    recent = store.get_recent_runs(1)
    assert len(recent) == 1
    assert recent[0]["run_id"] == "run-p"
