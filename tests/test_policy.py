from datetime import datetime, timezone

from waveos.models import ActionType, HealthScore, HealthStatus
from waveos.policy import recommend_actions


def test_policy_recommends_actions_for_fail_and_temp() -> None:
    score = HealthScore(
        entity_type="link",
        entity_id="link-1",
        score=40.0,
        status=HealthStatus.FAIL,
        drivers=["temperature_drift"],
        window_start=datetime(2025, 1, 1, tzinfo=timezone.utc),
        window_end=datetime(2025, 1, 1, 0, 5, tzinfo=timezone.utc),
    )
    actions = recommend_actions([score])
    action_types = {action.action for action in actions}
    assert ActionType.REROUTE in action_types
    assert ActionType.RATE_LIMIT in action_types
    assert ActionType.POWER_THERMAL_CONSTRAINT in action_types


def test_policy_respects_feature_flags() -> None:
    score = HealthScore(
        entity_type="link",
        entity_id="link-2",
        score=40.0,
        status=HealthStatus.FAIL,
        drivers=["temperature_drift"],
        window_start="2025-01-01T00:00:00Z",
        window_end="2025-01-01T00:05:00Z",
    )
    actions = recommend_actions([score], feature_flags={"action_reroute": False, "action_rate_limit": False})
    action_types = {action.action for action in actions}
    assert ActionType.REROUTE not in action_types
    assert ActionType.RATE_LIMIT not in action_types
