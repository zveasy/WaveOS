"""
Safety interlocks for actuation: hard limits, approval workflow, rate limiting and cooldown.

Call before apply to:
- Enforce hard limits (max temp, min SOC, max current) against current or last-known state
- Require approval for high-risk action types (two-person rule)
- Rate limit and cooldown to avoid repeated actuations
"""

from __future__ import annotations

import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

from waveos.models import ActionRecommendation, ActionType
from waveos.utils import get_logger


class SafetyInterlock:
    """
    Validates actions against hard limits, approval, and rate/cooldown before apply.
    """

    def __init__(
        self,
        max_temp_c: Optional[float] = None,
        min_soc_pct: Optional[float] = None,
        max_current_a: Optional[float] = None,
        approval_required_action_types: Optional[List[str]] = None,
        approval_path: Optional[Path] = None,
        approval_env_var: str = "WAVEOS_ACTUATION_APPROVED",
        max_actions_per_minute: Optional[int] = None,
        cooldown_seconds: float = 0.0,
        cooldown_action_types: Optional[List[str]] = None,
        state_lookup: Optional[Any] = None,
    ) -> None:
        self.max_temp_c = max_temp_c
        self.min_soc_pct = min_soc_pct
        self.max_current_a = max_current_a
        self.approval_required = set((approval_required_action_types or []))
        self.approval_path = approval_path
        self.approval_env_var = approval_env_var
        self.max_actions_per_minute = max_actions_per_minute
        self.cooldown_seconds = cooldown_seconds
        self.cooldown_action_types = set(cooldown_action_types or [])
        self.state_lookup = state_lookup  # callable (entity_id) -> dict of metrics or None
        self.logger = get_logger("waveos.actuators.safety")
        self._action_times: Dict[str, List[float]] = defaultdict(list)
        self._last_action_time: Dict[str, float] = {}  # key by entity_id or "global"

    def _action_type_str(self, action: ActionRecommendation) -> str:
        return action.action.value if hasattr(action.action, "value") else str(action.action)

    def _get_state(self, entity_id: str) -> Dict[str, Any]:
        if self.state_lookup is None:
            return {}
        try:
            out = self.state_lookup(entity_id)
            return out if isinstance(out, dict) else {}
        except Exception:
            return {}

    def check_limits(self, action: ActionRecommendation) -> bool:
        """Return False if action would violate hard limits given current/last state."""
        state = self._get_state(action.entity_id)
        if self.max_temp_c is not None:
            temp = state.get("temperature_c") or state.get("temp_c")
            if temp is not None and float(temp) > self.max_temp_c:
                self.logger.warning("Safety: temperature %.1f exceeds max %.1f", temp, self.max_temp_c)
                return False
        if self.min_soc_pct is not None:
            soc = state.get("battery_soc_pct") or state.get("soc_pct")
            if soc is not None and float(soc) < self.min_soc_pct:
                self.logger.warning("Safety: SOC %.1f below min %.1f", soc, self.min_soc_pct)
                return False
        if self.max_current_a is not None:
            cur = state.get("current_a")
            if cur is not None and float(cur) > self.max_current_a:
                self.logger.warning("Safety: current %.1f exceeds max %.1f", cur, self.max_current_a)
                return False
        return True

    def check_approval(self, action: ActionRecommendation) -> bool:
        """Return False if action requires approval and approval not present."""
        atype = self._action_type_str(action)
        if atype not in self.approval_required:
            return True
        import os
        if os.environ.get(self.approval_env_var, "").strip().lower() in ("1", "true", "yes", "on"):
            return True
        if self.approval_path and self.approval_path.exists():
            try:
                return self.approval_path.read_text(encoding="utf-8").strip().lower() == "approved"
            except OSError:
                pass
        self.logger.warning("Safety: action %s requires approval (set %s or approval file)", atype, self.approval_env_var)
        return False

    def check_rate_and_cooldown(self, action: ActionRecommendation) -> bool:
        """Return False if rate limit or cooldown would be violated."""
        now = time.time()
        atype = self._action_type_str(action)
        key = f"{action.entity_type}:{action.entity_id}"
        # Cooldown per entity (or global for cooldown_action_types)
        if atype in self.cooldown_action_types and self.cooldown_seconds > 0:
            last = self._last_action_time.get(key, 0)
            if now - last < self.cooldown_seconds:
                self.logger.warning("Safety: cooldown active for %s (%.0fs remaining)", key, self.cooldown_seconds - (now - last))
                return False
        # Global or per-entity rate limit
        if self.max_actions_per_minute is not None:
            self._action_times[key].append(now)
            cutoff = now - 60.0
            self._action_times[key] = [t for t in self._action_times[key] if t > cutoff]
            if len(self._action_times[key]) > self.max_actions_per_minute:
                self.logger.warning("Safety: rate limit exceeded for %s (%s/min)", key, self.max_actions_per_minute)
                return False
        self._last_action_time[key] = now
        return True

    def validate(self, action: ActionRecommendation) -> bool:
        """Run all checks. Return True only if action is allowed."""
        if not action.entity_id or not action.entity_type:
            return False
        if not self.check_limits(action):
            return False
        if not self.check_approval(action):
            return False
        if not self.check_rate_and_cooldown(action):
            return False
        return True

    def filter_actions(self, actions: Iterable[ActionRecommendation]) -> List[ActionRecommendation]:
        """Return only actions that pass all safety checks."""
        return [a for a in actions if self.validate(a)]


def safe_actuator(interlock: SafetyInterlock, inner: "RealActuator") -> "RealActuator":
    """Return a RealActuator that runs SafetyInterlock before delegating to inner."""
    from waveos.actuators.base import RealActuator
    from waveos.models import ActionRecommendation
    from typing import Iterable

    class SafeActuator(RealActuator):
        def __init__(self, interlock: SafetyInterlock, inner: RealActuator):
            super().__init__(name=f"safe_{inner.name}")
            self._interlock = interlock
            self._inner = inner

        def validate(self, action: ActionRecommendation) -> bool:
            return self._interlock.validate(action)

        def apply(self, actions: Iterable[ActionRecommendation]) -> None:
            allowed = self._interlock.filter_actions(actions)
            if allowed:
                self._inner.apply(iter(allowed))

    return SafeActuator(interlock, inner)
