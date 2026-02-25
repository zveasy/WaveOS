"""Transfer gateway — pull from outside registry, scan, approve, publish inside."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.transfer.gateway")


class TransferStatus(str, Enum):
    PENDING = "pending"
    SCANNING = "scanning"
    SCAN_PASSED = "scan_passed"
    SCAN_FAILED = "scan_failed"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    TRANSFERRING = "transferring"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ScanResult:
    scanner: str
    passed: bool
    message: str = ""
    timestamp: str = ""
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"scanner": self.scanner, "passed": self.passed, "message": self.message, "timestamp": self.timestamp or utc_now().isoformat(), "details": self.details}

    @classmethod
    def from_dict(cls, d: dict) -> ScanResult:
        return cls(**{k: d[k] for k in d if k in cls.__dataclass_fields__})


@dataclass
class TransferJob:
    """A transfer job from source to destination."""
    job_id: str
    bundle_id: str
    source: str
    destination: str
    status: TransferStatus = TransferStatus.PENDING
    scan_results: List[ScanResult] = field(default_factory=list)
    approved_by: str = ""
    transfer_receipt: Dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    completed_at: str = ""
    sha256: str = ""

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id, "bundle_id": self.bundle_id,
            "source": self.source, "destination": self.destination,
            "status": self.status.value,
            "scan_results": [s.to_dict() for s in self.scan_results],
            "approved_by": self.approved_by, "transfer_receipt": self.transfer_receipt,
            "created_at": self.created_at or utc_now().isoformat(), "completed_at": self.completed_at,
            "sha256": self.sha256,
        }

    @classmethod
    def from_dict(cls, d: dict) -> TransferJob:
        job = cls(
            job_id=d.get("job_id", ""), bundle_id=d.get("bundle_id", ""),
            source=d.get("source", ""), destination=d.get("destination", ""),
            status=TransferStatus(d.get("status", "pending")),
            approved_by=d.get("approved_by", ""),
            transfer_receipt=d.get("transfer_receipt", {}),
            created_at=d.get("created_at", ""), completed_at=d.get("completed_at", ""),
            sha256=d.get("sha256", ""),
        )
        job.scan_results = [ScanResult.from_dict(s) for s in d.get("scan_results", [])]
        return job


class TransferGateway:
    """Controlled transfer gateway: pull-from-outside, scan, approve, publish-inside."""

    def __init__(self, staging_dir: Path, dest_registry_root: Path) -> None:
        self.staging_dir = staging_dir
        self.dest_registry_root = dest_registry_root
        self._jobs: Dict[str, TransferJob] = {}
        self._scan_hooks: List[Callable] = []
        self.staging_dir.mkdir(parents=True, exist_ok=True)

    def add_scan_hook(self, hook: Callable) -> None:
        """Add a scan hook: callable(bundle_dir: Path) -> ScanResult."""
        self._scan_hooks.append(hook)

    def create_job(self, bundle_id: str, source_bundle_dir: Path, source_label: str = "external") -> TransferJob:
        """Create a transfer job by pulling bundle into staging."""
        from uuid import uuid4
        job_id = f"xfer-{uuid4().hex[:8]}"
        staged = self.staging_dir / job_id
        shutil.copytree(source_bundle_dir, staged)
        manifest_path = staged / "bundle.json"
        sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest() if manifest_path.exists() else ""
        job = TransferJob(job_id=job_id, bundle_id=bundle_id, source=source_label, destination=str(self.dest_registry_root), sha256=sha, created_at=utc_now().isoformat())
        self._jobs[job_id] = job
        logger.info("Transfer job %s created for bundle %s", job_id, bundle_id)
        return job

    def scan_job(self, job_id: str) -> TransferJob:
        """Run scan hooks on a staged bundle."""
        job = self._jobs.get(job_id)
        if not job:
            raise ValueError(f"Job not found: {job_id}")
        staged = self.staging_dir / job_id
        job.status = TransferStatus.SCANNING
        all_passed = True
        for hook in self._scan_hooks:
            try:
                result = hook(staged)
                if isinstance(result, ScanResult):
                    job.scan_results.append(result)
                    if not result.passed:
                        all_passed = False
                elif isinstance(result, tuple):
                    ok, msg = result
                    job.scan_results.append(ScanResult(scanner="hook", passed=ok, message=msg))
                    if not ok:
                        all_passed = False
            except Exception as exc:
                job.scan_results.append(ScanResult(scanner="hook", passed=False, message=str(exc)))
                all_passed = False
        job.status = TransferStatus.SCAN_PASSED if all_passed else TransferStatus.SCAN_FAILED
        if all_passed and not self._scan_hooks:
            job.status = TransferStatus.SCAN_PASSED
        return job

    def approve_job(self, job_id: str, approver: str) -> TransferJob:
        job = self._jobs.get(job_id)
        if not job:
            raise ValueError(f"Job not found: {job_id}")
        if job.status not in (TransferStatus.SCAN_PASSED, TransferStatus.AWAITING_APPROVAL):
            raise ValueError(f"Job {job_id} not in approvable state: {job.status.value}")
        job.approved_by = approver
        job.status = TransferStatus.APPROVED
        return job

    def reject_job(self, job_id: str, reason: str = "") -> TransferJob:
        job = self._jobs.get(job_id)
        if not job:
            raise ValueError(f"Job not found: {job_id}")
        job.status = TransferStatus.REJECTED
        job.transfer_receipt["rejection_reason"] = reason
        return job

    def execute_transfer(self, job_id: str, channel: str = "prod") -> TransferJob:
        """Execute the approved transfer: copy from staging to destination registry."""
        job = self._jobs.get(job_id)
        if not job:
            raise ValueError(f"Job not found: {job_id}")
        if job.status != TransferStatus.APPROVED:
            raise ValueError(f"Job {job_id} not approved: {job.status.value}")
        staged = self.staging_dir / job_id
        job.status = TransferStatus.TRANSFERRING
        try:
            from waveos.registry.store import RegistryStore
            store = RegistryStore(self.dest_registry_root)
            entry = store.publish(staged, channel=channel, publisher=f"gateway:{job.approved_by}")
            job.transfer_receipt = {
                "bundle_id": entry.bundle_id, "channel": channel, "published_at": entry.published_at,
                "publisher": entry.publisher, "sha256": job.sha256,
                "timestamp": utc_now().isoformat(),
            }
            job.status = TransferStatus.COMPLETED
            job.completed_at = utc_now().isoformat()
            logger.info("Transfer %s completed: bundle %s -> %s", job_id, job.bundle_id, channel)
        except Exception as exc:
            job.status = TransferStatus.FAILED
            job.transfer_receipt["error"] = str(exc)
            logger.error("Transfer %s failed: %s", job_id, exc)
        return job

    def get_job(self, job_id: str) -> Optional[TransferJob]:
        return self._jobs.get(job_id)

    def list_jobs(self, status: Optional[TransferStatus] = None) -> List[TransferJob]:
        jobs = list(self._jobs.values())
        if status:
            jobs = [j for j in jobs if j.status == status]
        return sorted(jobs, key=lambda j: j.created_at, reverse=True)
