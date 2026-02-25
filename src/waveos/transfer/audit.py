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
    """A single custody event in the artifact's journey."""
    stage: str  # ci_build | ci_sign | publish | gateway_scan | gateway_approve | mirror_sync | agent_download | agent_verify | agent_install
    actor: str
    timestamp: str = ""
    bundle_id: str = ""
    checksum: str = ""
    location: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    previous_hash: str = ""

    def to_dict(self) -> dict:
        return {
            "stage": self.stage, "actor": self.actor,
            "timestamp": self.timestamp or utc_now().isoformat(),
            "bundle_id": self.bundle_id, "checksum": self.checksum,
            "location": self.location, "details": self.details,
            "previous_hash": self.previous_hash,
        }

    @classmethod
    def from_dict(cls, d: dict) -> ChainOfCustodyEntry:
        return cls(**{k: d[k] for k in d if k in cls.__dataclass_fields__})

    def entry_hash(self) -> str:
        payload = json.dumps(self.to_dict(), sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


class TransferAuditChain:
    """Tamper-evident chain-of-custody for bundle transfers."""

    def __init__(self) -> None:
        self._chain: List[ChainOfCustodyEntry] = []

    def add_entry(self, stage: str, actor: str, bundle_id: str = "", checksum: str = "", location: str = "", details: Optional[Dict[str, Any]] = None) -> ChainOfCustodyEntry:
        prev_hash = self._chain[-1].entry_hash() if self._chain else "genesis"
        entry = ChainOfCustodyEntry(
            stage=stage, actor=actor, timestamp=utc_now().isoformat(),
            bundle_id=bundle_id, checksum=checksum, location=location,
            details=details or {}, previous_hash=prev_hash,
        )
        self._chain.append(entry)
        return entry

    def verify_chain(self) -> tuple[bool, List[str]]:
        errors: List[str] = []
        for i, entry in enumerate(self._chain):
            if i == 0:
                if entry.previous_hash != "genesis":
                    errors.append(f"First entry previous_hash should be 'genesis', got '{entry.previous_hash}'")
            else:
                expected = self._chain[i - 1].entry_hash()
                if entry.previous_hash != expected:
                    errors.append(f"Entry {i} ({entry.stage}): hash chain broken")
        return len(errors) == 0, errors

    def get_chain(self) -> List[ChainOfCustodyEntry]:
        return list(self._chain)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps([e.to_dict() for e in self._chain], indent=2) + "\n", encoding="utf-8")

    def load(self, path: Path) -> None:
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self._chain = [ChainOfCustodyEntry.from_dict(e) for e in data]
        except (json.JSONDecodeError, KeyError):
            pass

    def export_for_compliance(self) -> Dict[str, Any]:
        return {
            "chain_length": len(self._chain),
            "stages": [e.stage for e in self._chain],
            "entries": [e.to_dict() for e in self._chain],
            "chain_valid": self.verify_chain()[0],
        }
