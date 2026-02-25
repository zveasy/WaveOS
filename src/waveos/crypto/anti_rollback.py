"""Anti-rollback controls — monotonic version epochs and release counters."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.crypto.anti_rollback")


@dataclass
class VersionEpoch:
    """Monotonic version epoch for anti-rollback."""
    epoch: int
    bundle_id: str
    version: str
    installed_at: str = ""
    approved_downgrade: bool = False

    def to_dict(self) -> dict:
        return {"epoch": self.epoch, "bundle_id": self.bundle_id, "version": self.version, "installed_at": self.installed_at, "approved_downgrade": self.approved_downgrade}

    @classmethod
    def from_dict(cls, d: dict) -> VersionEpoch:
        return cls(**{k: d[k] for k in d if k in cls.__dataclass_fields__})


class ReleaseEpochStore:
    """Persistent store for release epochs (anti-rollback)."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._epochs: List[VersionEpoch] = []
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self._epochs = [VersionEpoch.from_dict(e) for e in data]
        except (json.JSONDecodeError, KeyError):
            pass

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps([e.to_dict() for e in self._epochs], indent=2) + "\n", encoding="utf-8")

    def current_epoch(self) -> int:
        if not self._epochs:
            return 0
        return max(e.epoch for e in self._epochs)

    def get_current(self) -> Optional[VersionEpoch]:
        if not self._epochs:
            return None
        return max(self._epochs, key=lambda e: e.epoch)

    def record(self, bundle_id: str, version: str, epoch: Optional[int] = None) -> VersionEpoch:
        e = epoch if epoch is not None else self.current_epoch() + 1
        ve = VersionEpoch(epoch=e, bundle_id=bundle_id, version=version, installed_at=utc_now().isoformat())
        self._epochs.append(ve)
        self._save()
        return ve

    def history(self) -> List[VersionEpoch]:
        return sorted(self._epochs, key=lambda e: e.epoch)


def check_anti_rollback(proposed_epoch: int, store: ReleaseEpochStore, allow_approved_downgrade: bool = False) -> tuple[bool, str]:
    """Check if a proposed epoch is allowed (must be >= current)."""
    current = store.current_epoch()
    if proposed_epoch > current:
        return True, f"epoch {proposed_epoch} > current {current}"
    if proposed_epoch == current:
        return True, f"epoch {proposed_epoch} == current {current} (re-install)"
    if allow_approved_downgrade:
        return True, f"downgrade approved: {proposed_epoch} < {current}"
    return False, f"anti-rollback violation: proposed {proposed_epoch} < current {current}"


def record_installed_epoch(store: ReleaseEpochStore, bundle_id: str, version: str, epoch: Optional[int] = None) -> VersionEpoch:
    return store.record(bundle_id, version, epoch)


def get_current_epoch(store: ReleaseEpochStore) -> int:
    return store.current_epoch()
