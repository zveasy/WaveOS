"""Anti-rollback controls — monotonic version counters, release epochs, version policy enforcement."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.crypto.anti_rollback")


@dataclass
class VersionEpoch:
    """Monotonic version epoch — tracks the minimum acceptable version per app/channel."""
    app_name: str
    channel: str = "prod"
    epoch: int = 0
    min_version: str = ""
    updated_at: str = ""
    updated_by: str = ""
    reason: str = ""

    def to_dict(self) -> dict:
        return {"app_name": self.app_name, "channel": self.channel, "epoch": self.epoch,
                "min_version": self.min_version, "updated_at": self.updated_at,
                "updated_by": self.updated_by, "reason": self.reason}

    @classmethod
    def from_dict(cls, d: dict) -> VersionEpoch:
        return cls(**{k: d[k] for k in d if k in cls.__dataclass_fields__})


def _parse_version(v: str) -> Tuple[int, ...]:
    """Parse version string into tuple for comparison. Handles semver, epoch-prefixed, etc."""
    v = v.strip().lstrip("v").split("-")[0].split("+")[0]
    parts = []
    for p in v.split("."):
        try:
            parts.append(int(p))
        except ValueError:
            parts.append(0)
    return tuple(parts) if parts else (0,)


def check_anti_rollback(bundle_version: str, epoch: VersionEpoch,
                        allow_override: bool = False) -> Tuple[bool, str]:
    """Check if a bundle version is allowed (not a rollback below the epoch minimum).

    Returns (allowed, reason).
    """
    if not epoch.min_version:
        return True, ""
    bundle_v = _parse_version(bundle_version)
    min_v = _parse_version(epoch.min_version)
    if bundle_v < min_v:
        if allow_override:
            return True, f"Rollback override: {bundle_version} < {epoch.min_version} (epoch {epoch.epoch})"
        return False, f"Anti-rollback: {bundle_version} < minimum {epoch.min_version} (epoch {epoch.epoch})"
    return True, ""


def record_version_epoch(epochs_path: Path, app_name: str, channel: str, version: str,
                         updater: str = "", reason: str = "") -> VersionEpoch:
    """Record a new version epoch (advance the minimum version)."""
    epochs_path.parent.mkdir(parents=True, exist_ok=True)
    epochs: List[VersionEpoch] = []
    if epochs_path.exists():
        try:
            data = json.loads(epochs_path.read_text(encoding="utf-8"))
            epochs = [VersionEpoch.from_dict(e) for e in data]
        except (json.JSONDecodeError, OSError):
            pass
    current = next((e for e in epochs if e.app_name == app_name and e.channel == channel), None)
    new_epoch_num = (current.epoch + 1) if current else 1
    new_epoch = VersionEpoch(app_name=app_name, channel=channel, epoch=new_epoch_num,
                             min_version=version, updated_at=utc_now().isoformat(),
                             updated_by=updater, reason=reason or f"Version advanced to {version}")
    epochs = [e for e in epochs if not (e.app_name == app_name and e.channel == channel)]
    epochs.append(new_epoch)
    epochs_path.write_text(json.dumps([e.to_dict() for e in epochs], indent=2) + "\n", encoding="utf-8")
    return new_epoch


def load_version_epoch(epochs_path: Path, app_name: str, channel: str) -> Optional[VersionEpoch]:
    """Load the current version epoch for an app/channel."""
    if not epochs_path.exists():
        return None
    try:
        data = json.loads(epochs_path.read_text(encoding="utf-8"))
        for e in data:
            ve = VersionEpoch.from_dict(e)
            if ve.app_name == app_name and ve.channel == channel:
                return ve
    except (json.JSONDecodeError, OSError):
        pass
    return None
