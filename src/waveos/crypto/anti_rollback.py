"""Anti-rollback protection — monotonic version counters and release epochs."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.crypto.anti_rollback")


@dataclass
class ReleaseEpoch:
    """Monotonic release epoch for anti-rollback protection."""
    epoch: int
    bundle_id: str
    version: str
    timestamp: str = ""
    channel: str = ""
    approved_downgrade: bool = False

    def to_dict(self) -> dict:
        return {
            "epoch": self.epoch, "bundle_id": self.bundle_id, "version": self.version,
            "timestamp": self.timestamp or utc_now().isoformat(), "channel": self.channel,
            "approved_downgrade": self.approved_downgrade,
        }

    @classmethod
    def from_dict(cls, d: dict) -> ReleaseEpoch:
        return cls(**{k: d[k] for k in d if k in cls.__dataclass_fields__})


def _epoch_store_path(base_dir: Path) -> Path:
    return base_dir / "release_epochs.json"


def get_current_epoch(base_dir: Path) -> int:
    """Get the current (highest) release epoch."""
    path = _epoch_store_path(base_dir)
    if not path.exists():
        return 0
    try:
        epochs = json.loads(path.read_text(encoding="utf-8"))
        if not epochs:
            return 0
        return max(e.get("epoch", 0) for e in epochs)
    except (json.JSONDecodeError, KeyError):
        return 0


def get_epoch_history(base_dir: Path) -> List[ReleaseEpoch]:
    """Get full epoch history."""
    path = _epoch_store_path(base_dir)
    if not path.exists():
        return []
    try:
        return [ReleaseEpoch.from_dict(e) for e in json.loads(path.read_text(encoding="utf-8"))]
    except (json.JSONDecodeError, KeyError):
        return []


def record_epoch(base_dir: Path, bundle_id: str, version: str, channel: str = "") -> ReleaseEpoch:
    """Record a new release epoch (monotonically increasing)."""
    base_dir.mkdir(parents=True, exist_ok=True)
    current = get_current_epoch(base_dir)
    new_epoch = current + 1
    entry = ReleaseEpoch(
        epoch=new_epoch, bundle_id=bundle_id, version=version,
        timestamp=utc_now().isoformat(), channel=channel,
    )
    history = get_epoch_history(base_dir)
    history.append(entry)
    _epoch_store_path(base_dir).write_text(
        json.dumps([e.to_dict() for e in history], indent=2) + "\n", encoding="utf-8",
    )
    logger.info("Recorded epoch %d for %s v%s", new_epoch, bundle_id, version)
    return entry


def check_anti_rollback(
    base_dir: Path,
    target_epoch: int,
    allow_approved_downgrade: bool = False,
) -> Tuple[bool, str]:
    """Check if installing a bundle at target_epoch is allowed.
    Returns (allowed, reason).
    """
    current = get_current_epoch(base_dir)
    if target_epoch >= current:
        return True, ""
    if target_epoch == 0 and current == 0:
        return True, ""
    if allow_approved_downgrade:
        return True, f"Approved downgrade from epoch {current} to {target_epoch}"
    return False, f"Anti-rollback: target epoch {target_epoch} < current {current}. Set allow_approved_downgrade=True to override."
