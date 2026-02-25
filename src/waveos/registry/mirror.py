"""WaveOS Registry Mirror — sync between registries for controlled-transfer environments."""

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
    failed: List[str] = field(default_factory=list)
    timestamp: str = ""

    def to_dict(self) -> dict:
        return {
            "synced": self.synced,
            "skipped": self.skipped,
            "failed": self.failed,
            "timestamp": self.timestamp or utc_now().isoformat(),
            "total_synced": len(self.synced),
            "total_skipped": len(self.skipped),
            "total_failed": len(self.failed),
        }


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
        return {
            "bundle_id": self.bundle_id,
            "source": self.source,
            "destination": self.destination,
            "timestamp": self.timestamp or utc_now().isoformat(),
            "sha256": self.sha256,
            "verified": self.verified,
            "approver": self.approver,
        }


class RegistryMirror:
    """Sync bundles between registries (push from source to destination).
    
    Supports:
    - Full sync (all bundles)
    - Channel-filtered sync
    - One-way (data diode) mode
    - Transfer receipts for chain-of-custody
    """

    def __init__(self, source_root: Path, dest_root: Path) -> None:
        self.source_root = source_root
        self.dest_root = dest_root
        self._receipts: List[TransferReceipt] = []

    def sync(
        self,
        channel: Optional[str] = None,
        verify_signatures: bool = True,
        hmac_key: Optional[str] = None,
        approver: str = "",
        scan_hook: Optional[callable] = None,
    ) -> SyncResult:
        """Sync bundles from source to destination registry."""
        from waveos.registry.store import RegistryStore
        
        source = RegistryStore(self.source_root)
        dest = RegistryStore(self.dest_root)
        
        entries = source.list_bundles(channel=channel)
        dest_entries = {e.bundle_id for e in dest.list_bundles()}
        
        result = SyncResult(timestamp=utc_now().isoformat())
        
        for entry in entries:
            if entry.bundle_id in dest_entries:
                result.skipped.append(entry.bundle_id)
                continue
            
            source_path = source.get_bundle(entry.bundle_id)
            if not source_path:
                result.failed.append(entry.bundle_id)
                continue
            
            if verify_signatures and hmac_key:
                from waveos.bundle import verify_manifest
                if not verify_manifest(source_path, hmac_key):
                    logger.warning("Signature verification failed for %s, skipping", entry.bundle_id)
                    result.failed.append(entry.bundle_id)
                    continue
            
            if scan_hook:
                try:
                    scan_ok = scan_hook(source_path)
                    if not scan_ok:
                        logger.warning("Scan hook rejected %s", entry.bundle_id)
                        result.failed.append(entry.bundle_id)
                        continue
                except Exception as exc:
                    logger.warning("Scan hook error for %s: %s", entry.bundle_id, exc)
                    result.failed.append(entry.bundle_id)
                    continue
            
            try:
                dest.publish(source_path, channel=entry.channel, publisher=f"mirror:{approver or 'auto'}")
                
                import hashlib
                manifest_path = source_path / "bundle.json"
                sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest() if manifest_path.exists() else ""
                
                receipt = TransferReceipt(
                    bundle_id=entry.bundle_id,
                    source=str(self.source_root),
                    destination=str(self.dest_root),
                    sha256=sha,
                    verified=True,
                    approver=approver,
                )
                self._receipts.append(receipt)
                result.synced.append(entry.bundle_id)
                logger.info("Synced %s to mirror", entry.bundle_id)
            except Exception as exc:
                logger.warning("Failed to sync %s: %s", entry.bundle_id, exc)
                result.failed.append(entry.bundle_id)
        
        return result

    def get_receipts(self) -> List[TransferReceipt]:
        return list(self._receipts)

    def save_receipts(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = [r.to_dict() for r in self._receipts]
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    def save_sync_log(self, result: SyncResult, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(result.to_dict(), default=str) + "\n")
