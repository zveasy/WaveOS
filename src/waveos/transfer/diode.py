"""Data diode / one-way sync mode for classified environments."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.transfer.diode")


class DiodeMode(str, Enum):
    ONE_WAY = "one_way"
    VERIFIED_ONE_WAY = "verified_one_way"


@dataclass
class DiodeSyncResult:
    mode: DiodeMode = DiodeMode.ONE_WAY
    pushed: List[str] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)
    failed: List[str] = field(default_factory=list)
    timestamp: str = ""

    def to_dict(self) -> dict:
        return {"mode": self.mode.value, "pushed": self.pushed, "skipped": self.skipped,
                "failed": self.failed, "timestamp": self.timestamp or utc_now().isoformat()}


class DiodeSync:
    """One-way sync: pushes bundles from source directory to destination directory.
    Simulates data diode behavior — no back-channel, no acknowledgment from dest.
    """

    def __init__(self, source_dir: Path, dest_dir: Path, mode: DiodeMode = DiodeMode.ONE_WAY,
                 verify_hook=None) -> None:
        self.source_dir = source_dir
        self.dest_dir = dest_dir
        self.mode = mode
        self.verify_hook = verify_hook

    def push(self, bundle_ids: Optional[List[str]] = None) -> DiodeSyncResult:
        """Push bundles from source to destination (one-way)."""
        result = DiodeSyncResult(mode=self.mode, timestamp=utc_now().isoformat())
        self.dest_dir.mkdir(parents=True, exist_ok=True)
        source_bundles = self.source_dir / "bundles" if (self.source_dir / "bundles").is_dir() else self.source_dir
        if not source_bundles.exists():
            return result
        for bundle_path in sorted(source_bundles.iterdir()):
            if not bundle_path.is_dir():
                continue
            bid = bundle_path.name
            if bundle_ids and bid not in bundle_ids:
                continue
            dest_path = self.dest_dir / "bundles" / bid
            if dest_path.exists():
                result.skipped.append(bid)
                continue
            if self.mode == DiodeMode.VERIFIED_ONE_WAY and self.verify_hook:
                try:
                    if not self.verify_hook(bundle_path):
                        result.failed.append(bid)
                        continue
                except Exception:
                    result.failed.append(bid)
                    continue
            try:
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(bundle_path, dest_path)
                result.pushed.append(bid)
            except (OSError, shutil.Error):
                result.failed.append(bid)
        return result
