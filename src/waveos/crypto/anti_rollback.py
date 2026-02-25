"""Anti-rollback controls — monotonic version epochs and downgrade prevention."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.crypto.anti_rollback")


@dataclass
class VersionEpoch:
    bundle_id: str
    version: str
    epoch: int
    timestamp: str = ""
    approved_downgrade: bool = False
    approver: str = ""

    def to_dict(self) -> dict:
        return {
            "bundle_id": self.bundle_id,
            "version": self.version,
            "epoch": self.epoch,
            "timestamp": self.timestamp or utc_now().isoformat(),
            "approved_downgrade": self.approved_downgrade,
            "approver": self.approver,
        }

    @classmethod
    def from_dict(cls, d: dict) -> VersionEpoch:
        return cls(**{k: d[k] for k in d if k in cls.__dataclass_fields__})


def _load_epochs(epoch_path: Path) -> List[VersionEpoch]:
    if not epoch_path.exists():
        return []
    try:
        data = json.loads(epoch_path.read_text(encoding="utf-8"))
        return [VersionEpoch.from_dict(e) for e in data]
    except (json.JSONDecodeError, KeyError):
        return []


def _save_epochs(epoch_path: Path, epochs: List[VersionEpoch]) -> None:
    epoch_path.parent.mkdir(parents=True, exist_ok=True)
    epoch_path.write_text(json.dumps([e.to_dict() for e in epochs], indent=2) + "\n", encoding="utf-8")


def record_epoch(epoch_path: Path, bundle_id: str, version: str, epoch: int) -> VersionEpoch:
    epochs = _load_epochs(epoch_path)
    entry = VersionEpoch(bundle_id=bundle_id, version=version, epoch=epoch, timestamp=utc_now().isoformat())
    epochs.append(entry)
    _save_epochs(epoch_path, epochs)
    return entry


def get_current_epoch(epoch_path: Path) -> int:
    epochs = _load_epochs(epoch_path)
    if not epochs:
        return 0
    return max(e.epoch for e in epochs)


def check_anti_rollback(
    epoch_path: Path,
    proposed_epoch: int,
    allow_approved_downgrade: bool = False,
    approver: str = "",
) -> Tuple[bool, str]:
    """Check if proposed epoch is allowed (must be >= current unless explicitly approved)."""
    current = get_current_epoch(epoch_path)
    if proposed_epoch >= current:
        return True, f"Epoch {proposed_epoch} >= current {current}"
    if allow_approved_downgrade and approver:
        logger.warning("Approved downgrade from epoch %d to %d by %s", current, proposed_epoch, approver)
        return True, f"Approved downgrade to epoch {proposed_epoch} by {approver}"
    return False, f"Anti-rollback: epoch {proposed_epoch} < current {current}. Downgrade blocked."


def parse_version_epoch(version: str) -> int:
    """Extract epoch from version string. Supports semver and epoch-prefixed versions."""
    parts = version.replace("-", ".").split(".")
    try:
        return sum(int(p) * (1000 ** (len(parts) - 1 - i)) for i, p in enumerate(parts) if p.isdigit())
    except (ValueError, IndexError):
        return 0
