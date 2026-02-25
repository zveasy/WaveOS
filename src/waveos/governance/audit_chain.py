"""Immutable governance audit chain — tamper-evident log of all governance actions."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.governance.audit_chain")


@dataclass
class GovernanceEvent:
    """A governance event in the immutable audit chain."""
    event_type: str  # publish | promote | rollback | quarantine | approve | revoke
    actor: str
    bundle_id: str = ""
    channel: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""
    previous_hash: str = ""

    def to_dict(self) -> dict:
        return {"event_type": self.event_type, "actor": self.actor, "bundle_id": self.bundle_id,
                "channel": self.channel, "details": self.details,
                "timestamp": self.timestamp or utc_now().isoformat(),
                "previous_hash": self.previous_hash}

    @classmethod
    def from_dict(cls, d: dict) -> GovernanceEvent:
        return cls(**{k: d[k] for k in d if k in cls.__dataclass_fields__})

    def event_hash(self) -> str:
        canonical = json.dumps(self.to_dict(), sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode()).hexdigest()


class GovernanceAuditChain:
    """Tamper-evident governance audit chain."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self._events: List[GovernanceEvent] = []
        self._path = path
        if path and path.exists():
            self._load()

    def _load(self) -> None:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            self._events = [GovernanceEvent.from_dict(e) for e in data]
        except (json.JSONDecodeError, OSError):
            pass

    def record(self, event_type: str, actor: str, bundle_id: str = "", channel: str = "",
               details: Optional[Dict[str, Any]] = None) -> GovernanceEvent:
        previous_hash = self._events[-1].event_hash() if self._events else ""
        event = GovernanceEvent(event_type=event_type, actor=actor, bundle_id=bundle_id,
                                channel=channel, details=details or {},
                                timestamp=utc_now().isoformat(), previous_hash=previous_hash)
        self._events.append(event)
        if self._path:
            self.save()
        return event

    def verify(self) -> Tuple[bool, List[str]]:
        errors: List[str] = []
        for i, event in enumerate(self._events):
            if i == 0:
                if event.previous_hash:
                    errors.append("First event has non-empty previous_hash")
            else:
                expected = self._events[i - 1].event_hash()
                if event.previous_hash != expected:
                    errors.append(f"Chain break at index {i}")
        return len(errors) == 0, errors

    def get_events(self, event_type: Optional[str] = None, bundle_id: Optional[str] = None) -> List[GovernanceEvent]:
        events = self._events
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        if bundle_id:
            events = [e for e in events if e.bundle_id == bundle_id]
        return events

    def who_deployed_what(self) -> List[Dict[str, str]]:
        """Access review: who deployed what to where."""
        return [{"actor": e.actor, "bundle_id": e.bundle_id, "channel": e.channel,
                 "action": e.event_type, "timestamp": e.timestamp}
                for e in self._events if e.event_type in ("publish", "promote", "rollback")]

    def save(self, path: Optional[Path] = None) -> None:
        p = path or self._path
        if not p:
            return
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps([e.to_dict() for e in self._events], indent=2) + "\n", encoding="utf-8")
