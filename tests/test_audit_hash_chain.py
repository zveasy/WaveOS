"""Tests for hash-chained audit (tamper evidence)."""

from __future__ import annotations

from pathlib import Path

import json

import pytest

from waveos.utils.audit import _audit_hash, _read_last_audit_hash, append_audit


def test_audit_hash_deterministic() -> None:
    h1 = _audit_hash("", {"a": 1})
    h2 = _audit_hash("", {"a": 1})
    assert h1 == h2


def test_audit_hash_chains() -> None:
    h0 = ""
    h1 = _audit_hash(h0, {"event": "first"})
    h2 = _audit_hash(h1, {"event": "second"})
    assert h1 != h2
    assert len(h1) == 64 and len(h2) == 64


def test_append_audit_hash_chain(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    append_audit(path, {"ts": "2025-01-01", "action": "run"}, hash_chain=True)
    lines = path.read_text().strip().split("\n")
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert "prev_hash" in rec
    assert "hash" in rec
    assert "payload" in rec
    assert rec["payload"]["action"] == "run"
    assert rec["prev_hash"] == ""
    assert len(rec["hash"]) == 64
    last_hash_file = tmp_path / "audit.jsonl.last_hash"
    assert last_hash_file.exists()
    assert last_hash_file.read_text().strip() == rec["hash"]

    append_audit(path, {"ts": "2025-01-02", "action": "run2"}, hash_chain=True)
    lines2 = path.read_text().strip().split("\n")
    assert len(lines2) == 2
    rec2 = json.loads(lines2[1])
    assert rec2["prev_hash"] == rec["hash"]
    assert rec2["hash"] != rec["hash"]
