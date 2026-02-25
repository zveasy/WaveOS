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
    """A monotonic version epoch record."""
    bundle_id: str
    epoch: int
    version: str = ""
    timestamp: str = ""
    approved_downgrade: bool = False

    def to_dict(self) -> dict:
        return {
            "bundle_id": self.bundle_id, "epoch": self.epoch,
            "version": self.version, "timestamp": self.timestamp or utc_now().isoformat(),
            "approved_downgrade": self.approved_downgrade,
        }

    @classmethod
    def from_dict(cls, d: dict) -> VersionEpoch:
        return cls(**{k: d[k] for k in d if k in cls.__dataclass_fields__})


class EpochStore:
    """Persists monotonic epoch counters for anti-rollback enforcement."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._epochs: Dict[str, int] = {}
        self._history: List[VersionEpoch] = []
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
                self._epochs = data.get("epochs", {})
                self._history = [VersionEpoch.from_dict(h) for h in data.get("history", [])]
            except (json.JSONDecodeError, KeyError):
                pass

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps({
            "epochs": self._epochs,
            "history": [h.to_dict() for h in self._history[-500:]],
        }, indent=2) + "\n", encoding="utf-8")

    def current_epoch(self, app_name: str = "default") -> int:
        return self._epochs.get(app_name, 0)

    def record(self, app_name: str, bundle_id: str, epoch: int, version: str = "") -> None:
        self._epochs[app_name] = max(self._epochs.get(app_name, 0), epoch)
        self._history.append(VersionEpoch(
            bundle_id=bundle_id, epoch=epoch, version=version,
            timestamp=utc_now().isoformat(),
        ))
        self._save()

    def history(self, app_name: str = "", limit: int = 50) -> List[VersionEpoch]:
        h = self._history
        if app_name:
            h = [e for e in h if e.bundle_id.startswith(app_name)]
        return h[-limit:]


def check_anti_rollback(
    epoch_store: EpochStore,
    app_name: str,
    proposed_epoch: int,
    allow_approved_downgrade: bool = False,
) -> tuple[bool, str]:
    """Check if a proposed epoch is allowed (anti-rollback).
    Returns (allowed, reason).
    """
    current = epoch_store.current_epoch(app_name)
    if proposed_epoch > current:
        return True, f"Epoch {proposed_epoch} > current {current}"
    if proposed_epoch == current:
        return True, f"Epoch {proposed_epoch} == current (re-install)"
    if allow_approved_downgrade:
        return True, f"Downgrade {proposed_epoch} < {current} approved"
    return False, f"Anti-rollback: epoch {proposed_epoch} < current {current}. Set allow_approved_downgrade=True to override."


def record_epoch(epoch_store: EpochStore, app_name: str, bundle_id: str, epoch: int, version: str = "") -> None:
    epoch_store.record(app_name, bundle_id, epoch, version)
