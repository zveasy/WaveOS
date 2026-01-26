from __future__ import annotations

from typing import Iterable, List

from waveos.models import ActionRecommendation, ActionType, HealthScore, HealthStatus


def recommend_actions(scores: Iterable[HealthScore]) -> List[ActionRecommendation]:
    actions: List[ActionRecommendation] = []
    for score in scores:
        if score.status == HealthStatus.PASS:
            continue
        if score.status == HealthStatus.FAIL:
            actions.append(
                ActionRecommendation(
                    action=ActionType.REROUTE,
                    entity_type=score.entity_type,
                    entity_id=score.entity_id,
                    rationale="Link health is FAIL; recommend reroute.",
                    parameters={"priority": "high"},
                )
            )
            actions.append(
                ActionRecommendation(
                    action=ActionType.RATE_LIMIT,
                    entity_type=score.entity_type,
                    entity_id=score.entity_id,
                    rationale="Degraded link; reduce load to stabilize.",
                    parameters={"limit_pct": 60},
                )
            )
        if score.status == HealthStatus.WARN:
            actions.append(
                ActionRecommendation(
                    action=ActionType.QOS_PRIORITIZATION,
                    entity_type=score.entity_type,
                    entity_id=score.entity_id,
                    rationale="Moderate drift detected; prioritize critical traffic.",
                    parameters={"class": "gold"},
                )
            )
        if any("temperature" in driver for driver in score.drivers):
            actions.append(
                ActionRecommendation(
                    action=ActionType.POWER_THERMAL_CONSTRAINT,
                    entity_type=score.entity_type,
                    entity_id=score.entity_id,
                    rationale="Temperature drift detected; apply thermal constraints.",
                    parameters={"max_temp_c": 75},
                )
            )
    return actions
