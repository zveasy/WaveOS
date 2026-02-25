"""Transfer gateway — pull-from-outside, scan, approve, publish-inside."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from waveos.registry.store import RegistryStore
from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.transfer.gateway")


@dataclass
class GatewayConfig:
    """Configuration for the transfer gateway."""
    source_registry: Path = Path("out/external_registry")
    dest_registry: Path = Path("out/internal_registry")
    quarantine_dir: Path = Path("out/transfer_quarantine")
    receipts_path: Path = Path("out/transfer_receipts.jsonl")
    require_scan: bool = True
    require_approval: bool = False
    allowed_channels: List[str] = field(default_factory=lambda: ["dev", "staging", "prod"])
    one_way: bool = False

    def to_dict(self) -> dict:
        return {
            "source_registry": str(self.source_registry),
            "dest_registry": str(self.dest_registry),
            "quarantine_dir": str(self.quarantine_dir),
            "receipts_path": str(self.receipts_path),
            "require_scan": self.require_scan,
            "require_approval": self.require_approval,
            "allowed_channels": self.allowed_channels,
            "one_way": self.one_way,
        }


@dataclass
class TransferResult:
    bundle_id: str
    status: str  # transferred | quarantined | rejected | error
    reason: str = ""
    receipt_id: str = ""
    timestamp: str = ""

    def to_dict(self) -> dict:
        return {
            "bundle_id": self.bundle_id, "status": self.status,
            "reason": self.reason, "receipt_id": self.receipt_id,
            "timestamp": self.timestamp or utc_now().isoformat(),
        }


class TransferGateway:
    """DMZ-zone transfer gateway: pull from outside, scan, approve, publish inside."""

    def __init__(
        self,
        config: GatewayConfig,
        scan_fn: Optional[Callable[[Path], bool]] = None,
        approval_fn: Optional[Callable[[str, str], bool]] = None,
    ) -> None:
        self.config = config
        self.scan_fn = scan_fn
        self.approval_fn = approval_fn
        self.source = RegistryStore(config.source_registry)
        self.dest = RegistryStore(config.dest_registry)
        self.config.quarantine_dir.mkdir(parents=True, exist_ok=True)
        self._results: List[TransferResult] = []

    def _write_receipt(self, result: TransferResult) -> None:
        self.config.receipts_path.parent.mkdir(parents=True, exist_ok=True)
        with self.config.receipts_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(result.to_dict(), default=str) + "\n")

    def transfer_bundle(self, bundle_id: str) -> TransferResult:
        """Transfer a single bundle through the gateway pipeline."""
        source_path = self.source.get_bundle(bundle_id)
        if not source_path:
            result = TransferResult(bundle_id=bundle_id, status="error", reason="Not found in source registry")
            self._results.append(result)
            return result

        entry = self.source.get_entry(bundle_id)
        channel = entry.channel if entry else "dev"
        if channel not in self.config.allowed_channels:
            result = TransferResult(bundle_id=bundle_id, status="rejected", reason=f"Channel {channel} not allowed")
            self._results.append(result)
            self._write_receipt(result)
            return result

        if self.config.require_scan and self.scan_fn:
            try:
                scan_ok = self.scan_fn(source_path)
                if not scan_ok:
                    import shutil
                    quarantine_dest = self.config.quarantine_dir / bundle_id
                    if quarantine_dest.exists():
                        shutil.rmtree(quarantine_dest)
                    shutil.copytree(source_path, quarantine_dest)
                    result = TransferResult(bundle_id=bundle_id, status="quarantined", reason="Scan failed")
                    self._results.append(result)
                    self._write_receipt(result)
                    return result
            except Exception as exc:
                result = TransferResult(bundle_id=bundle_id, status="error", reason=f"Scan error: {exc}")
                self._results.append(result)
                self._write_receipt(result)
                return result

        if self.config.require_approval and self.approval_fn:
            try:
                approved = self.approval_fn(bundle_id, channel)
                if not approved:
                    result = TransferResult(bundle_id=bundle_id, status="rejected", reason="Approval denied")
                    self._results.append(result)
                    self._write_receipt(result)
                    return result
            except Exception as exc:
                result = TransferResult(bundle_id=bundle_id, status="error", reason=f"Approval error: {exc}")
                self._results.append(result)
                self._write_receipt(result)
                return result

        try:
            self.dest.publish(source_path, channel=channel, publisher="transfer-gateway")
            receipt_id = f"xfer-{utc_now().strftime('%Y%m%d%H%M%S')}-{bundle_id[:8]}"
            result = TransferResult(
                bundle_id=bundle_id, status="transferred",
                reason=f"Published to {channel}", receipt_id=receipt_id,
            )
            self._results.append(result)
            self._write_receipt(result)
            return result
        except Exception as exc:
            result = TransferResult(bundle_id=bundle_id, status="error", reason=str(exc))
            self._results.append(result)
            self._write_receipt(result)
            return result

    def transfer_all(self, channel: Optional[str] = None) -> List[TransferResult]:
        """Transfer all available bundles from source to destination."""
        entries = self.source.list_bundles(channel=channel)
        dest_ids = {e.bundle_id for e in self.dest.list_bundles()}
        results = []
        for entry in entries:
            if entry.bundle_id in dest_ids:
                continue
            results.append(self.transfer_bundle(entry.bundle_id))
        return results

    @property
    def results(self) -> List[TransferResult]:
        return list(self._results)
