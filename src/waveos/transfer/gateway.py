"""Transfer gateway — pull-from-outside, publish-inside job for DMZ environments."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from waveos.registry.store import RegistryStore
from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.transfer.gateway")


class TransferStatus(str, Enum):
    PENDING = "pending"
    SCANNING = "scanning"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    TRANSFERRING = "transferring"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class TransferJob:
    job_id: str
    bundle_id: str
    source_path: str
    target_registry: str
    channel: str = "prod"
    status: TransferStatus = TransferStatus.PENDING
    scan_result: str = ""
    approval_by: str = ""
    sha256: str = ""
    started_at: str = ""
    completed_at: str = ""
    error: str = ""
    receipt: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "bundle_id": self.bundle_id,
            "source_path": self.source_path,
            "target_registry": self.target_registry,
            "channel": self.channel,
            "status": self.status.value,
            "scan_result": self.scan_result,
            "approval_by": self.approval_by,
            "sha256": self.sha256,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "error": self.error,
            "receipt": self.receipt,
        }


class TransferGateway:
    """Controlled-transfer gateway: pull from source, scan, approve, publish to internal registry.

    Operates in a DMZ-like zone between external CI/CD and internal secure networks.
    """

    def __init__(
        self,
        staging_dir: Path,
        target_store: RegistryStore,
        scan_hook: Optional[Callable[[Path], str]] = None,
        approval_hook: Optional[Callable[[str, str], str]] = None,
        one_way: bool = True,
    ) -> None:
        self.staging_dir = staging_dir
        self.staging_dir.mkdir(parents=True, exist_ok=True)
        self.target = target_store
        self._scan_hook = scan_hook
        self._approval_hook = approval_hook
        self.one_way = one_way
        self._jobs: List[TransferJob] = []

    def submit(self, bundle_dir: Path, bundle_id: str, channel: str = "prod") -> TransferJob:
        """Submit a bundle for transfer through the gateway."""
        job_id = f"xfer-{utc_now().strftime('%Y%m%d%H%M%S')}-{bundle_id[:12]}"
        staging = self.staging_dir / job_id
        staging.mkdir(parents=True, exist_ok=True)
        shutil.copytree(bundle_dir, staging / "bundle", dirs_exist_ok=True)

        manifest_path = staging / "bundle" / "bundle.json"
        sha = ""
        if manifest_path.exists():
            sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()

        job = TransferJob(
            job_id=job_id,
            bundle_id=bundle_id,
            source_path=str(bundle_dir),
            target_registry=str(self.target.root),
            channel=channel,
            sha256=sha,
            started_at=utc_now().isoformat(),
        )
        self._jobs.append(job)
        return job

    def process(self, job: TransferJob) -> TransferJob:
        """Process a submitted transfer job through scan → approve → transfer pipeline."""
        # Scan
        job.status = TransferStatus.SCANNING
        staged_bundle = self.staging_dir / job.job_id / "bundle"
        if self._scan_hook:
            try:
                job.scan_result = self._scan_hook(staged_bundle)
                if job.scan_result in ("blocked", "malware"):
                    job.status = TransferStatus.FAILED
                    job.error = f"Scan blocked: {job.scan_result}"
                    return job
            except Exception as exc:
                job.scan_result = f"error: {exc}"
        else:
            job.scan_result = "clean"

        # Approve
        job.status = TransferStatus.AWAITING_APPROVAL
        if self._approval_hook:
            try:
                approval = self._approval_hook(job.bundle_id, job.channel)
                if approval.startswith("approved"):
                    job.approval_by = approval.split(":")[-1] if ":" in approval else "auto"
                    job.status = TransferStatus.APPROVED
                else:
                    job.status = TransferStatus.REJECTED
                    job.error = f"Approval rejected: {approval}"
                    return job
            except Exception as exc:
                job.error = f"Approval error: {exc}"
                job.status = TransferStatus.FAILED
                return job
        else:
            job.status = TransferStatus.APPROVED
            job.approval_by = "auto"

        # Transfer
        job.status = TransferStatus.TRANSFERRING
        try:
            entry = self.target.publish(staged_bundle, channel=job.channel, publisher=f"gateway:{job.job_id}")
            job.status = TransferStatus.COMPLETED
            job.completed_at = utc_now().isoformat()
            job.receipt = {
                "entry": entry.to_dict(),
                "source_sha256": job.sha256,
                "gateway_job_id": job.job_id,
                "transferred_at": job.completed_at,
            }
        except Exception as exc:
            job.status = TransferStatus.FAILED
            job.error = str(exc)

        return job

    def submit_and_process(self, bundle_dir: Path, bundle_id: str, channel: str = "prod") -> TransferJob:
        job = self.submit(bundle_dir, bundle_id, channel)
        return self.process(job)

    @property
    def jobs(self) -> List[TransferJob]:
        return list(self._jobs)

    def write_jobs(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps([j.to_dict() for j in self._jobs], indent=2) + "\n", encoding="utf-8")
