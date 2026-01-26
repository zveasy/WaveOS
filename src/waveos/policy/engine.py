from __future__ import annotations

from typing import Iterable, List

from waveos.models import ActionRecommendation, ActionType, HealthScore, HealthStatus
from waveos.utils import span


def recommend_actions(
    scores: Iterable[HealthScore],
    run_id: str | None = None,
    feature_flags: dict[str, bool] | None = None,
) -> List[ActionRecommendation]:
    actions: List[ActionRecommendation] = []
    feature_flags = feature_flags or {}
    enable_reroute = feature_flags.get("action_reroute", True)
    enable_rate_limit = feature_flags.get("action_rate_limit", True)
    enable_qos = feature_flags.get("action_qos", True)
    enable_thermal = feature_flags.get("action_thermal", True)
    with span("policy_recommendations") as active_span:
        if run_id:
            active_span.set_attribute("waveos.run_id", run_id)
        for score in scores:
            active_span.set_attribute("waveos.entity_type", score.entity_type)
            active_span.set_attribute("waveos.entity_id", score.entity_id)
            active_span.set_attribute("waveos.status", score.status)
            active_span.set_attribute("waveos.driver_count", len(score.drivers))
            if score.status == HealthStatus.PASS:
                continue
            if score.status == HealthStatus.FAIL:
                if enable_reroute:
                    actions.append(
                        ActionRecommendation(
                            action=ActionType.REROUTE,
                            entity_type=score.entity_type,
                            entity_id=score.entity_id,
                            rationale="Link health is FAIL; recommend reroute.",
                            parameters={"priority": "high"},
                        )
                    )
                if enable_rate_limit:
                    actions.append(
                        ActionRecommendation(
                            action=ActionType.RATE_LIMIT,
                            entity_type=score.entity_type,
                            entity_id=score.entity_id,
                            rationale="Degraded link; reduce load to stabilize.",
                            parameters={"limit_pct": 60},
                        )
                    )
            if score.status == HealthStatus.WARN and enable_qos:
                actions.append(
                    ActionRecommendation(
                        action=ActionType.QOS_PRIORITIZATION,
                        entity_type=score.entity_type,
                        entity_id=score.entity_id,
                        rationale="Moderate drift detected; prioritize critical traffic.",
                        parameters={"class": "gold"},
                    )
                )
            if any("temperature" in driver for driver in score.drivers) and enable_thermal:
                actions.append(
                    ActionRecommendation(
                        action=ActionType.POWER_THERMAL_CONSTRAINT,
                        entity_type=score.entity_type,
                        entity_id=score.entity_id,
                        rationale="Temperature drift detected; apply thermal constraints.",
                        parameters={"max_temp_c": 75},
                    )
                )
        active_span.set_attribute("waveos.action_count", len(actions))
    return actions
