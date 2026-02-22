"""Unit tests for ActuationReliabilityLayer: idempotency, retry, outcome file."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import Mock

import pytest

from waveos.actuators.reliability import (
    ActionOutcome,
    ActuationReliabilityLayer,
    IdempotencyStore,
    _idempotency_key,
)
from waveos.models import ActionRecommendation, ActionType


def _action(entity_id: str = "link-1", action_type: ActionType = ActionType.REROUTE, params: dict | None = None) -> ActionRecommendation:
    return ActionRecommendation(
        action=action_type,
        entity_type="link",
        entity_id=entity_id,
        rationale="test",
        parameters=params or {},
    )


class TestIdempotencyKey:
    def test_same_action_same_key(self) -> None:
        a = _action("link-1", ActionType.REROUTE, {"p": 1})
        b = _action("link-1", ActionType.REROUTE, {"p": 1})
        assert _idempotency_key(a) == _idempotency_key(b)

    def test_different_entity_different_key(self) -> None:
        a = _action("link-1")
        b = _action("link-2")
        assert _idempotency_key(a) != _idempotency_key(b)

    def test_different_params_different_key(self) -> None:
        a = _action("link-1", ActionType.RATE_LIMIT, {"limit_pct": 50})
        b = _action("link-1", ActionType.RATE_LIMIT, {"limit_pct": 80})
        assert _idempotency_key(a) != _idempotency_key(b)


class TestIdempotencyStore:
    def test_seen_returns_false_before_add(self) -> None:
        store = IdempotencyStore(ttl_seconds=60.0)
        assert store.seen("key1") is False

    def test_seen_returns_true_after_add(self) -> None:
        store = IdempotencyStore(ttl_seconds=60.0)
        now = time.time()
        store.add("key1", now=now)
        assert store.seen("key1", now=now + 1) is True

    def test_seen_returns_false_after_ttl(self) -> None:
        store = IdempotencyStore(ttl_seconds=0.5)
        now = time.time()
        store.add("key1", now=now)
        assert store.seen("key1", now=now + 1) is False


class TestActuationReliabilityLayer:
    def test_idempotency_skips_duplicate_and_records_skipped(self, tmp_path: Path) -> None:
        outcomes_path = tmp_path / "outcomes.jsonl"
        inner = Mock()
        inner.validate = Mock(return_value=True)
        layer = ActuationReliabilityLayer(
            inner=inner,
            run_id="run-1",
            timeout_seconds=2.0,
            retry_count=1,
            idempotency_ttl_seconds=300.0,
            outcomes_path=outcomes_path,
        )
        action = _action("link-1")
        actions = [action, action]  # same action twice
        layer.apply(iter(actions))
        # First action applied (inner.apply once), second skipped by idempotency
        assert inner.apply.call_count == 1
        assert outcomes_path.exists()
        lines = outcomes_path.read_text().strip().split("\n")
        assert len(lines) == 2
        import json
        rec0 = json.loads(lines[0])
        rec1 = json.loads(lines[1])
        assert rec0["outcome"] == "succeeded"
        assert rec1["outcome"] == "skipped_idempotent"

    def test_retry_on_failure_then_succeed(self, tmp_path: Path) -> None:
        outcomes_path = tmp_path / "outcomes.jsonl"
        inner = Mock()
        inner.validate = Mock(return_value=True)
        call_count = 0
        def apply_side_effect(actions):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise TimeoutError("timeout")
            # else succeed on 3rd attempt
        inner.apply = Mock(side_effect=apply_side_effect)
        layer = ActuationReliabilityLayer(
            inner=inner,
            run_id="run-1",
            timeout_seconds=5.0,
            retry_count=2,  # 3 total attempts: 1 + 2 retries
            idempotency_ttl_seconds=300.0,
            outcomes_path=outcomes_path,
        )
        action = _action("link-1")
        layer.apply(iter([action]))
        assert call_count == 3  # initial + 2 retries, then success
        lines = outcomes_path.read_text().strip().split("\n")
        assert len(lines) == 1
        rec = __import__("json").loads(lines[0])
        assert rec["outcome"] == "succeeded"
        assert rec["attempt_count"] == 3

    def test_all_retries_fail_records_failed(self, tmp_path: Path) -> None:
        outcomes_path = tmp_path / "outcomes.jsonl"
        inner = Mock()
        inner.validate = Mock(return_value=True)
        inner.apply = Mock(side_effect=RuntimeError("device unreachable"))
        layer = ActuationReliabilityLayer(
            inner=inner,
            run_id="run-1",
            timeout_seconds=2.0,
            retry_count=1,
            idempotency_ttl_seconds=300.0,
            outcomes_path=outcomes_path,
        )
        action = _action("link-1")
        layer.apply(iter([action]))
        lines = outcomes_path.read_text().strip().split("\n")
        assert len(lines) == 1
        rec = __import__("json").loads(lines[0])
        assert rec["outcome"] == "failed"
        assert rec["attempt_count"] >= 1

    def test_validate_delegates_to_inner(self) -> None:
        inner = Mock()
        inner.validate = Mock(return_value=False)
        layer = ActuationReliabilityLayer(inner=inner)
        action = _action("link-1")
        assert layer.validate(action) is False
        inner.validate.assert_called_once_with(action)

    def test_apply_safe_filters_by_validate(self, tmp_path: Path) -> None:
        inner = Mock()
        inner.validate = Mock(side_effect=lambda a: a.entity_id == "link-1")
        inner.apply = Mock()
        layer = ActuationReliabilityLayer(
            inner=inner,
            outcomes_path=tmp_path / "out.jsonl",
        )
        actions = [_action("link-1"), _action("link-2")]
        layer.apply_safe(iter(actions))
        inner.apply.assert_called_once()
        # Only link-1 should be passed
        call_args = inner.apply.call_args[0][0]
        applied = list(call_args)
        assert len(applied) == 1
        assert applied[0].entity_id == "link-1"
