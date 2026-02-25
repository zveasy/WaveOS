"""Anti-rollback controls — monotonic version epochs to prevent installing vulnerable older builds."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.crypto.anti_rollback")


@dataclass
class VersionEpoch:
    """Monotonic epoch counter for anti-rollback."""
    epoch: int
    version: str
    bundle_id: str
    recorded_at: str = ""

    def to_dict(self) -> dict:
        return {
            "epoch": self.epoch,
            "version": self.version,
            "bundle_id": self.bundle_id,
            "recorded_at": self.recorded_at or utc_now().isoformat(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> VersionEpoch:
        return cls(epoch=d.get("epoch", 0), version=d.get("version", ""), bundle_id=d.get("bundle_id", ""), recorded_at=d.get("recorded_at", ""))


def _epoch_path(state_dir: Path) -> Path:
    return state_dir / "version_epoch.json"


def get_current_epoch(state_dir: Path) -> Optional[VersionEpoch]:
    """Get the current version epoch."""
    path = _epoch_path(state_dir)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return VersionEpoch.from_dict(data)
    except (json.JSONDecodeError, KeyError):
        return None


def record_epoch(state_dir: Path, epoch: int, version: str, bundle_id: str) -> VersionEpoch:
    """Record a new version epoch (must be strictly increasing)."""
    state_dir.mkdir(parents=True, exist_ok=True)
    current = get_current_epoch(state_dir)
    if current and epoch <= current.epoch:
        raise ValueError(f"Epoch {epoch} is not greater than current epoch {current.epoch}. Anti-rollback violation.")
    ve = VersionEpoch(epoch=epoch, version=version, bundle_id=bundle_id, recorded_at=utc_now().isoformat())
    _epoch_path(state_dir).write_text(json.dumps(ve.to_dict(), indent=2) + "\n", encoding="utf-8")

    history_path = state_dir / "version_epoch_history.jsonl"
    with history_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(ve.to_dict()) + "\n")
    return ve


def check_anti_rollback(
    state_dir: Path,
    proposed_epoch: int,
    allow_override: bool = False,
) -> tuple[bool, str]:
    """Check if proposed epoch is allowed. Returns (allowed, reason)."""
    current = get_current_epoch(state_dir)
    if not current:
        return True, "No existing epoch, first install"
    if proposed_epoch > current.epoch:
        return True, f"Epoch {proposed_epoch} > current {current.epoch}"
    if proposed_epoch == current.epoch:
        return True, f"Epoch {proposed_epoch} == current (re-install)"
    if allow_override:
        logger.warning("Anti-rollback override: epoch %d < current %d", proposed_epoch, current.epoch)
        return True, f"Override: epoch {proposed_epoch} < current {current.epoch}"
    return False, f"Anti-rollback: epoch {proposed_epoch} < current {current.epoch}. Downgrade blocked."
