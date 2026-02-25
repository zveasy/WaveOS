"""WaveOS Registry Mirror — sync between registries for controlled-transfer environments."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from waveos.registry.store import RegistryStore
from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.registry.mirror")


class SyncDirection(str, Enum):
    PULL = "pull"
    PUSH = "push"
    ONE_WAY = "one_way"


@dataclass
class SyncResult:
    """Result of a mirror sync operation."""
    synced: List[str] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)
    errors: List[Dict[str, Any]] = field(default_factory=list)
    timestamp: str = ""
    direction: str = ""

    def to_dict(self) -> dict:
        return {
            "synced": self.synced, "skipped": self.skipped,
            "errors": [e for e in self.errors],
            "timestamp": self.timestamp or utc_now().isoformat(),
            "direction": self.direction,
        }


@dataclass
class TransferReceipt:
    """Signed receipt for a transfer operation (chain-of-custody)."""
    receipt_id: str
    bundle_id: str
    source_registry: str
    dest_registry: str
    timestamp: str
    direction: str
    sha256_manifest: str = ""
    transfer_agent: str = ""
    approval_ref: str = ""
    scan_result: str = ""

    def to_dict(self) -> dict:
        return {
            "receipt_id": self.receipt_id, "bundle_id": self.bundle_id,
            "source_registry": self.source_registry, "dest_registry": self.dest_registry,
            "timestamp": self.timestamp, "direction": self.direction,
            "sha256_manifest": self.sha256_manifest, "transfer_agent": self.transfer_agent,
            "approval_ref": self.approval_ref, "scan_result": self.scan_result,
        }

    @classmethod
    def from_dict(cls, d: dict) -> TransferReceipt:
        return cls(**{k: d[k] for k in d if k in cls.__dataclass_fields__})


class RegistryMirror:
    """Synchronizes bundles between registries for controlled-transfer environments.

    Supports:
    - pull: pull bundles from source to local mirror
    - push: push bundles from local to destination
    - one_way: data diode mode (pull only, no feedback)
    """

    def __init__(
        self,
        source: RegistryStore,
        destination: RegistryStore,
        direction: SyncDirection = SyncDirection.PULL,
        scan_hook=None,
        approval_hook=None,
    ) -> None:
        self.source = source
        self.destination = destination
        self.direction = direction
        self.scan_hook = scan_hook
        self.approval_hook = approval_hook
        self._receipts: List[TransferReceipt] = []

    def sync(
        self,
        channel: Optional[str] = None,
        bundle_ids: Optional[List[str]] = None,
    ) -> SyncResult:
        """Synchronize bundles from source to destination."""
        result = SyncResult(direction=self.direction.value)

        source_entries = self.source.list_bundles(channel=channel)
        dest_entries = {e.bundle_id for e in self.destination.list_bundles()}

        for entry in source_entries:
            if bundle_ids and entry.bundle_id not in bundle_ids:
                result.skipped.append(entry.bundle_id)
                continue
            if entry.bundle_id in dest_entries:
                result.skipped.append(entry.bundle_id)
                continue
            source_path = self.source.get_bundle(entry.bundle_id)
            if not source_path:
                result.errors.append({"bundle_id": entry.bundle_id, "error": "Source path not found"})
                continue

            if self.scan_hook:
                try:
                    scan_ok = self.scan_hook(source_path)
                    if not scan_ok:
                        result.errors.append({"bundle_id": entry.bundle_id, "error": "Scan rejected"})
                        continue
                except Exception as exc:
                    result.errors.append({"bundle_id": entry.bundle_id, "error": f"Scan failed: {exc}"})
                    continue

            if self.approval_hook:
                try:
                    approved = self.approval_hook(entry.bundle_id, entry.channel)
                    if not approved:
                        result.errors.append({"bundle_id": entry.bundle_id, "error": "Approval denied"})
                        continue
                except Exception as exc:
                    result.errors.append({"bundle_id": entry.bundle_id, "error": f"Approval failed: {exc}"})
                    continue

            try:
                self.destination.publish(source_path, channel=entry.channel, publisher=f"mirror:{self.direction.value}")
                result.synced.append(entry.bundle_id)

                import hashlib
                manifest_path = source_path / "bundle.json"
                manifest_hash = ""
                if manifest_path.exists():
                    manifest_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()

                receipt = TransferReceipt(
                    receipt_id=f"xfer-{utc_now().strftime('%Y%m%d%H%M%S')}-{entry.bundle_id[:8]}",
                    bundle_id=entry.bundle_id,
                    source_registry=str(self.source.root),
                    dest_registry=str(self.destination.root),
                    timestamp=utc_now().isoformat(),
                    direction=self.direction.value,
                    sha256_manifest=manifest_hash,
                    transfer_agent="waveos-mirror",
                    scan_result="passed" if self.scan_hook else "not_scanned",
                )
                self._receipts.append(receipt)
            except Exception as exc:
                result.errors.append({"bundle_id": entry.bundle_id, "error": str(exc)})

        result.timestamp = utc_now().isoformat()
        return result

    @property
    def receipts(self) -> List[TransferReceipt]:
        return list(self._receipts)

    def save_receipts(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps([r.to_dict() for r in self._receipts], indent=2) + "\n",
            encoding="utf-8",
        )

    def load_receipts(self, path: Path) -> None:
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                self._receipts = [TransferReceipt.from_dict(r) for r in data]
            except (json.JSONDecodeError, KeyError):
                pass
