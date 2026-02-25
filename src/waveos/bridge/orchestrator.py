"""Bridge orchestrator — safe startup ordering and mode transitions for legacy+new systems."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.bridge.orchestrator")


class BridgeMode(str, Enum):
    MIRROR = "mirror"      # both legacy and new run; new mirrors legacy
    CANARY = "canary"      # partial traffic to new system
    CUTOVER = "cutover"    # full cutover to new system


class BridgeState(str, Enum):
    IDLE = "idle"
    STARTING_LEGACY = "starting_legacy"
    STARTING_ADAPTER = "starting_adapter"
    STARTING_NEW = "starting_new"
    VALIDATING = "validating"
    ROUTING = "routing"
    ACTIVE = "active"
    FAILED = "failed"


@dataclass
class BridgeConfig:
    mode: BridgeMode = BridgeMode.MIRROR
    legacy_service: str = ""
    adapter_service: str = ""
    new_service: str = ""
    routing_rules: Dict[str, Any] = field(default_factory=dict)
    validation_checks: List[str] = field(default_factory=list)
    canary_percent: int = 10
    health_threshold: float = 70.0

    def to_dict(self) -> dict:
        return {
            "mode": self.mode.value,
            "legacy_service": self.legacy_service,
            "adapter_service": self.adapter_service,
            "new_service": self.new_service,
            "routing_rules": self.routing_rules,
            "validation_checks": self.validation_checks,
            "canary_percent": self.canary_percent,
            "health_threshold": self.health_threshold,
        }

    @classmethod
    def from_dict(cls, d: dict) -> BridgeConfig:
        return cls(
            mode=BridgeMode(d.get("mode", "mirror")),
            legacy_service=d.get("legacy_service", ""),
            adapter_service=d.get("adapter_service", ""),
            new_service=d.get("new_service", ""),
            routing_rules=d.get("routing_rules", {}),
            validation_checks=d.get("validation_checks", []),
            canary_percent=d.get("canary_percent", 10),
            health_threshold=d.get("health_threshold", 70.0),
        )


class BridgeOrchestrator:
    """Orchestrates legacy-to-new bridge transitions with safe ordering."""

    def __init__(self, config: BridgeConfig) -> None:
        self.config = config
        self._state = BridgeState.IDLE
        self._log: List[Dict[str, Any]] = []

    @property
    def state(self) -> BridgeState:
        return self._state

    @property
    def log(self) -> List[Dict[str, Any]]:
        return list(self._log)

    def _record(self, event: str, details: Optional[Dict[str, Any]] = None) -> None:
        entry = {"timestamp": utc_now().isoformat(), "event": event, "state": self._state.value, **(details or {})}
        self._log.append(entry)
        logger.info("Bridge %s: %s", event, self._state.value)

    def get_startup_sequence(self) -> List[Dict[str, str]]:
        """Return ordered startup sequence: legacy -> adapter -> new -> routing switch."""
        seq: List[Dict[str, str]] = []
        if self.config.legacy_service:
            seq.append({"step": "start_legacy", "service": self.config.legacy_service})
        if self.config.adapter_service:
            seq.append({"step": "start_adapter", "service": self.config.adapter_service})
        if self.config.new_service:
            seq.append({"step": "start_new", "service": self.config.new_service})
        seq.append({"step": "validate", "service": "health_gates"})
        seq.append({"step": "route", "service": f"mode={self.config.mode.value}"})
        return seq

    def execute_startup(self, health_check_fn=None) -> Dict[str, Any]:
        """Execute the bridge startup sequence.
        health_check_fn: optional callable() -> float (health score 0-100)
        """
        results: List[Dict[str, Any]] = []

        # 1) Start legacy
        if self.config.legacy_service:
            self._state = BridgeState.STARTING_LEGACY
            self._record("start_legacy", {"service": self.config.legacy_service})
            results.append({"step": "start_legacy", "ok": True, "service": self.config.legacy_service})

        # 2) Start adapter
        if self.config.adapter_service:
            self._state = BridgeState.STARTING_ADAPTER
            self._record("start_adapter", {"service": self.config.adapter_service})
            results.append({"step": "start_adapter", "ok": True, "service": self.config.adapter_service})

        # 3) Start new module
        if self.config.new_service:
            self._state = BridgeState.STARTING_NEW
            self._record("start_new", {"service": self.config.new_service})
            results.append({"step": "start_new", "ok": True, "service": self.config.new_service})

        # 4) Validate (health gates)
        self._state = BridgeState.VALIDATING
        health_ok = True
        health_score = 100.0
        if health_check_fn:
            try:
                health_score = health_check_fn()
                health_ok = health_score >= self.config.health_threshold
            except Exception as exc:
                health_ok = False
                health_score = 0.0
                logger.warning("Bridge health check failed: %s", exc)
        self._record("validate", {"health_ok": health_ok, "health_score": health_score})
        results.append({"step": "validate", "ok": health_ok, "health_score": health_score})

        if not health_ok:
            self._state = BridgeState.FAILED
            self._record("failed", {"reason": "Health gate not met"})
            return {"ok": False, "state": self._state.value, "steps": results}

        # 5) Apply routing
        self._state = BridgeState.ROUTING
        self._record("route", {"mode": self.config.mode.value, "canary_percent": self.config.canary_percent})
        results.append({"step": "route", "ok": True, "mode": self.config.mode.value})

        self._state = BridgeState.ACTIVE
        self._record("active")
        return {"ok": True, "state": self._state.value, "mode": self.config.mode.value, "steps": results}

    def transition_mode(self, new_mode: BridgeMode, health_check_fn=None) -> Dict[str, Any]:
        """Transition from current mode to a new mode (e.g. mirror -> canary -> cutover)."""
        if health_check_fn:
            score = health_check_fn()
            if score < self.config.health_threshold:
                self._record("mode_transition_blocked", {"target": new_mode.value, "health_score": score})
                return {"ok": False, "reason": f"Health score {score} below threshold {self.config.health_threshold}"}
        old_mode = self.config.mode
        self.config.mode = new_mode
        self._record("mode_transition", {"from": old_mode.value, "to": new_mode.value})
        return {"ok": True, "from": old_mode.value, "to": new_mode.value}

    def save_log(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self._log, indent=2) + "\n", encoding="utf-8")
