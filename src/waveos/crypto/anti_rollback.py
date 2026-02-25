"""Anti-rollback controls — monotonic version epochs and rollback prevention."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.crypto.anti_rollback")


@dataclass
class ReleaseEpoch:
    epoch: int
    version: str
    bundle_id: str
    released_at: str = ""
    enforced: bool = True
    override_reason: str = ""

    def to_dict(self) -> dict:
        return {
            "epoch": self.epoch,
            "version": self.version,
            "bundle_id": self.bundle_id,
            "released_at": self.released_at or utc_now().isoformat(),
            "enforced": self.enforced,
            "override_reason": self.override_reason,
        }

    @classmethod
    def from_dict(cls, d: dict) -> ReleaseEpoch:
        return cls(**{k: d[k] for k in d if k in cls.__dataclass_fields__})


def _epoch_path(state_dir: Path) -> Path:
    return state_dir / "release_epochs.json"


def get_current_epoch(state_dir: Path) -> int:
    path = _epoch_path(state_dir)
    if not path.exists():
        return 0
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        epochs = [ReleaseEpoch.from_dict(e) for e in data]
        return max((e.epoch for e in epochs), default=0)
    except (json.JSONDecodeError, KeyError):
        return 0


def record_epoch(state_dir: Path, epoch: ReleaseEpoch) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    path = _epoch_path(state_dir)
    existing: List[ReleaseEpoch] = []
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            existing = [ReleaseEpoch.from_dict(e) for e in data]
        except (json.JSONDecodeError, KeyError):
            pass
    existing.append(epoch)
    existing.sort(key=lambda e: e.epoch)
    path.write_text(json.dumps([e.to_dict() for e in existing], indent=2) + "\n", encoding="utf-8")


def check_anti_rollback(
    state_dir: Path,
    candidate_epoch: int,
    allow_override: bool = False,
    override_reason: str = "",
) -> tuple[bool, str]:
    """Check if a candidate epoch is allowed (must be >= current).
    Returns (allowed, reason).
    """
    current = get_current_epoch(state_dir)
    if candidate_epoch >= current:
        return True, f"Epoch {candidate_epoch} >= current {current}"
    if allow_override:
        logger.warning("Anti-rollback override: epoch %d < current %d, reason: %s", candidate_epoch, current, override_reason)
        return True, f"Override: {override_reason}"
    return False, f"Anti-rollback: epoch {candidate_epoch} < current {current}. Set allow_override=True with reason to bypass."
