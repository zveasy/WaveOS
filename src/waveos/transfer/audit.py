"""Transfer audit — chain-of-custody for artifacts from CI to device."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.transfer.audit")


@dataclass
class TransferReceipt:
    """Signed receipt for a transfer step (CI -> gateway -> mirror -> device)."""
    receipt_id: str
    bundle_id: str
    stage: str   # ci_build | gateway_scan | gateway_approve | mirror_publish | device_install
    actor: str = ""
    timestamp: str = ""
    content_hash: str = ""
    prev_receipt_hash: str = ""
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "receipt_id": self.receipt_id,
            "bundle_id": self.bundle_id,
            "stage": self.stage,
            "actor": self.actor,
            "timestamp": self.timestamp or utc_now().isoformat(),
            "content_hash": self.content_hash,
            "prev_receipt_hash": self.prev_receipt_hash,
            "details": self.details,
        }

    @classmethod
    def from_dict(cls, d: dict) -> TransferReceipt:
        return cls(**{k: d[k] for k in d if k in cls.__dataclass_fields__})

    def compute_hash(self) -> str:
        payload = json.dumps(self.to_dict(), sort_keys=True).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


class TransferAuditLog:
    """Hash-chained audit log for transfer chain-of-custody."""

    def __init__(self, log_path: Optional[Path] = None) -> None:
        self._entries: List[TransferReceipt] = []
        self._log_path = log_path
        if log_path and log_path.exists():
            self._load()

    def _load(self) -> None:
        try:
            for line in self._log_path.read_text(encoding="utf-8").strip().split("\n"):
                if line.strip():
                    self._entries.append(TransferReceipt.from_dict(json.loads(line)))
        except (json.JSONDecodeError, OSError):
            pass

    def _save_entry(self, receipt: TransferReceipt) -> None:
        if self._log_path:
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
            with self._log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(receipt.to_dict(), default=str) + "\n")

    def record(self, bundle_id: str, stage: str, actor: str = "", content_hash: str = "", details: Optional[Dict[str, Any]] = None) -> TransferReceipt:
        """Record a transfer step with hash chain."""
        prev_hash = self._entries[-1].compute_hash() if self._entries else ""
        receipt_id = f"rcpt-{hashlib.sha256(f'{bundle_id}-{stage}-{utc_now().isoformat()}'.encode()).hexdigest()[:12]}"
        receipt = TransferReceipt(
            receipt_id=receipt_id,
            bundle_id=bundle_id,
            stage=stage,
            actor=actor,
            timestamp=utc_now().isoformat(),
            content_hash=content_hash,
            prev_receipt_hash=prev_hash,
            details=details or {},
        )
        self._entries.append(receipt)
        self._save_entry(receipt)
        return receipt

    def verify_chain(self) -> tuple[bool, List[str]]:
        """Verify the hash chain integrity."""
        errors: List[str] = []
        for i, entry in enumerate(self._entries):
            if i == 0:
                if entry.prev_receipt_hash:
                    errors.append(f"First entry should have empty prev_hash, got {entry.prev_receipt_hash[:16]}")
            else:
                expected = self._entries[i - 1].compute_hash()
                if entry.prev_receipt_hash != expected:
                    errors.append(f"Chain broken at entry {i}: expected {expected[:16]}, got {entry.prev_receipt_hash[:16]}")
        return len(errors) == 0, errors

    def get_chain(self, bundle_id: Optional[str] = None) -> List[TransferReceipt]:
        if bundle_id:
            return [e for e in self._entries if e.bundle_id == bundle_id]
        return list(self._entries)

    def export(self) -> List[Dict[str, Any]]:
        return [e.to_dict() for e in self._entries]
