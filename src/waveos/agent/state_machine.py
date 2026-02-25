"""Agent state machine for deployment lifecycle."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.agent.state_machine")


class AgentState(str, Enum):
    IDLE = "IDLE"
    CHECK_UPDATE = "CHECK_UPDATE"
    DOWNLOAD = "DOWNLOAD"
    VERIFY = "VERIFY"
    PREFLIGHT = "PREFLIGHT"
    INSTALL = "INSTALL"
    ACTIVATE = "ACTIVATE"
    MONITOR = "MONITOR"
    ROLLBACK = "ROLLBACK"
    QUARANTINE = "QUARANTINE"


VALID_TRANSITIONS: Dict[AgentState, List[AgentState]] = {
    AgentState.IDLE: [AgentState.CHECK_UPDATE, AgentState.MONITOR],
    AgentState.CHECK_UPDATE: [AgentState.DOWNLOAD, AgentState.IDLE],
    AgentState.DOWNLOAD: [AgentState.VERIFY, AgentState.IDLE, AgentState.QUARANTINE],
    AgentState.VERIFY: [AgentState.PREFLIGHT, AgentState.QUARANTINE, AgentState.IDLE],
    AgentState.PREFLIGHT: [AgentState.INSTALL, AgentState.IDLE, AgentState.QUARANTINE],
    AgentState.INSTALL: [AgentState.ACTIVATE, AgentState.ROLLBACK, AgentState.QUARANTINE],
    AgentState.ACTIVATE: [AgentState.MONITOR, AgentState.ROLLBACK, AgentState.QUARANTINE],
    AgentState.MONITOR: [AgentState.IDLE, AgentState.ROLLBACK, AgentState.CHECK_UPDATE, AgentState.QUARANTINE],
    AgentState.ROLLBACK: [AgentState.IDLE, AgentState.QUARANTINE],
    AgentState.QUARANTINE: [AgentState.IDLE],
}


@dataclass
class AgentEvent:
    """Structured event in the agent event log."""
    timestamp: str
    from_state: str
    to_state: str
    reason: str = ""
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "from_state": self.from_state,
            "to_state": self.to_state,
            "reason": self.reason,
            "details": self.details,
        }


class AgentStateMachine:
    """State machine for the WaveOS agent lifecycle."""

    def __init__(self, initial_state: AgentState = AgentState.IDLE) -> None:
        self._state = initial_state
        self._history: List[AgentEvent] = []

    @property
    def state(self) -> AgentState:
        return self._state

    @property
    def history(self) -> List[AgentEvent]:
        return list(self._history)

    def can_transition(self, target: AgentState) -> bool:
        return target in VALID_TRANSITIONS.get(self._state, [])

    def transition(self, target: AgentState, reason: str = "", details: Optional[Dict[str, Any]] = None) -> bool:
        if not self.can_transition(target):
            logger.warning("Invalid transition %s -> %s", self._state.value, target.value)
            return False
        event = AgentEvent(
            timestamp=utc_now().isoformat(),
            from_state=self._state.value,
            to_state=target.value,
            reason=reason,
            details=details or {},
        )
        self._history.append(event)
        logger.info("Agent transition %s -> %s: %s", self._state.value, target.value, reason)
        self._state = target
        return True

    def force_state(self, target: AgentState, reason: str = "") -> None:
        """Force a state change (bypass validation). Use for recovery only."""
        event = AgentEvent(
            timestamp=utc_now().isoformat(),
            from_state=self._state.value,
            to_state=target.value,
            reason=f"FORCED: {reason}",
        )
        self._history.append(event)
        self._state = target

    def save_state(self, path: Path) -> None:
        """Persist current state and history."""
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "state": self._state.value,
            "history": [e.to_dict() for e in self._history[-100:]],
        }
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    @classmethod
    def load_state(cls, path: Path) -> AgentStateMachine:
        """Load state machine from persisted state."""
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            sm = cls(AgentState(data.get("state", "IDLE")))
            for e in data.get("history", []):
                sm._history.append(AgentEvent(
                    timestamp=e.get("timestamp", ""),
                    from_state=e.get("from_state", ""),
                    to_state=e.get("to_state", ""),
                    reason=e.get("reason", ""),
                    details=e.get("details", {}),
                ))
            return sm
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("Failed to load agent state: %s", exc)
            return cls()
