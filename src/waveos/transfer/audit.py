"""Transfer audit — chain-of-custody tracking from CI to gateway to mirror to device."""

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
    """Single entry in the chain of custody for a bundle."""
    bundle_id: str
    stage: str
    actor: str
    timestamp: str = ""
    action: str = ""
    location: str = ""
    artifact_hash: str = ""
    previous_hash: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"bundle_id": self.bundle_id, "stage": self.stage, "actor": self.actor,
                "timestamp": self.timestamp or utc_now().isoformat(), "action": self.action,
                "location": self.location, "artifact_hash": self.artifact_hash,
                "previous_hash": self.previous_hash, "metadata": self.metadata}

    @classmethod
    def from_dict(cls, d: dict) -> ChainOfCustodyEntry:
        return cls(**{k: d[k] for k in d if k in cls.__dataclass_fields__})

    def entry_hash(self) -> str:
        canonical = json.dumps(self.to_dict(), sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode()).hexdigest()


class TransferAuditChain:
    """Tamper-evident chain of custody for bundle transfers."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self._entries: List[ChainOfCustodyEntry] = []
        self._path = path
        if path and path.exists():
            self._load(path)

    def _load(self, path: Path) -> None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self._entries = [ChainOfCustodyEntry.from_dict(e) for e in data]
        except (json.JSONDecodeError, OSError):
            pass

    def add_entry(self, bundle_id: str, stage: str, actor: str, action: str = "",
                  location: str = "", artifact_hash: str = "", metadata: Optional[Dict[str, Any]] = None) -> ChainOfCustodyEntry:
        previous_hash = self._entries[-1].entry_hash() if self._entries else ""
        entry = ChainOfCustodyEntry(bundle_id=bundle_id, stage=stage, actor=actor,
                                     timestamp=utc_now().isoformat(), action=action,
                                     location=location, artifact_hash=artifact_hash,
                                     previous_hash=previous_hash, metadata=metadata or {})
        self._entries.append(entry)
        return entry

    def get_chain(self, bundle_id: Optional[str] = None) -> List[ChainOfCustodyEntry]:
        if bundle_id:
            return [e for e in self._entries if e.bundle_id == bundle_id]
        return list(self._entries)

    def verify_chain(self) -> tuple[bool, List[str]]:
        """Verify the hash chain integrity."""
        errors: List[str] = []
        for i, entry in enumerate(self._entries):
            if i == 0:
                if entry.previous_hash:
                    errors.append(f"First entry has non-empty previous_hash")
            else:
                expected = self._entries[i - 1].entry_hash()
                if entry.previous_hash != expected:
                    errors.append(f"Chain break at index {i}: expected {expected[:16]}... got {entry.previous_hash[:16]}...")
        return len(errors) == 0, errors

    def save(self, path: Optional[Path] = None) -> None:
        p = path or self._path
        if not p:
            return
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps([e.to_dict() for e in self._entries], indent=2) + "\n", encoding="utf-8")
