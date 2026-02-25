"""Transfer gateway — pull-from-outside, publish-inside job for DMZ-like zones."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.transfer.gateway")


@dataclass
class GatewayConfig:
    source_dir: Path = Path("out/external_registry")
    dest_dir: Path = Path("out/internal_registry")
    quarantine_dir: Path = Path("out/quarantine")
    scan_enabled: bool = True
    approval_required: bool = True
    allowed_channels: List[str] = field(default_factory=lambda: ["staging", "prod"])
    max_bundle_size_mb: int = 500

    def to_dict(self) -> dict:
        return {
            "source_dir": str(self.source_dir), "dest_dir": str(self.dest_dir),
            "quarantine_dir": str(self.quarantine_dir), "scan_enabled": self.scan_enabled,
            "approval_required": self.approval_required,
            "allowed_channels": self.allowed_channels,
            "max_bundle_size_mb": self.max_bundle_size_mb,
        }


@dataclass
class TransferResult:
    bundle_id: str
    status: str = "pending"  # pending | scanned | approved | transferred | rejected | quarantined
    scan_result: str = ""
    approved_by: str = ""
    checksum: str = ""
    timestamp: str = ""
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "bundle_id": self.bundle_id, "status": self.status,
            "scan_result": self.scan_result, "approved_by": self.approved_by,
            "checksum": self.checksum, "timestamp": self.timestamp or utc_now().isoformat(),
            "error": self.error,
        }


class TransferGateway:
    """Controlled transfer gateway: scans, approves, and publishes bundles from external to internal registry."""

    def __init__(self, config: Optional[GatewayConfig] = None) -> None:
        self.config = config or GatewayConfig()
        self.config.quarantine_dir.mkdir(parents=True, exist_ok=True)
        self._results: List[TransferResult] = []

    def discover_bundles(self) -> List[str]:
        """Discover bundle IDs in source directory."""
        if not self.config.source_dir.is_dir():
            return []
        bundles = []
        bundles_dir = self.config.source_dir / "bundles"
        if bundles_dir.is_dir():
            for d in bundles_dir.iterdir():
                if d.is_dir() and (d / "bundle.json").exists():
                    bundles.append(d.name)
        else:
            for d in self.config.source_dir.iterdir():
                if d.is_dir() and (d / "bundle.json").exists():
                    bundles.append(d.name)
        return bundles

    def _get_bundle_path(self, bundle_id: str) -> Optional[Path]:
        p = self.config.source_dir / "bundles" / bundle_id
        if p.is_dir():
            return p
        p = self.config.source_dir / bundle_id
        if p.is_dir():
            return p
        return None

    def transfer_bundle(
        self,
        bundle_id: str,
        scan_hook: Optional[Callable[[Path], str]] = None,
        approval_hook: Optional[Callable[[str], str]] = None,
    ) -> TransferResult:
        """Transfer a single bundle through the gateway pipeline."""
        result = TransferResult(bundle_id=bundle_id)
        bundle_path = self._get_bundle_path(bundle_id)
        if not bundle_path:
            result.status = "rejected"
            result.error = "Bundle not found in source"
            self._results.append(result)
            return result

        total_size = sum(f.stat().st_size for f in bundle_path.rglob("*") if f.is_file())
        if total_size > self.config.max_bundle_size_mb * 1024 * 1024:
            result.status = "rejected"
            result.error = f"Bundle size {total_size} exceeds limit {self.config.max_bundle_size_mb}MB"
            self._results.append(result)
            return result

        manifest_path = bundle_path / "bundle.json"
        result.checksum = hashlib.sha256(manifest_path.read_bytes()).hexdigest() if manifest_path.exists() else ""

        if self.config.scan_enabled:
            if scan_hook:
                try:
                    scan_result = scan_hook(bundle_path)
                    result.scan_result = scan_result
                    if scan_result not in ("clean", "passed", "ok", ""):
                        result.status = "quarantined"
                        dest = self.config.quarantine_dir / bundle_id
                        if dest.exists():
                            shutil.rmtree(dest)
                        shutil.copytree(bundle_path, dest)
                        self._results.append(result)
                        return result
                except Exception as exc:
                    result.status = "rejected"
                    result.error = f"Scan failed: {exc}"
                    self._results.append(result)
                    return result
            result.scan_result = "passed"
        result.status = "scanned"

        if self.config.approval_required:
            if approval_hook:
                try:
                    approved_by = approval_hook(bundle_id)
                    if not approved_by:
                        result.status = "rejected"
                        result.error = "Approval denied"
                        self._results.append(result)
                        return result
                    result.approved_by = approved_by
                except Exception as exc:
                    result.status = "rejected"
                    result.error = f"Approval failed: {exc}"
                    self._results.append(result)
                    return result
            else:
                result.approved_by = "auto"
        result.status = "approved"

        try:
            from waveos.registry.store import RegistryStore
            dest_store = RegistryStore(self.config.dest_dir)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
            channel = manifest.get("channel", "staging")
            if self.config.allowed_channels and channel not in self.config.allowed_channels:
                channel = self.config.allowed_channels[0] if self.config.allowed_channels else "staging"
            dest_store.publish(bundle_path, channel=channel, publisher=f"gateway:{result.approved_by}")
            result.status = "transferred"
        except Exception as exc:
            result.status = "rejected"
            result.error = f"Publish failed: {exc}"

        result.timestamp = utc_now().isoformat()
        self._results.append(result)
        return result

    def transfer_all(self, scan_hook=None, approval_hook=None) -> List[TransferResult]:
        results = []
        for bundle_id in self.discover_bundles():
            results.append(self.transfer_bundle(bundle_id, scan_hook=scan_hook, approval_hook=approval_hook))
        return results

    def get_results(self) -> List[TransferResult]:
        return list(self._results)
