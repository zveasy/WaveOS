from __future__ import annotations

from typing import Iterable

from waveos.models import ActionRecommendation
from waveos.utils import get_logger


class NoopActuator:
    def apply(self, actions: Iterable[ActionRecommendation]) -> None:
        return None


class MockActuator:
    def __init__(self) -> None:
        self.logger = get_logger("waveos.actuator")

    def apply(self, actions: Iterable[ActionRecommendation]) -> None:
        for action in actions:
            self.logger.info(
                "Actuator action=%s entity=%s/%s rationale=%s",
                action.action,
                action.entity_type,
                action.entity_id,
                action.rationale,
            )
