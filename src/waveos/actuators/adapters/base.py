"""Base interface for device adapters: translate ActionRecommendation to device-specific execution with outcome."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional

from waveos.models import ActionRecommendation


class AdapterOutcome(str, Enum):
    SUCCEEDED = "succeeded"
    NO_EFFECT = "no_effect"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"  # adapter does not handle this action type


@dataclass
class AdapterResult:
    """Result of applying one action via an adapter."""
    action: ActionRecommendation
    outcome: AdapterOutcome
    ack: bool = False
    message: Optional[str] = None
    actual_state: Optional[Dict[str, Any]] = None  # optional read-back for reconciliation


class DeviceAdapterBase(ABC):
    """
    Adapter that executes WaveOS actions against a specific device/protocol.
    Handles: SDN (reroute, QoS, rate limit), EV charger (OCPP: throttle, pause/resume),
    Inverter/BESS (Modbus/SunSpec: setpoints, curtailment, SOC).
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Adapter name for logging and config."""
        ...

    @property
    @abstractmethod
    def supported_action_types(self) -> List[str]:
        """Action type values this adapter handles (e.g. REROUTE, POWER_THERMAL_CONSTRAINT)."""
        ...

    def applies_to(self, action: ActionRecommendation) -> bool:
        """True if this adapter should handle this action."""
        atype = action.action.value if hasattr(action.action, "value") else str(action.action)
        return atype in self.supported_action_types

    @abstractmethod
    def apply_one(self, action: ActionRecommendation, timeout_seconds: float = 10.0) -> AdapterResult:
        """
        Execute a single action. Implement ACK/timeout/retry inside if needed.
        Return AdapterResult with outcome and optional actual_state for reconciliation.
        """
        ...

    def apply(self, actions: Iterable[ActionRecommendation], timeout_seconds: float = 10.0) -> List[AdapterResult]:
        """Apply all actions that this adapter handles; return list of results."""
        results: List[AdapterResult] = []
        for action in actions:
            if not self.applies_to(action):
                continue
            results.append(self.apply_one(action, timeout_seconds=timeout_seconds))
        return results
