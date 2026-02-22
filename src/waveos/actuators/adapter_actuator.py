"""
Adapter-based real actuator: dispatch actions to device adapters (SDN REST, OCPP, Modbus)
with optional fallback to JSONL/write actuator when no adapter handles the action.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, List, Optional

from waveos.models import ActionRecommendation
from waveos.utils import get_logger, utc_now

from waveos.actuators.base import RealActuator
from waveos.actuators.adapters.base import AdapterOutcome, AdapterResult, DeviceAdapterBase


class AdapterBasedActuator(RealActuator):
    """
    Real actuator that dispatches each action to the first adapter that applies_to(action).
    If an adapter returns SUCCEEDED/NO_EFFECT/DEGRADED/UNKNOWN, the action is done.
    If all adapters return NOT_APPLICABLE, optional fallback actuator is used (e.g. write JSONL).
    """

    def __init__(
        self,
        adapters: List[DeviceAdapterBase],
        fallback: Optional[RealActuator] = None,
        output_dir: Optional[Path] = None,
        run_id: Optional[str] = None,
        timeout_seconds: float = 10.0,
        name: str = "adapter_based",
    ) -> None:
        super().__init__(name=name)
        self.adapters = adapters
        self.fallback = fallback
        self.output_dir = Path(output_dir) if output_dir else None
        self.run_id = run_id or ""
        self.timeout_seconds = timeout_seconds
        self._results: List[AdapterResult] = []

    def validate(self, action: ActionRecommendation) -> bool:
        if not action.entity_id or not action.entity_type:
            return False
        return True

    def apply(self, actions: Iterable[ActionRecommendation]) -> None:
        self._results = []
        for action in actions:
            result = self._apply_one(action)
            self._results.append(result)
            if result.outcome == AdapterOutcome.NOT_APPLICABLE and self.fallback:
                self.fallback.apply(iter([action]))

    def _apply_one(self, action: ActionRecommendation) -> AdapterResult:
        for adapter in self.adapters:
            if not adapter.applies_to(action):
                continue
            result = adapter.apply_one(action, timeout_seconds=self.timeout_seconds)
            if result.outcome != AdapterOutcome.NOT_APPLICABLE:
                self.logger.info(
                    "Adapter %s: action=%s entity=%s outcome=%s",
                    adapter.name,
                    action.action,
                    action.entity_id,
                    result.outcome.value,
                )
                return result
        return AdapterResult(action=action, outcome=AdapterOutcome.NOT_APPLICABLE, message="No adapter handled action")

    def get_last_results(self) -> List[AdapterResult]:
        """Return results from last apply (for outcome recording)."""
        return list(self._results)
