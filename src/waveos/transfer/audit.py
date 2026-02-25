"""Transfer audit — chain-of-custody tracking for artifacts across trust boundaries."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.transfer.audit")


@dataclass
class CustodyEvent:
    event_type: str  # build | publish | scan | approve | transfer | verify | install | activate
    actor: str
    bundle_id: str
    timestamp: str = ""
    location: str = ""
    sha256: str = ""
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "event_type": self.event_type,
            "actor": self.actor,
            "bundle_id": self.bundle_id,
            "timestamp": self.timestamp or utc_now().isoformat(),
            "location": self.location,
            "sha256": self.sha256,
            "details": self.details,
        }


@dataclass
class ChainOfCustody:
    bundle_id: str
    events: List[CustodyEvent] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_event(self, event: CustodyEvent) -> None:
        self.events.append(event)

    def to_dict(self) -> dict:
        return {
            "type": "chain_of_custody",
            "bundle_id": self.bundle_id,
            "events": [e.to_dict() for e in self.events],
            "metadata": self.metadata,
            "event_count": len(self.events),
            "integrity_hash": self._integrity_hash(),
        }

    def _integrity_hash(self) -> str:
        content = json.dumps([e.to_dict() for e in self.events], sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> ChainOfCustody:
        data = json.loads(path.read_text(encoding="utf-8"))
        chain = cls(bundle_id=data.get("bundle_id", ""))
        for e in data.get("events", []):
            chain.events.append(CustodyEvent(**{k: e[k] for k in e if k in CustodyEvent.__dataclass_fields__}))
        chain.metadata = data.get("metadata", {})
        return chain

    def verify_integrity(self) -> bool:
        return self._integrity_hash() == json.loads(json.dumps(self.to_dict())).get("integrity_hash", "")


class TransferAuditLog:
    """Append-only audit log for transfer events with hash chain."""

    def __init__(self, log_path: Path) -> None:
        self.path = log_path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._prev_hash = "0" * 64

    def append(self, event: CustodyEvent) -> str:
        entry = event.to_dict()
        entry["prev_hash"] = self._prev_hash
        entry_json = json.dumps(entry, sort_keys=True)
        entry_hash = hashlib.sha256(entry_json.encode()).hexdigest()
        entry["entry_hash"] = entry_hash
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str) + "\n")
        self._prev_hash = entry_hash
        return entry_hash

    def verify_chain(self) -> tuple[bool, int]:
        """Verify the hash chain. Returns (valid, entry_count)."""
        if not self.path.exists():
            return True, 0
        prev = "0" * 64
        count = 0
        for line in self.path.read_text(encoding="utf-8").strip().split("\n"):
            if not line.strip():
                continue
            entry = json.loads(line)
            if entry.get("prev_hash") != prev:
                return False, count
            stored_hash = entry.pop("entry_hash", "")
            computed = hashlib.sha256(json.dumps(entry, sort_keys=True).encode()).hexdigest()
            if computed != stored_hash:
                return False, count
            prev = stored_hash
            count += 1
        return True, count
