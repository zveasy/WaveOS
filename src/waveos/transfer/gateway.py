"""Transfer gateway — pull-from-outside, publish-inside job runner for DMZ environments."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.transfer.gateway")


class TransferJobStatus(str, Enum):
    PENDING = "pending"
    SCANNING = "scanning"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    TRANSFERRING = "transferring"
    PUBLISHING = "publishing"
    COMPLETED = "completed"
    REJECTED = "rejected"
    FAILED = "failed"


@dataclass
class TransferJob:
    job_id: str
    bundle_id: str
    source_registry: str
    dest_registry: str
    channel: str = "dev"
    status: TransferJobStatus = TransferJobStatus.PENDING
    scan_result: Optional[Dict[str, Any]] = None
    approval: Optional[Dict[str, Any]] = None
    receipt: Optional[Dict[str, Any]] = None
    created_at: str = ""
    completed_at: str = ""
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "bundle_id": self.bundle_id,
            "source_registry": self.source_registry,
            "dest_registry": self.dest_registry,
            "channel": self.channel,
            "status": self.status.value,
            "scan_result": self.scan_result,
            "approval": self.approval,
            "receipt": self.receipt,
            "created_at": self.created_at or utc_now().isoformat(),
            "completed_at": self.completed_at,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, d: dict) -> TransferJob:
        d2 = dict(d)
        if "status" in d2:
            d2["status"] = TransferJobStatus(d2["status"])
        return cls(**{k: d2[k] for k in d2 if k in cls.__dataclass_fields__})


class TransferGateway:
    """Manages controlled transfer jobs: scan -> approve -> transfer -> publish."""

    def __init__(self, jobs_dir: Path) -> None:
        self.jobs_dir = jobs_dir
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self._scan_hook: Optional[Callable] = None
        self._approval_hook: Optional[Callable] = None

    def set_scan_hook(self, hook: Callable[[Path], Dict[str, Any]]) -> None:
        self._scan_hook = hook

    def set_approval_hook(self, hook: Callable[[TransferJob], Dict[str, Any]]) -> None:
        self._approval_hook = hook

    def create_job(self, bundle_id: str, source_registry: str, dest_registry: str, channel: str = "dev") -> TransferJob:
        job_id = f"xfer-{utc_now().strftime('%Y%m%d%H%M%S')}-{bundle_id[:8]}"
        job = TransferJob(
            job_id=job_id, bundle_id=bundle_id, source_registry=source_registry,
            dest_registry=dest_registry, channel=channel, created_at=utc_now().isoformat(),
        )
        self._save_job(job)
        return job

    def _save_job(self, job: TransferJob) -> None:
        path = self.jobs_dir / f"{job.job_id}.json"
        path.write_text(json.dumps(job.to_dict(), indent=2) + "\n", encoding="utf-8")

    def _load_job(self, job_id: str) -> Optional[TransferJob]:
        path = self.jobs_dir / f"{job_id}.json"
        if not path.exists():
            return None
        try:
            return TransferJob.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, KeyError):
            return None

    def execute_job(self, job_id: str) -> TransferJob:
        """Execute a transfer job through the full pipeline."""
        job = self._load_job(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        source = Path(job.source_registry)
        dest = Path(job.dest_registry)

        from waveos.registry.store import RegistryStore
        source_store = RegistryStore(source)
        bundle_path = source_store.get_bundle(job.bundle_id)
        if not bundle_path:
            job.status = TransferJobStatus.FAILED
            job.error = "Bundle not found in source registry"
            self._save_job(job)
            return job

        # Scan
        job.status = TransferJobStatus.SCANNING
        self._save_job(job)
        if self._scan_hook:
            try:
                scan_result = self._scan_hook(bundle_path)
                job.scan_result = scan_result
                if not scan_result.get("ok", True):
                    job.status = TransferJobStatus.REJECTED
                    job.error = scan_result.get("reason", "Scan rejected")
                    self._save_job(job)
                    return job
            except Exception as exc:
                job.status = TransferJobStatus.FAILED
                job.error = f"Scan error: {exc}"
                self._save_job(job)
                return job
        else:
            job.scan_result = {"ok": True, "scanner": "none"}

        # Approval
        job.status = TransferJobStatus.AWAITING_APPROVAL
        self._save_job(job)
        if self._approval_hook:
            try:
                approval = self._approval_hook(job)
                job.approval = approval
                if not approval.get("approved", False):
                    job.status = TransferJobStatus.REJECTED
                    job.error = approval.get("reason", "Not approved")
                    self._save_job(job)
                    return job
            except Exception as exc:
                job.status = TransferJobStatus.FAILED
                job.error = f"Approval error: {exc}"
                self._save_job(job)
                return job
        else:
            job.approval = {"approved": True, "approver": "auto"}
        job.status = TransferJobStatus.APPROVED
        self._save_job(job)

        # Transfer
        job.status = TransferJobStatus.TRANSFERRING
        self._save_job(job)
        dest_store = RegistryStore(dest)
        try:
            entry = dest_store.publish(bundle_path, channel=job.channel, publisher=f"gateway:{job.job_id}")
            job.receipt = {
                "bundle_id": entry.bundle_id, "channel": entry.channel,
                "published_at": entry.published_at, "size_bytes": entry.size_bytes,
            }
        except Exception as exc:
            job.status = TransferJobStatus.FAILED
            job.error = f"Transfer failed: {exc}"
            self._save_job(job)
            return job

        job.status = TransferJobStatus.COMPLETED
        job.completed_at = utc_now().isoformat()
        self._save_job(job)
        logger.info("Transfer job %s completed: %s -> %s", job.job_id, job.source_registry, job.dest_registry)
        return job

    def list_jobs(self) -> List[TransferJob]:
        jobs = []
        for path in sorted(self.jobs_dir.glob("xfer-*.json")):
            try:
                jobs.append(TransferJob.from_dict(json.loads(path.read_text(encoding="utf-8"))))
            except (json.JSONDecodeError, KeyError):
                pass
        return jobs
