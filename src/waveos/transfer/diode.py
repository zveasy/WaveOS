"""Data diode / one-way sync — bundles flow source→dest only, no metadata flows back."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.transfer.diode")


@dataclass
class DiodeConfig:
    source_dir: Path = Path("out/diode_source")
    dest_dir: Path = Path("out/diode_dest")
    one_way: bool = True
    verify_checksums: bool = True

    def to_dict(self) -> dict:
        return {
            "source_dir": str(self.source_dir), "dest_dir": str(self.dest_dir),
            "one_way": self.one_way, "verify_checksums": self.verify_checksums,
        }


@dataclass
class DiodeSyncResult:
    synced: List[str] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    timestamp: str = ""

    def to_dict(self) -> dict:
        return {"synced": self.synced, "skipped": self.skipped, "errors": self.errors, "timestamp": self.timestamp or utc_now().isoformat()}


class DiodeSync:
    """One-way bundle sync simulating a data diode."""

    def __init__(self, config: Optional[DiodeConfig] = None) -> None:
        self.config = config or DiodeConfig()

    def sync(self) -> DiodeSyncResult:
        result = DiodeSyncResult()
        src = self.config.source_dir
        dst = self.config.dest_dir
        dst.mkdir(parents=True, exist_ok=True)
        if not src.is_dir():
            result.errors.append(f"Source not found: {src}")
            return result
        for item in src.iterdir():
            if not item.is_dir():
                continue
            manifest = item / "bundle.json"
            if not manifest.exists():
                continue
            dest_item = dst / item.name
            if dest_item.exists():
                result.skipped.append(item.name)
                continue
            try:
                shutil.copytree(item, dest_item)
                if self.config.verify_checksums and manifest.exists():
                    src_hash = hashlib.sha256(manifest.read_bytes()).hexdigest()
                    dst_hash = hashlib.sha256((dest_item / "bundle.json").read_bytes()).hexdigest()
                    if src_hash != dst_hash:
                        shutil.rmtree(dest_item)
                        result.errors.append(f"Checksum mismatch for {item.name}")
                        continue
                result.synced.append(item.name)
            except (OSError, shutil.Error) as exc:
                result.errors.append(f"Failed to sync {item.name}: {exc}")
        result.timestamp = utc_now().isoformat()
        return result
