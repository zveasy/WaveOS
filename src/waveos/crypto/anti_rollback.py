"""Anti-rollback controls — monotonic version epochs and rollback policy."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.crypto.anti_rollback")


@dataclass
class VersionEpoch:
    epoch: int
    version: str
    bundle_id: str
    timestamp: str = ""
    approved_downgrade: bool = False

    def to_dict(self) -> dict:
        return {"epoch": self.epoch, "version": self.version, "bundle_id": self.bundle_id,
                "timestamp": self.timestamp or utc_now().isoformat(),
                "approved_downgrade": self.approved_downgrade}

    @classmethod
    def from_dict(cls, d: dict) -> VersionEpoch:
        return cls(**{k: d[k] for k in d if k in cls.__dataclass_fields__})


def get_current_epoch(epoch_path: Path) -> Optional[VersionEpoch]:
    if not epoch_path.exists():
        return None
    try:
        data = json.loads(epoch_path.read_text(encoding="utf-8"))
        epochs = [VersionEpoch.from_dict(e) for e in data] if isinstance(data, list) else [VersionEpoch.from_dict(data)]
        return max(epochs, key=lambda e: e.epoch) if epochs else None
    except (json.JSONDecodeError, KeyError):
        return None


def record_epoch(epoch_path: Path, version: str, bundle_id: str) -> VersionEpoch:
    current = get_current_epoch(epoch_path)
    new_epoch = (current.epoch + 1) if current else 1
    entry = VersionEpoch(epoch=new_epoch, version=version, bundle_id=bundle_id, timestamp=utc_now().isoformat())
    epochs = []
    if epoch_path.exists():
        try:
            data = json.loads(epoch_path.read_text(encoding="utf-8"))
            epochs = data if isinstance(data, list) else [data]
        except (json.JSONDecodeError, OSError):
            pass
    epochs.append(entry.to_dict())
    epoch_path.parent.mkdir(parents=True, exist_ok=True)
    epoch_path.write_text(json.dumps(epochs, indent=2) + "\n", encoding="utf-8")
    return entry


def check_anti_rollback(epoch_path: Path, candidate_version: str, candidate_epoch: Optional[int] = None,
                        allow_approved_downgrade: bool = False) -> tuple[bool, str]:
    """Check if installing candidate would violate anti-rollback policy.

    Returns (allowed, reason).
    """
    current = get_current_epoch(epoch_path)
    if not current:
        return True, "no previous epoch recorded"

    if candidate_epoch is not None:
        if candidate_epoch < current.epoch:
            if allow_approved_downgrade:
                return True, f"downgrade approved: epoch {candidate_epoch} < {current.epoch}"
            return False, f"anti-rollback: epoch {candidate_epoch} < current {current.epoch}"
        return True, f"epoch {candidate_epoch} >= {current.epoch}"

    if candidate_version < current.version:
        if allow_approved_downgrade:
            return True, f"downgrade approved: {candidate_version} < {current.version}"
        return False, f"anti-rollback: version {candidate_version} < current {current.version}"

    return True, f"version {candidate_version} >= {current.version}"


def get_epoch_history(epoch_path: Path) -> List[VersionEpoch]:
    if not epoch_path.exists():
        return []
    try:
        data = json.loads(epoch_path.read_text(encoding="utf-8"))
        entries = data if isinstance(data, list) else [data]
        return [VersionEpoch.from_dict(e) for e in entries]
    except (json.JSONDecodeError, KeyError):
        return []
