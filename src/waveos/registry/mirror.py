"""WaveOS Registry Mirror — sync between registries for controlled-transfer environments."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.registry.mirror")


@dataclass
class SyncResult:
    """Result of a mirror sync operation."""
    synced: List[str] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)
    failed: List[str] = field(default_factory=list)
    transfer_receipts: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"synced": self.synced, "skipped": self.skipped, "failed": self.failed, "transfer_receipts": self.transfer_receipts, "timestamp": utc_now().isoformat()}


@dataclass
class TransferReceipt:
    """Signed receipt for a bundle transfer (chain-of-custody)."""
    bundle_id: str
    source: str
    destination: str
    timestamp: str = ""
    sha256: str = ""
    transfer_method: str = "mirror_sync"
    scan_result: str = "not_scanned"
    approved_by: str = ""

    def to_dict(self) -> dict:
        return {
            "bundle_id": self.bundle_id, "source": self.source, "destination": self.destination,
            "timestamp": self.timestamp or utc_now().isoformat(), "sha256": self.sha256,
            "transfer_method": self.transfer_method, "scan_result": self.scan_result, "approved_by": self.approved_by,
        }

    @classmethod
    def from_dict(cls, d: dict) -> TransferReceipt:
        return cls(**{k: d[k] for k in d if k in cls.__dataclass_fields__})


class RegistryMirror:
    """Sync bundles between source and destination registries (file-system based).

    Supports:
    - Full sync (copy all bundles from source to dest)
    - Channel-filtered sync
    - One-way (diode) mode: source → dest only, never writes back
    - Scan hooks (pre-copy validation)
    - Transfer receipts for chain-of-custody
    """

    def __init__(self, source_root: Path, dest_root: Path, one_way: bool = True) -> None:
        self.source_root = source_root
        self.dest_root = dest_root
        self.one_way = one_way
        self._scan_hooks: List[Any] = []

    def add_scan_hook(self, hook) -> None:
        """Add a scan hook: callable(bundle_dir: Path) -> (ok: bool, message: str)."""
        self._scan_hooks.append(hook)

    def _run_scans(self, bundle_dir: Path) -> tuple[bool, str]:
        for hook in self._scan_hooks:
            try:
                ok, msg = hook(bundle_dir)
                if not ok:
                    return False, msg
            except Exception as exc:
                return False, f"Scan hook failed: {exc}"
        return True, "passed" if self._scan_hooks else "not_scanned"

    def _bundle_hash(self, bundle_dir: Path) -> str:
        manifest = bundle_dir / "bundle.json"
        if manifest.exists():
            return hashlib.sha256(manifest.read_bytes()).hexdigest()
        return ""

    def sync(self, channel: Optional[str] = None, approved_by: str = "") -> SyncResult:
        """Sync bundles from source to destination."""
        result = SyncResult()
        source_index_path = self.source_root / "index.json"
        if not source_index_path.exists():
            logger.warning("No source index at %s", source_index_path)
            return result

        source_entries = json.loads(source_index_path.read_text(encoding="utf-8"))
        if channel:
            source_entries = [e for e in source_entries if e.get("channel") == channel]

        dest_index_path = self.dest_root / "index.json"
        self.dest_root.mkdir(parents=True, exist_ok=True)
        dest_entries = []
        if dest_index_path.exists():
            try:
                dest_entries = json.loads(dest_index_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass
        dest_ids = {e.get("bundle_id") for e in dest_entries}

        for entry in source_entries:
            bid = entry.get("bundle_id", "")
            src_bundle = self.source_root / "bundles" / bid
            if not src_bundle.is_dir():
                result.skipped.append(bid)
                continue
            if bid in dest_ids:
                result.skipped.append(bid)
                continue
            scan_ok, scan_msg = self._run_scans(src_bundle)
            if not scan_ok:
                logger.warning("Bundle %s failed scan: %s", bid, scan_msg)
                result.failed.append(bid)
                continue
            dest_bundle = self.dest_root / "bundles" / bid
            try:
                if dest_bundle.exists():
                    shutil.rmtree(dest_bundle)
                shutil.copytree(src_bundle, dest_bundle)
                receipt = TransferReceipt(
                    bundle_id=bid, source=str(self.source_root), destination=str(self.dest_root),
                    sha256=self._bundle_hash(dest_bundle), scan_result=scan_msg, approved_by=approved_by,
                )
                result.transfer_receipts.append(receipt.to_dict())
                dest_entries.append(entry)
                result.synced.append(bid)
                logger.info("Synced bundle %s", bid)
            except (OSError, shutil.Error) as exc:
                logger.error("Failed to sync bundle %s: %s", bid, exc)
                result.failed.append(bid)

        dest_index_path.write_text(json.dumps(dest_entries, indent=2) + "\n", encoding="utf-8")
        return result

    def write_sync_log(self, result: SyncResult, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(result.to_dict(), default=str) + "\n")
