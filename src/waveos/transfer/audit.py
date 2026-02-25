"""Chain-of-custody audit trail for controlled transfer operations."""

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
    """Single entry in the chain-of-custody for a bundle."""
    stage: str  # build | sign | publish | transfer | scan | approve | mirror | install | activate
    actor: str
    timestamp: str
    bundle_id: str
    artifact_hash: str = ""
    location: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    prev_hash: str = ""
    entry_hash: str = ""

    def compute_hash(self) -> str:
        content = json.dumps({
            "stage": self.stage, "actor": self.actor, "timestamp": self.timestamp,
            "bundle_id": self.bundle_id, "artifact_hash": self.artifact_hash,
            "location": self.location, "prev_hash": self.prev_hash,
        }, sort_keys=True)
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict:
        return {
            "stage": self.stage, "actor": self.actor, "timestamp": self.timestamp,
            "bundle_id": self.bundle_id, "artifact_hash": self.artifact_hash,
            "location": self.location, "details": self.details,
            "prev_hash": self.prev_hash, "entry_hash": self.entry_hash,
        }

    @classmethod
    def from_dict(cls, d: dict) -> ChainOfCustodyEntry:
        return cls(**{k: d[k] for k in d if k in cls.__dataclass_fields__})


class TransferAuditChain:
    """Hash-chain audit trail for bundle transfers (CI -> gateway -> mirror -> device)."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._entries: List[ChainOfCustodyEntry] = []
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            try:
                for line in self._path.read_text(encoding="utf-8").strip().split("\n"):
                    if line.strip():
                        self._entries.append(ChainOfCustodyEntry.from_dict(json.loads(line)))
            except (json.JSONDecodeError, KeyError):
                pass

    def _save_entry(self, entry: ChainOfCustodyEntry) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry.to_dict(), default=str) + "\n")

    def append(
        self,
        stage: str,
        actor: str,
        bundle_id: str,
        artifact_hash: str = "",
        location: str = "",
        details: Optional[Dict[str, Any]] = None,
    ) -> ChainOfCustodyEntry:
        prev_hash = self._entries[-1].entry_hash if self._entries else "genesis"
        entry = ChainOfCustodyEntry(
            stage=stage, actor=actor, timestamp=utc_now().isoformat(),
            bundle_id=bundle_id, artifact_hash=artifact_hash,
            location=location, details=details or {},
            prev_hash=prev_hash,
        )
        entry.entry_hash = entry.compute_hash()
        self._entries.append(entry)
        self._save_entry(entry)
        return entry

    def get_chain(self, bundle_id: Optional[str] = None) -> List[ChainOfCustodyEntry]:
        if bundle_id:
            return [e for e in self._entries if e.bundle_id == bundle_id]
        return list(self._entries)

    def verify_chain(self, bundle_id: Optional[str] = None) -> tuple[bool, List[str]]:
        """Verify hash chain integrity. Returns (ok, errors)."""
        chain = self.get_chain(bundle_id)
        errors: List[str] = []
        for i, entry in enumerate(chain):
            expected_hash = entry.compute_hash()
            if entry.entry_hash != expected_hash:
                errors.append(f"Entry {i} hash mismatch at stage={entry.stage}")
            if i > 0 and entry.prev_hash != chain[i - 1].entry_hash:
                errors.append(f"Entry {i} prev_hash mismatch (chain broken)")
        return len(errors) == 0, errors

    def export_for_bundle(self, bundle_id: str) -> List[Dict[str, Any]]:
        return [e.to_dict() for e in self.get_chain(bundle_id)]
