"""Tests for SRE runbooks."""

from __future__ import annotations

import pytest

from waveos.runbooks import get_runbook, list_runbooks, run_runbook


def test_list_runbooks() -> None:
    runbooks = list_runbooks()
    assert len(runbooks) >= 3
    ids = {rb.id for rb in runbooks}
    assert "telemetry_stale" in ids
    assert "actuator_down" in ids
    assert "scoring_spike" in ids


def test_get_runbook() -> None:
    rb = get_runbook("actuator_down")
    assert rb is not None
    assert rb.title == "Actuator unreachable or failing"
    assert len(rb.steps) >= 1
    assert get_runbook("nonexistent") is None


def test_run_runbook() -> None:
    result = run_runbook("telemetry_stale")
    assert result["ok"] is True
    assert result["runbook_id"] == "telemetry_stale"
    assert "steps" in result
    assert len(result["steps"]) >= 1


def test_run_runbook_not_found() -> None:
    result = run_runbook("nonexistent")
    assert result["ok"] is False
    assert "not found" in result.get("error", "")
