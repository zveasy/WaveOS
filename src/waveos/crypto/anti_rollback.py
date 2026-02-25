"""Anti-rollback controls — monotonic version epochs and release ordering enforcement."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.crypto.anti_rollback")


@dataclass
class VersionEpoch:
    """A monotonically increasing release epoch for anti-rollback."""
    bundle_id: str
    epoch: int
    version: str = ""
    channel: str = ""
    timestamp: str = ""
    approved_downgrade: bool = False

    def to_dict(self) -> dict:
        return {
            "bundle_id": self.bundle_id, "epoch": self.epoch, "version": self.version,
            "channel": self.channel, "timestamp": self.timestamp or utc_now().isoformat(),
            "approved_downgrade": self.approved_downgrade,
        }

    @classmethod
    def from_dict(cls, d: dict) -> VersionEpoch:
        return cls(**{k: d[k] for k in d if k in cls.__dataclass_fields__})


class ReleaseEpochStore:
    """Tracks monotonic release epochs per channel to prevent rollback to vulnerable versions."""

    def __init__(self, store_path: Optional[Path] = None) -> None:
        self._epochs: Dict[str, int] = {}
        self._history: List[VersionEpoch] = []
        self._store_path = store_path
        if store_path and store_path.exists():
            self._load()

    def _load(self) -> None:
        try:
            data = json.loads(self._store_path.read_text(encoding="utf-8"))
            self._epochs = data.get("current_epochs", {})
            self._history = [VersionEpoch.from_dict(e) for e in data.get("history", [])]
        except (json.JSONDecodeError, OSError):
            pass

    def save(self) -> None:
        if self._store_path:
            self._store_path.parent.mkdir(parents=True, exist_ok=True)
            self._store_path.write_text(json.dumps({
                "current_epochs": self._epochs,
                "history": [e.to_dict() for e in self._history[-500:]],
            }, indent=2) + "\n", encoding="utf-8")

    def get_epoch(self, channel: str) -> int:
        return self._epochs.get(channel, 0)

    def record_release(self, bundle_id: str, epoch: int, channel: str, version: str = "") -> VersionEpoch:
        current = self._epochs.get(channel, 0)
        if epoch <= current:
            raise ValueError(f"Epoch {epoch} is not greater than current {current} for channel {channel}")
        self._epochs[channel] = epoch
        entry = VersionEpoch(bundle_id=bundle_id, epoch=epoch, version=version, channel=channel, timestamp=utc_now().isoformat())
        self._history.append(entry)
        self.save()
        return entry

    def get_history(self, channel: Optional[str] = None) -> List[VersionEpoch]:
        if channel:
            return [e for e in self._history if e.channel == channel]
        return list(self._history)


def check_anti_rollback(
    proposed_epoch: int,
    channel: str,
    epoch_store: ReleaseEpochStore,
    allow_approved_downgrade: bool = False,
    approved: bool = False,
) -> Tuple[bool, str]:
    """Check if a proposed install violates anti-rollback policy.

    Returns (allowed, reason).
    """
    current = epoch_store.get_epoch(channel)
    if proposed_epoch > current:
        return True, f"Epoch {proposed_epoch} > current {current}"
    if proposed_epoch == current:
        return True, f"Same epoch {proposed_epoch} (re-install)"
    if allow_approved_downgrade and approved:
        return True, f"Downgrade approved: {proposed_epoch} < {current}"
    return False, f"Anti-rollback: epoch {proposed_epoch} < current {current} for channel {channel}"
