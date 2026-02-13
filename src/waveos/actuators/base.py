from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable

from waveos.models import ActionRecommendation
from waveos.utils import get_logger


class RealActuator(ABC):
    """Base for production actuators. Implement apply(); override validate() to gate actions.
    See docs/ACTUATOR_INTEGRATION_KIT.md for integration steps.
    """

    def __init__(self, name: str = "real") -> None:
        self.name = name
        self.logger = get_logger(f"waveos.actuator.{name}")

    def validate(self, action: ActionRecommendation) -> bool:
        """Return True if this action is allowed (safety envelope). Override to enforce limits."""
        return True

    @abstractmethod
    def apply(self, actions: Iterable[ActionRecommendation]) -> None:
        """Execute actions on real hardware. Only receives actions that passed validate()."""
        pass

    def apply_safe(self, actions: Iterable[ActionRecommendation]) -> None:
        """Apply only actions that pass validate(), then call apply()."""
        allowed = [a for a in actions if self.validate(a)]
        if allowed != list(actions):
            self.logger.warning("Filtered %s actions by safety envelope", len(list(actions)) - len(allowed))
        self.apply(allowed)


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
