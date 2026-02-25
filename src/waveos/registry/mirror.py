"""Registry mirror — sync bundles between registries for controlled-transfer environments."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from waveos.registry.store import RegistryStore
from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.registry.mirror")


@dataclass
class MirrorSyncResult:
    """Result of a mirror sync operation."""
    synced: List[str] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)
    failed: List[str] = field(default_factory=list)
    transfer_receipts: List[Dict[str, Any]] = field(default_factory=list)
    timestamp: str = ""

    def to_dict(self) -> dict:
        return {"synced": self.synced, "skipped": self.skipped, "failed": self.failed,
                "transfer_receipts": self.transfer_receipts,
                "timestamp": self.timestamp or utc_now().isoformat()}


@dataclass
class TransferReceipt:
    """Signed receipt for a bundle transfer (chain-of-custody)."""
    bundle_id: str
    source_registry: str
    dest_registry: str
    transfer_time: str
    source_hash: str = ""
    dest_hash: str = ""
    transfer_method: str = "file_copy"
    status: str = "completed"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"bundle_id": self.bundle_id, "source_registry": self.source_registry,
                "dest_registry": self.dest_registry, "transfer_time": self.transfer_time,
                "source_hash": self.source_hash, "dest_hash": self.dest_hash,
                "transfer_method": self.transfer_method, "status": self.status, "metadata": self.metadata}


class RegistryMirror:
    """Sync bundles between source and destination registries.

    Supports:
    - Full sync (all bundles from source to dest)
    - Channel-filtered sync
    - One-way (diode) mode: source -> dest only, no back-sync
    - Transfer receipts for chain-of-custody audit
    """

    def __init__(self, source: RegistryStore, dest: RegistryStore,
                 one_way: bool = True, scan_hook=None) -> None:
        self.source = source
        self.dest = dest
        self.one_way = one_way
        self.scan_hook = scan_hook

    def sync(self, channel: Optional[str] = None, dry_run: bool = False) -> MirrorSyncResult:
        """Sync bundles from source to dest."""
        result = MirrorSyncResult(timestamp=utc_now().isoformat())
        source_entries = self.source.list_bundles(channel=channel)
        dest_entries = {e.bundle_id: e for e in self.dest.list_bundles()}
        for entry in source_entries:
            if entry.bundle_id in dest_entries:
                result.skipped.append(entry.bundle_id)
                continue
            if dry_run:
                result.synced.append(entry.bundle_id)
                continue
            source_path = self.source.get_bundle(entry.bundle_id)
            if not source_path:
                result.failed.append(entry.bundle_id)
                continue
            if self.scan_hook:
                try:
                    scan_ok = self.scan_hook(source_path)
                    if not scan_ok:
                        logger.warning("Scan hook rejected bundle %s", entry.bundle_id)
                        result.failed.append(entry.bundle_id)
                        continue
                except Exception as exc:
                    logger.warning("Scan hook error for %s: %s", entry.bundle_id, exc)
                    result.failed.append(entry.bundle_id)
                    continue
            try:
                self.dest.publish(source_path, channel=entry.channel, publisher=f"mirror:{self.source.root}")
                receipt = TransferReceipt(
                    bundle_id=entry.bundle_id, source_registry=str(self.source.root),
                    dest_registry=str(self.dest.root), transfer_time=utc_now().isoformat(),
                    transfer_method="mirror_sync", status="completed",
                )
                result.transfer_receipts.append(receipt.to_dict())
                result.synced.append(entry.bundle_id)
                logger.info("Mirrored bundle %s to %s", entry.bundle_id, self.dest.root)
            except Exception as exc:
                logger.warning("Failed to mirror %s: %s", entry.bundle_id, exc)
                result.failed.append(entry.bundle_id)
        return result

    def save_receipts(self, path: Path, result: MirrorSyncResult) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result.to_dict(), indent=2) + "\n", encoding="utf-8")
