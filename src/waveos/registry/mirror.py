"""WaveOS Registry Mirror — sync bundles between registries for controlled-transfer environments."""

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
    timestamp: str = ""
    source: str = ""
    destination: str = ""
    bundles_synced: List[str] = field(default_factory=list)
    bundles_skipped: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    direction: str = "pull"  # pull | push | one_way

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp or utc_now().isoformat(),
            "source": self.source,
            "destination": self.destination,
            "bundles_synced": self.bundles_synced,
            "bundles_skipped": self.bundles_skipped,
            "errors": self.errors,
            "direction": self.direction,
        }


@dataclass
class TransferReceipt:
    """Signed receipt for a controlled transfer."""
    transfer_id: str
    bundle_id: str
    source_registry: str
    dest_registry: str
    timestamp: str = ""
    checksum: str = ""
    scan_result: str = ""
    approved_by: str = ""

    def to_dict(self) -> dict:
        return {
            "transfer_id": self.transfer_id,
            "bundle_id": self.bundle_id,
            "source_registry": self.source_registry,
            "dest_registry": self.dest_registry,
            "timestamp": self.timestamp or utc_now().isoformat(),
            "checksum": self.checksum,
            "scan_result": self.scan_result,
            "approved_by": self.approved_by,
        }

    @classmethod
    def from_dict(cls, d: dict) -> TransferReceipt:
        return cls(**{k: d[k] for k in d if k in cls.__dataclass_fields__})


class RegistryMirror:
    """Syncs bundles between a source and destination registry."""

    def __init__(self, source: RegistryStore, destination: RegistryStore) -> None:
        self.source = source
        self.destination = destination
        self._receipts: List[TransferReceipt] = []

    def sync(
        self,
        channel: Optional[str] = None,
        one_way: bool = False,
        scan_hook=None,
        approval_hook=None,
    ) -> MirrorSyncResult:
        """Sync bundles from source to destination.
        scan_hook: optional callable(bundle_dir) -> str ("clean"|"infected"|...)
        approval_hook: optional callable(bundle_id) -> str (approver name or "")
        one_way: data diode mode (source → dest only, no metadata flows back)
        """
        result = MirrorSyncResult(
            source=str(self.source.root),
            destination=str(self.destination.root),
            direction="one_way" if one_way else "pull",
        )
        source_entries = self.source.list_bundles(channel=channel)
        dest_entries = {e.bundle_id for e in self.destination.list_bundles()}

        for entry in source_entries:
            if entry.bundle_id in dest_entries:
                result.bundles_skipped.append(entry.bundle_id)
                continue
            bundle_path = self.source.get_bundle(entry.bundle_id)
            if not bundle_path:
                result.errors.append(f"Source bundle dir missing: {entry.bundle_id}")
                continue
            scan_result = ""
            if scan_hook:
                try:
                    scan_result = scan_hook(bundle_path)
                    if scan_result not in ("clean", "passed", "ok", ""):
                        result.errors.append(f"Scan blocked {entry.bundle_id}: {scan_result}")
                        continue
                except Exception as exc:
                    result.errors.append(f"Scan error {entry.bundle_id}: {exc}")
                    continue
            approved_by = ""
            if approval_hook:
                try:
                    approved_by = approval_hook(entry.bundle_id)
                    if not approved_by:
                        result.errors.append(f"Approval denied for {entry.bundle_id}")
                        continue
                except Exception as exc:
                    result.errors.append(f"Approval error {entry.bundle_id}: {exc}")
                    continue
            try:
                self.destination.publish(bundle_path, channel=entry.channel, publisher=f"mirror:{entry.publisher}")
                result.bundles_synced.append(entry.bundle_id)
                import hashlib
                checksum = ""
                manifest_path = bundle_path / "bundle.json"
                if manifest_path.exists():
                    checksum = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
                receipt = TransferReceipt(
                    transfer_id=f"xfer-{utc_now().strftime('%Y%m%d%H%M%S')}-{entry.bundle_id}",
                    bundle_id=entry.bundle_id,
                    source_registry=str(self.source.root),
                    dest_registry=str(self.destination.root),
                    checksum=checksum,
                    scan_result=scan_result,
                    approved_by=approved_by,
                )
                self._receipts.append(receipt)
            except Exception as exc:
                result.errors.append(f"Publish failed {entry.bundle_id}: {exc}")

        result.timestamp = utc_now().isoformat()
        return result

    def get_receipts(self) -> List[TransferReceipt]:
        return list(self._receipts)

    def save_receipts(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = [r.to_dict() for r in self._receipts]
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    def load_receipts(self, path: Path) -> None:
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self._receipts = [TransferReceipt.from_dict(r) for r in data]
        except (json.JSONDecodeError, KeyError):
            pass
