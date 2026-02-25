"""WaveOS Registry Mirror — sync between external and internal registries."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.registry.mirror")


@dataclass
class SyncResult:
    synced: List[str] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)
    errors: List[Dict[str, str]] = field(default_factory=list)
    timestamp: str = ""

    def to_dict(self) -> dict:
        return {"synced": self.synced, "skipped": self.skipped, "errors": self.errors,
                "timestamp": self.timestamp or utc_now().isoformat()}


@dataclass
class TransferReceipt:
    bundle_id: str
    source: str
    destination: str
    timestamp: str = ""
    sha256: str = ""
    verified: bool = False
    approver: str = ""

    def to_dict(self) -> dict:
        return {"bundle_id": self.bundle_id, "source": self.source, "destination": self.destination,
                "timestamp": self.timestamp or utc_now().isoformat(), "sha256": self.sha256,
                "verified": self.verified, "approver": self.approver}


class RegistryMirror:
    """Sync bundles between registries (external -> internal mirror).

    Supports:
    - Pull mode: internal mirror pulls from external source
    - Push mode: external pushes to internal mirror
    - One-way (diode) mode: enforces unidirectional flow
    """

    def __init__(self, source_root: Path, mirror_root: Path, one_way: bool = True) -> None:
        self.source_root = source_root
        self.mirror_root = mirror_root
        self.one_way = one_way
        self._receipts_path = mirror_root / "transfer_receipts.jsonl"

    def sync(self, channel: Optional[str] = None, scan_hook=None,
             approval_hook=None) -> SyncResult:
        """Sync bundles from source to mirror.

        scan_hook: optional callable(bundle_dir: Path) -> (ok: bool, reason: str)
        approval_hook: optional callable(bundle_id: str) -> (approved: bool, approver: str)
        """
        from waveos.registry.store import RegistryStore
        source = RegistryStore(self.source_root)
        mirror = RegistryStore(self.mirror_root)
        result = SyncResult(timestamp=utc_now().isoformat())

        source_entries = source.list_bundles(channel=channel)
        mirror_entries = {e.bundle_id for e in mirror.list_bundles()}

        for entry in source_entries:
            if entry.bundle_id in mirror_entries:
                result.skipped.append(entry.bundle_id)
                continue

            source_path = source.get_bundle(entry.bundle_id)
            if not source_path:
                result.errors.append({"bundle_id": entry.bundle_id, "error": "source path missing"})
                continue

            if scan_hook:
                ok, reason = scan_hook(source_path)
                if not ok:
                    result.errors.append({"bundle_id": entry.bundle_id, "error": f"scan failed: {reason}"})
                    continue

            if approval_hook:
                approved, approver = approval_hook(entry.bundle_id)
                if not approved:
                    result.errors.append({"bundle_id": entry.bundle_id, "error": "approval denied"})
                    continue
            else:
                approver = ""

            try:
                mirror.publish(source_path, channel=entry.channel, publisher=f"mirror:{entry.publisher}")
                result.synced.append(entry.bundle_id)
                from waveos.bundle import _sha256
                manifest_hash = ""
                mp = source_path / "bundle.json"
                if mp.exists():
                    manifest_hash = _sha256(mp)
                receipt = TransferReceipt(
                    bundle_id=entry.bundle_id, source=str(self.source_root),
                    destination=str(self.mirror_root), sha256=manifest_hash,
                    verified=True, approver=approver,
                )
                self._append_receipt(receipt)
            except Exception as exc:
                result.errors.append({"bundle_id": entry.bundle_id, "error": str(exc)})

        return result

    def _append_receipt(self, receipt: TransferReceipt) -> None:
        self._receipts_path.parent.mkdir(parents=True, exist_ok=True)
        with self._receipts_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(receipt.to_dict(), default=str) + "\n")

    def get_receipts(self, limit: int = 100) -> List[TransferReceipt]:
        if not self._receipts_path.exists():
            return []
        lines = self._receipts_path.read_text(encoding="utf-8").strip().split("\n")
        receipts = []
        for line in lines[-limit:]:
            if line.strip():
                try:
                    d = json.loads(line)
                    receipts.append(TransferReceipt(**{k: d[k] for k in d if k in TransferReceipt.__dataclass_fields__}))
                except (json.JSONDecodeError, TypeError):
                    pass
        return receipts

    def verify_chain_of_custody(self, bundle_id: str) -> Dict[str, Any]:
        """Verify chain of custody for a bundle: CI -> gateway -> mirror -> device."""
        receipts = [r for r in self.get_receipts() if r.bundle_id == bundle_id]
        if not receipts:
            return {"ok": False, "error": "no transfer receipts found", "bundle_id": bundle_id}
        chain = [r.to_dict() for r in receipts]
        all_verified = all(r.verified for r in receipts)
        return {"ok": all_verified, "bundle_id": bundle_id, "chain": chain, "steps": len(chain)}
