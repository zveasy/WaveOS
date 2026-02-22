"""Tests for change log (Compliance Phase 3)."""

import tempfile
from pathlib import Path

from waveos.change_log import append_change_log, get_recent_changes


def test_append_and_get_recent_changes() -> None:
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
        path = Path(f.name)
    try:
        append_change_log(path, "install", bundle_id="b1")
        append_change_log(path, "promote", bundle_id="b1", approver="ops")
        entries = get_recent_changes(path, limit=10)
        assert len(entries) == 2
        assert entries[0]["event"] == "promote"
        assert entries[0]["bundle_id"] == "b1"
        assert entries[0]["approver"] == "ops"
        assert entries[1]["event"] == "install"
    finally:
        path.unlink(missing_ok=True)
