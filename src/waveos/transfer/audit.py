"""Transfer audit — chain-of-custody tracking for artifacts from CI to device."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.transfer.audit")


@dataclass
class ChainOfCustodyEntry:
    """Single entry in the chain of custody."""
    step: str
    actor: str
    bundle_id: str
    timestamp: str = ""
    action: str = ""
    source: str = ""
    destination: str = ""
    sha256: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    prev_hash: str = ""

    def to_dict(self) -> dict:
        return {
            "step": self.step,
            "actor": self.actor,
            "bundle_id": self.bundle_id,
            "timestamp": self.timestamp or utc_now().isoformat(),
            "action": self.action,
            "source": self.source,
            "destination": self.destination,
            "sha256": self.sha256,
            "details": self.details,
            "prev_hash": self.prev_hash,
        }

    @classmethod
    def from_dict(cls, d: dict) -> ChainOfCustodyEntry:
        return cls(**{k: d[k] for k in d if k in cls.__dataclass_fields__})

    def entry_hash(self) -> str:
        content = json.dumps(self.to_dict(), sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()


class TransferAuditLog:
    """Tamper-evident chain-of-custody log for bundle transfers."""

    def __init__(self, log_path: Path) -> None:
        self.log_path = log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> List[ChainOfCustodyEntry]:
        if not self.log_path.exists():
            return []
        entries = []
        for line in self.log_path.read_text(encoding="utf-8").strip().split("\n"):
            if line.strip():
                try:
                    entries.append(ChainOfCustodyEntry.from_dict(json.loads(line)))
                except (json.JSONDecodeError, KeyError):
                    pass
        return entries

    def append(self, step: str, actor: str, bundle_id: str, action: str = "", source: str = "", destination: str = "", sha256: str = "", details: Optional[Dict[str, Any]] = None) -> ChainOfCustodyEntry:
        entries = self._load()
        prev_hash = entries[-1].entry_hash() if entries else ""
        entry = ChainOfCustodyEntry(
            step=step, actor=actor, bundle_id=bundle_id, timestamp=utc_now().isoformat(),
            action=action, source=source, destination=destination, sha256=sha256,
            details=details or {}, prev_hash=prev_hash,
        )
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry.to_dict(), default=str) + "\n")
        return entry

    def get_chain(self, bundle_id: Optional[str] = None) -> List[ChainOfCustodyEntry]:
        entries = self._load()
        if bundle_id:
            entries = [e for e in entries if e.bundle_id == bundle_id]
        return entries

    def verify_chain(self) -> tuple[bool, List[str]]:
        """Verify hash chain integrity."""
        entries = self._load()
        errors: List[str] = []
        for i, entry in enumerate(entries):
            if i == 0:
                if entry.prev_hash:
                    errors.append(f"Entry 0 has prev_hash but should be empty")
            else:
                expected = entries[i - 1].entry_hash()
                if entry.prev_hash != expected:
                    errors.append(f"Entry {i} prev_hash mismatch: expected {expected[:16]}...")
        return len(errors) == 0, errors

    def export_for_compliance(self, bundle_id: str) -> Dict[str, Any]:
        chain = self.get_chain(bundle_id)
        return {
            "bundle_id": bundle_id,
            "chain_length": len(chain),
            "first_seen": chain[0].timestamp if chain else "",
            "last_seen": chain[-1].timestamp if chain else "",
            "steps": [e.to_dict() for e in chain],
            "exported_at": utc_now().isoformat(),
        }
