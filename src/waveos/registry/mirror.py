"""WaveOS Registry Mirror — sync bundles between registries for controlled-transfer environments."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from waveos.registry.store import RegistryStore
from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.registry.mirror")


@dataclass
class SyncResult:
    synced: List[str] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)
    failed: List[str] = field(default_factory=list)
    timestamp: str = ""

    def to_dict(self) -> dict:
        return {"synced": self.synced, "skipped": self.skipped, "failed": self.failed, "timestamp": self.timestamp or utc_now().isoformat()}


@dataclass
class TransferReceipt:
    bundle_id: str
    source_registry: str
    target_registry: str
    sha256: str
    transferred_at: str = ""
    transferred_by: str = ""
    scan_result: str = "not_scanned"  # not_scanned | clean | flagged | blocked
    approval_status: str = "auto"  # auto | pending | approved | rejected

    def to_dict(self) -> dict:
        return {
            "bundle_id": self.bundle_id,
            "source_registry": self.source_registry,
            "target_registry": self.target_registry,
            "sha256": self.sha256,
            "transferred_at": self.transferred_at or utc_now().isoformat(),
            "transferred_by": self.transferred_by,
            "scan_result": self.scan_result,
            "approval_status": self.approval_status,
        }


class MirrorSync:
    """Synchronize bundles between two file-system registries.

    Supports:
    - Full sync (all bundles from source to target)
    - Channel-filtered sync
    - One-way mode (data diode simulation)
    - Scanning hooks (callback before import)
    - Transfer receipts for chain-of-custody
    """

    def __init__(
        self,
        source: RegistryStore,
        target: RegistryStore,
        one_way: bool = True,
        scan_hook=None,
        approval_hook=None,
    ) -> None:
        self.source = source
        self.target = target
        self.one_way = one_way
        self._scan_hook = scan_hook
        self._approval_hook = approval_hook
        self._receipts: List[TransferReceipt] = []

    def sync(self, channel: Optional[str] = None) -> SyncResult:
        """Sync bundles from source to target."""
        result = SyncResult(timestamp=utc_now().isoformat())
        source_entries = self.source.list_bundles(channel=channel)
        target_entries = self.target.list_bundles()
        target_ids = {e.bundle_id for e in target_entries}

        for entry in source_entries:
            if entry.bundle_id in target_ids:
                result.skipped.append(entry.bundle_id)
                continue
            bundle_path = self.source.get_bundle(entry.bundle_id)
            if not bundle_path:
                result.failed.append(entry.bundle_id)
                continue

            manifest_bytes = (bundle_path / "bundle.json").read_bytes() if (bundle_path / "bundle.json").exists() else b""
            bundle_sha = hashlib.sha256(manifest_bytes).hexdigest()

            scan_result = "not_scanned"
            if self._scan_hook:
                try:
                    scan_result = self._scan_hook(bundle_path)
                    if scan_result == "blocked":
                        result.failed.append(entry.bundle_id)
                        self._receipts.append(TransferReceipt(
                            bundle_id=entry.bundle_id,
                            source_registry=str(self.source.root),
                            target_registry=str(self.target.root),
                            sha256=bundle_sha,
                            scan_result="blocked",
                        ))
                        continue
                except Exception as exc:
                    logger.warning("Scan hook failed for %s: %s", entry.bundle_id, exc)
                    scan_result = "error"

            approval = "auto"
            if self._approval_hook:
                try:
                    approval = self._approval_hook(entry.bundle_id, entry.channel)
                    if approval == "rejected":
                        result.failed.append(entry.bundle_id)
                        continue
                except Exception:
                    approval = "auto"

            try:
                self.target.publish(bundle_path, channel=entry.channel, publisher=f"mirror:{self.source.root}")
                result.synced.append(entry.bundle_id)
                self._receipts.append(TransferReceipt(
                    bundle_id=entry.bundle_id,
                    source_registry=str(self.source.root),
                    target_registry=str(self.target.root),
                    sha256=bundle_sha,
                    scan_result=scan_result,
                    approval_status=approval,
                ))
            except Exception as exc:
                logger.warning("Failed to sync %s: %s", entry.bundle_id, exc)
                result.failed.append(entry.bundle_id)

        return result

    @property
    def receipts(self) -> List[TransferReceipt]:
        return list(self._receipts)

    def write_receipts(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            for r in self._receipts:
                f.write(json.dumps(r.to_dict(), default=str) + "\n")

    def write_chain_of_custody(self, path: Path) -> None:
        """Write full chain-of-custody manifest."""
        chain = {
            "type": "chain_of_custody",
            "timestamp": utc_now().isoformat(),
            "source_registry": str(self.source.root),
            "target_registry": str(self.target.root),
            "one_way": self.one_way,
            "transfers": [r.to_dict() for r in self._receipts],
            "total_synced": sum(1 for r in self._receipts if r.scan_result != "blocked"),
            "total_blocked": sum(1 for r in self._receipts if r.scan_result == "blocked"),
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(chain, indent=2) + "\n", encoding="utf-8")
