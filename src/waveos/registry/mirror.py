"""WaveOS Registry Mirror — sync bundles between registries for controlled-transfer environments."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.registry.mirror")


@dataclass
class TransferReceipt:
    """Signed receipt for a bundle transfer between registries."""
    bundle_id: str
    source_registry: str
    dest_registry: str
    transfer_time: str = ""
    transfer_method: str = "push"
    bundle_hash: str = ""
    verified: bool = False
    scanned: bool = False
    scan_result: str = ""
    approved_by: str = ""
    chain_of_custody: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "bundle_id": self.bundle_id,
            "source_registry": self.source_registry,
            "dest_registry": self.dest_registry,
            "transfer_time": self.transfer_time or utc_now().isoformat(),
            "transfer_method": self.transfer_method,
            "bundle_hash": self.bundle_hash,
            "verified": self.verified,
            "scanned": self.scanned,
            "scan_result": self.scan_result,
            "approved_by": self.approved_by,
            "chain_of_custody": self.chain_of_custody,
        }

    @classmethod
    def from_dict(cls, d: dict) -> TransferReceipt:
        return cls(**{k: d[k] for k in d if k in cls.__dataclass_fields__})


class RegistryMirror:
    """Manages bundle synchronization between outside and inside registries.

    Supports:
    - Push mode: outside -> inside (for CDS/gateway)
    - Pull mode: inside pulls from outside
    - One-way (diode): only metadata + bundles flow inward
    """

    def __init__(self, source_root: Path, dest_root: Path, mode: str = "push") -> None:
        self.source_root = source_root
        self.dest_root = dest_root
        self.mode = mode
        self._receipts_path = dest_root / "transfer_receipts.jsonl"

    def _load_source_index(self) -> List[Dict[str, Any]]:
        index_path = self.source_root / "index.json"
        if not index_path.exists():
            return []
        return json.loads(index_path.read_text(encoding="utf-8"))

    def _load_dest_index(self) -> List[Dict[str, Any]]:
        index_path = self.dest_root / "index.json"
        if not index_path.exists():
            return []
        return json.loads(index_path.read_text(encoding="utf-8"))

    def _append_receipt(self, receipt: TransferReceipt) -> None:
        self._receipts_path.parent.mkdir(parents=True, exist_ok=True)
        with self._receipts_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(receipt.to_dict(), default=str) + "\n")

    def diff(self) -> List[str]:
        """Return bundle IDs present in source but not in dest."""
        source_ids = {e.get("bundle_id") for e in self._load_source_index()}
        dest_ids = {e.get("bundle_id") for e in self._load_dest_index()}
        return sorted(source_ids - dest_ids)

    def sync(
        self,
        channel: Optional[str] = None,
        scan_hook=None,
        approval_hook=None,
        one_way: bool = False,
    ) -> List[TransferReceipt]:
        """Sync bundles from source to dest.

        scan_hook: optional callable(bundle_dir) -> (ok, result_str)
        approval_hook: optional callable(bundle_id) -> (approved, approver_name)
        one_way: if True, never sync from dest to source (diode mode)
        """
        from waveos.registry.store import RegistryStore
        source_store = RegistryStore(self.source_root)
        dest_store = RegistryStore(self.dest_root)

        source_entries = source_store.list_bundles(channel=channel)
        dest_ids = {e.bundle_id for e in dest_store.list_bundles()}

        receipts: List[TransferReceipt] = []
        for entry in source_entries:
            if entry.bundle_id in dest_ids:
                continue

            bundle_path = source_store.get_bundle(entry.bundle_id)
            if not bundle_path:
                continue

            scanned = False
            scan_result = ""
            if scan_hook:
                ok, scan_result = scan_hook(bundle_path)
                scanned = True
                if not ok:
                    logger.warning("Scan failed for %s: %s", entry.bundle_id, scan_result)
                    receipt = TransferReceipt(
                        bundle_id=entry.bundle_id,
                        source_registry=str(self.source_root),
                        dest_registry=str(self.dest_root),
                        transfer_method=self.mode,
                        scanned=True,
                        scan_result=scan_result,
                        verified=False,
                    )
                    receipts.append(receipt)
                    self._append_receipt(receipt)
                    continue

            approved_by = ""
            if approval_hook:
                approved, approver = approval_hook(entry.bundle_id)
                if not approved:
                    logger.info("Transfer not approved for %s", entry.bundle_id)
                    continue
                approved_by = approver

            import hashlib
            bundle_hash = ""
            manifest_path = bundle_path / "bundle.json"
            if manifest_path.exists():
                bundle_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()

            dest_entry = dest_store.publish(bundle_path, channel=entry.channel, publisher=f"mirror:{entry.publisher}")

            chain = [
                {"stage": "source", "registry": str(self.source_root), "timestamp": entry.published_at},
                {"stage": "transfer", "method": self.mode, "timestamp": utc_now().isoformat()},
                {"stage": "dest", "registry": str(self.dest_root), "timestamp": dest_entry.published_at},
            ]

            receipt = TransferReceipt(
                bundle_id=entry.bundle_id,
                source_registry=str(self.source_root),
                dest_registry=str(self.dest_root),
                transfer_method=self.mode,
                bundle_hash=bundle_hash,
                verified=True,
                scanned=scanned,
                scan_result=scan_result,
                approved_by=approved_by,
                chain_of_custody=chain,
            )
            receipts.append(receipt)
            self._append_receipt(receipt)
            logger.info("Mirrored %s from %s to %s", entry.bundle_id, self.source_root, self.dest_root)

        return receipts

    def get_receipts(self, limit: int = 100) -> List[TransferReceipt]:
        if not self._receipts_path.exists():
            return []
        lines = self._receipts_path.read_text(encoding="utf-8").strip().split("\n")
        receipts = []
        for line in lines[-limit:]:
            if line.strip():
                try:
                    receipts.append(TransferReceipt.from_dict(json.loads(line)))
                except (json.JSONDecodeError, KeyError):
                    pass
        return receipts
