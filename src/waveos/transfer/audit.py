"""Transfer audit trail — chain-of-custody for artifacts from CI -> gateway -> mirror -> device."""

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
    """A single entry in the chain of custody."""
    step: str
    actor: str
    bundle_id: str
    timestamp: str = ""
    action: str = ""
    location: str = ""
    sha256: str = ""
    prev_hash: str = ""
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "step": self.step, "actor": self.actor, "bundle_id": self.bundle_id,
            "timestamp": self.timestamp or utc_now().isoformat(), "action": self.action,
            "location": self.location, "sha256": self.sha256, "prev_hash": self.prev_hash,
            "details": self.details,
        }

    @classmethod
    def from_dict(cls, d: dict) -> ChainOfCustodyEntry:
        return cls(**{k: d[k] for k in d if k in cls.__dataclass_fields__})

    def compute_hash(self) -> str:
        payload = json.dumps(self.to_dict(), sort_keys=True).encode()
        return hashlib.sha256(payload).hexdigest()


class TransferAuditLog:
    """Append-only, hash-chained audit log for transfer custody."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._entries: List[ChainOfCustodyEntry] = []
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            for line in self.path.read_text(encoding="utf-8").strip().split("\n"):
                if line.strip():
                    self._entries.append(ChainOfCustodyEntry.from_dict(json.loads(line)))
        except (json.JSONDecodeError, KeyError):
            pass

    def _save_entry(self, entry: ChainOfCustodyEntry) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry.to_dict(), default=str) + "\n")

    def append(self, step: str, actor: str, bundle_id: str, action: str = "", location: str = "", sha256: str = "", details: Optional[Dict[str, Any]] = None) -> ChainOfCustodyEntry:
        prev_hash = self._entries[-1].compute_hash() if self._entries else ""
        entry = ChainOfCustodyEntry(
            step=step, actor=actor, bundle_id=bundle_id, action=action,
            location=location, sha256=sha256, prev_hash=prev_hash, details=details or {},
        )
        self._entries.append(entry)
        self._save_entry(entry)
        return entry

    def verify_chain(self) -> tuple[bool, List[str]]:
        """Verify the hash chain integrity."""
        errors: List[str] = []
        for i, entry in enumerate(self._entries):
            if i == 0:
                if entry.prev_hash:
                    errors.append(f"Entry 0 has non-empty prev_hash")
                continue
            expected = self._entries[i - 1].compute_hash()
            if entry.prev_hash != expected:
                errors.append(f"Entry {i}: prev_hash mismatch (expected {expected[:16]}..., got {entry.prev_hash[:16]}...)")
        return len(errors) == 0, errors

    def get_chain(self, bundle_id: Optional[str] = None) -> List[ChainOfCustodyEntry]:
        entries = self._entries
        if bundle_id:
            entries = [e for e in entries if e.bundle_id == bundle_id]
        return entries

    def export(self, bundle_id: Optional[str] = None) -> List[Dict[str, Any]]:
        return [e.to_dict() for e in self.get_chain(bundle_id)]
