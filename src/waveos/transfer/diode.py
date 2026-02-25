"""Data diode / one-way sync mode for classified environments."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.transfer.diode")


class DiodeDirection(str, Enum):
    PUSH = "push"   # outside pushes to inside
    PULL = "pull"   # inside pulls from outside drop point


@dataclass
class DiodeSyncConfig:
    direction: DiodeDirection = DiodeDirection.PUSH
    source_dir: Path = Path("/opt/waveos/diode/incoming")
    mirror_registry_root: Path = Path("/opt/waveos/mirror")
    processed_dir: Path = Path("/opt/waveos/diode/processed")
    channel: str = "prod"
    require_signature: bool = True
    hmac_key: str = ""
    poll_interval_sec: int = 60

    def to_dict(self) -> dict:
        return {
            "direction": self.direction.value,
            "source_dir": str(self.source_dir),
            "mirror_registry_root": str(self.mirror_registry_root),
            "processed_dir": str(self.processed_dir),
            "channel": self.channel,
            "require_signature": self.require_signature,
            "poll_interval_sec": self.poll_interval_sec,
        }


class DiodeSyncManager:
    """Manages one-way sync from diode drop point to internal mirror registry."""

    def __init__(self, config: DiodeSyncConfig) -> None:
        self.config = config
        self._sync_log: List[Dict[str, Any]] = []
        config.source_dir.mkdir(parents=True, exist_ok=True)
        config.mirror_registry_root.mkdir(parents=True, exist_ok=True)
        config.processed_dir.mkdir(parents=True, exist_ok=True)

    def scan_incoming(self) -> List[Path]:
        """Scan source directory for new bundles to sync."""
        bundles: List[Path] = []
        for item in sorted(self.config.source_dir.iterdir()):
            if item.is_dir() and (item / "bundle.json").exists():
                bundles.append(item)
        return bundles

    def verify_bundle(self, bundle_dir: Path) -> Dict[str, Any]:
        """Verify bundle before syncing."""
        manifest_path = bundle_dir / "bundle.json"
        if not manifest_path.exists():
            return {"ok": False, "error": "No manifest"}
        if self.config.require_signature:
            sig_path = bundle_dir / "bundle.sig"
            if not sig_path.exists():
                return {"ok": False, "error": "Signature required but missing"}
            if self.config.hmac_key:
                from waveos.bundle import verify_manifest
                if not verify_manifest(bundle_dir, self.config.hmac_key):
                    return {"ok": False, "error": "Signature verification failed"}
        return {"ok": True}

    def sync_bundle(self, bundle_dir: Path) -> Dict[str, Any]:
        """Sync a single bundle to the mirror registry."""
        verify = self.verify_bundle(bundle_dir)
        if not verify.get("ok"):
            return verify
        try:
            from waveos.registry.store import RegistryStore
            store = RegistryStore(self.config.mirror_registry_root)
            entry = store.publish(bundle_dir, channel=self.config.channel, publisher="diode-sync")
            processed = self.config.processed_dir / bundle_dir.name
            if processed.exists():
                shutil.rmtree(processed)
            shutil.move(str(bundle_dir), str(processed))
            record = {
                "timestamp": utc_now().isoformat(),
                "bundle_id": entry.bundle_id,
                "channel": self.config.channel,
                "source": str(bundle_dir),
                "direction": self.config.direction.value,
                "content_hash": hashlib.sha256(json.dumps(entry.to_dict(), sort_keys=True).encode()).hexdigest(),
            }
            self._sync_log.append(record)
            logger.info("Diode sync: %s -> mirror", entry.bundle_id)
            return {"ok": True, "entry": entry.to_dict(), "record": record}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def sync_all(self) -> List[Dict[str, Any]]:
        """Sync all incoming bundles."""
        results = []
        for bundle_dir in self.scan_incoming():
            results.append(self.sync_bundle(bundle_dir))
        return results

    def get_sync_log(self) -> List[Dict[str, Any]]:
        return list(self._sync_log)

    def save_sync_log(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self._sync_log, indent=2) + "\n", encoding="utf-8")
