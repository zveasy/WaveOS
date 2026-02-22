"""Unit tests for SafetyInterlock: limits, approval, rate limit, cooldown."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from waveos.actuators.safety import SafetyInterlock, safe_actuator
from waveos.models import ActionRecommendation, ActionType


def _action(
    entity_id: str = "link-1",
    action_type: ActionType = ActionType.REROUTE,
    params: dict | None = None,
) -> ActionRecommendation:
    return ActionRecommendation(
        action=action_type,
        entity_type="link",
        entity_id=entity_id,
        rationale="test",
        parameters=params or {},
    )


class TestSafetyInterlockLimits:
    def test_limits_pass_when_no_state_lookup(self) -> None:
        interlock = SafetyInterlock(max_temp_c=80.0, min_soc_pct=10.0, max_current_a=100.0)
        assert interlock.check_limits(_action("link-1")) is True

    def test_temp_over_limit_rejected(self) -> None:
        interlock = SafetyInterlock(max_temp_c=80.0, state_lookup=lambda eid: {"temperature_c": 85.0})
        assert interlock.check_limits(_action("link-1")) is False

    def test_temp_under_limit_allowed(self) -> None:
        interlock = SafetyInterlock(max_temp_c=80.0, state_lookup=lambda eid: {"temperature_c": 70.0})
        assert interlock.check_limits(_action("link-1")) is True

    def test_soc_below_min_rejected(self) -> None:
        interlock = SafetyInterlock(min_soc_pct=15.0, state_lookup=lambda eid: {"battery_soc_pct": 10.0})
        assert interlock.check_limits(_action("link-1")) is False

    def test_soc_above_min_allowed(self) -> None:
        interlock = SafetyInterlock(min_soc_pct=15.0, state_lookup=lambda eid: {"soc_pct": 20.0})
        assert interlock.check_limits(_action("link-1")) is True

    def test_current_over_limit_rejected(self) -> None:
        interlock = SafetyInterlock(max_current_a=50.0, state_lookup=lambda eid: {"current_a": 60.0})
        assert interlock.check_limits(_action("link-1")) is False

    def test_state_lookup_exception_returns_empty(self) -> None:
        interlock = SafetyInterlock(max_temp_c=80.0, state_lookup=lambda eid: (_ for _ in ()).throw(ValueError("bad")))
        assert interlock.check_limits(_action("link-1")) is True  # no state -> pass


class TestSafetyInterlockApproval:
    def test_action_not_in_approval_list_passes(self) -> None:
        interlock = SafetyInterlock(approval_required_action_types=["REROUTE"], approval_path=Path("/nonexistent"))
        # RATE_LIMIT not in list
        assert interlock.check_approval(_action("link-1", ActionType.RATE_LIMIT)) is True

    def test_approval_required_without_file_fails(self) -> None:
        interlock = SafetyInterlock(
            approval_required_action_types=["REROUTE"],
            approval_path=Path("/nonexistent/file"),
        )
        assert interlock.check_approval(_action("link-1", ActionType.REROUTE)) is False

    def test_approval_file_approved_passes(self, tmp_path: Path) -> None:
        approval_file = tmp_path / "approved"
        approval_file.write_text("approved")
        interlock = SafetyInterlock(
            approval_required_action_types=["REROUTE"],
            approval_path=approval_file,
        )
        assert interlock.check_approval(_action("link-1", ActionType.REROUTE)) is True

    def test_approval_env_var_passes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        interlock = SafetyInterlock(
            approval_required_action_types=["REROUTE"],
            approval_path=Path("/nonexistent"),
            approval_env_var="WAVEOS_ACTUATION_APPROVED",
        )
        monkeypatch.setenv("WAVEOS_ACTUATION_APPROVED", "1")
        assert interlock.check_approval(_action("link-1", ActionType.REROUTE)) is True


class TestSafetyInterlockRateAndCooldown:
    def test_rate_limit_exceeded_rejected(self) -> None:
        interlock = SafetyInterlock(max_actions_per_minute=2)
        action = _action("link-1")
        assert interlock.check_rate_and_cooldown(action) is True
        assert interlock.check_rate_and_cooldown(action) is True
        assert interlock.check_rate_and_cooldown(action) is False  # third within same "minute"

    def test_cooldown_active_rejected(self) -> None:
        interlock = SafetyInterlock(cooldown_seconds=10.0, cooldown_action_types=["REROUTE"])
        action = _action("link-1", ActionType.REROUTE)
        assert interlock.check_rate_and_cooldown(action) is True
        assert interlock.check_rate_and_cooldown(action) is False  # still in cooldown

    def test_validate_rejects_empty_entity(self) -> None:
        interlock = SafetyInterlock()
        a = _action("link-1")
        a.entity_id = ""
        assert interlock.validate(a) is False


class TestSafetyInterlockFilterActions:
    def test_filter_actions_returns_only_valid(self) -> None:
        interlock = SafetyInterlock(max_temp_c=80.0, state_lookup=lambda eid: {"temperature_c": 90.0 if eid == "link-1" else 70.0})
        actions = [_action("link-1"), _action("link-2")]
        filtered = interlock.filter_actions(actions)
        assert len(filtered) == 1
        assert filtered[0].entity_id == "link-2"


class TestSafeActuator:
    def test_safe_actuator_delegates_filtered_actions(self) -> None:
        from unittest.mock import Mock
        from waveos.actuators.base import RealActuator
        applied: list = []
        class RecordingInner(RealActuator):
            def apply(self, actions):
                applied.extend(list(actions))
        inner = RecordingInner(name="rec")
        interlock = SafetyInterlock()
        safe = safe_actuator(interlock, inner)
        actions = [_action("link-1"), _action("link-2")]
        safe.apply(iter(actions))
        assert len(applied) == 2
        assert applied[0].entity_id == "link-1"
        assert applied[1].entity_id == "link-2"

    def test_safe_actuator_validate_delegates_to_interlock(self) -> None:
        from waveos.actuators.base import RealActuator
        class DummyInner(RealActuator):
            def apply(self, actions):
                pass
        inner_real = DummyInner(name="dummy")
        interlock = SafetyInterlock(max_temp_c=80.0, state_lookup=lambda eid: {"temperature_c": 85.0 if eid == "link-1" else 70.0})
        safe = safe_actuator(interlock, inner_real)
        assert safe.validate(_action("link-1")) is False  # temp 85 > 80
        assert safe.validate(_action("link-2")) is True   # temp 70 ok
