"""Transfer gateway adaptor — pull-from-outside, publish-inside job for DMZ-like zones."""

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
    """A transfer job moving a bundle from outside to inside registry."""
    job_id: str
    bundle_id: str
    source_path: str
    dest_registry: str
    channel: str = "prod"
    status: TransferJobStatus = TransferJobStatus.PENDING
    scan_result: Optional[Dict[str, Any]] = None
    approval: Optional[Dict[str, Any]] = None
    receipt: Optional[Dict[str, Any]] = None
    created_at: str = ""
    completed_at: str = ""
    error: str = ""

    def to_dict(self) -> dict:
        return {"job_id": self.job_id, "bundle_id": self.bundle_id, "source_path": self.source_path,
                "dest_registry": self.dest_registry, "channel": self.channel,
                "status": self.status.value, "scan_result": self.scan_result,
                "approval": self.approval, "receipt": self.receipt,
                "created_at": self.created_at, "completed_at": self.completed_at, "error": self.error}

    @classmethod
    def from_dict(cls, d: dict) -> TransferJob:
        d2 = dict(d)
        if "status" in d2:
            d2["status"] = TransferJobStatus(d2["status"])
        return cls(**{k: d2[k] for k in d2 if k in cls.__dataclass_fields__})


class TransferGateway:
    """Operates in a DMZ zone: pulls from outside source, scans, gets approval, publishes to internal mirror."""

    def __init__(self, staging_dir: Path, scan_hook: Optional[Callable[[Path], Dict[str, Any]]] = None,
                 approval_hook: Optional[Callable[[TransferJob], bool]] = None) -> None:
        self.staging_dir = staging_dir
        self.staging_dir.mkdir(parents=True, exist_ok=True)
        self.scan_hook = scan_hook
        self.approval_hook = approval_hook
        self._jobs: Dict[str, TransferJob] = {}

    def create_job(self, bundle_id: str, source_path: Path, dest_registry: str,
                   channel: str = "prod") -> TransferJob:
        job_id = f"xfer-{utc_now().strftime('%Y%m%d%H%M%S')}-{bundle_id[:8]}"
        job = TransferJob(job_id=job_id, bundle_id=bundle_id, source_path=str(source_path),
                          dest_registry=dest_registry, channel=channel,
                          created_at=utc_now().isoformat())
        self._jobs[job_id] = job
        logger.info("Transfer job created: %s for bundle %s", job_id, bundle_id)
        return job

    def execute_job(self, job_id: str) -> TransferJob:
        """Execute a transfer job through all stages."""
        job = self._jobs.get(job_id)
        if not job:
            raise ValueError(f"Unknown job: {job_id}")
        source = Path(job.source_path)
        if not source.exists():
            job.status = TransferJobStatus.FAILED
            job.error = "Source not found"
            return job
        staged = self.staging_dir / job.bundle_id
        if staged.exists():
            shutil.rmtree(staged)
        if source.is_dir():
            shutil.copytree(source, staged)
        else:
            staged.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, staged / source.name)
        job.status = TransferJobStatus.SCANNING
        if self.scan_hook:
            try:
                result = self.scan_hook(staged)
                job.scan_result = result
                if not result.get("passed", True):
                    job.status = TransferJobStatus.REJECTED
                    job.error = result.get("reason", "Scan failed")
                    return job
            except Exception as exc:
                job.status = TransferJobStatus.FAILED
                job.error = f"Scan error: {exc}"
                return job
        else:
            job.scan_result = {"passed": True, "scanner": "none"}
        job.status = TransferJobStatus.AWAITING_APPROVAL
        if self.approval_hook:
            approved = self.approval_hook(job)
            if not approved:
                job.status = TransferJobStatus.REJECTED
                job.error = "Approval denied"
                return job
            job.approval = {"approved": True, "timestamp": utc_now().isoformat()}
        else:
            job.approval = {"approved": True, "auto": True, "timestamp": utc_now().isoformat()}
        job.status = TransferJobStatus.APPROVED
        job.status = TransferJobStatus.TRANSFERRING
        try:
            from waveos.registry.store import RegistryStore
            dest = RegistryStore(Path(job.dest_registry))
            entry = dest.publish(staged, channel=job.channel, publisher=f"gateway:{job.job_id}")
            job.receipt = {"bundle_id": entry.bundle_id, "channel": entry.channel,
                          "published_at": entry.published_at, "dest": job.dest_registry,
                          "source_hash": hashlib.sha256(json.dumps(job.scan_result or {}).encode()).hexdigest()[:16]}
            job.status = TransferJobStatus.COMPLETED
            job.completed_at = utc_now().isoformat()
        except Exception as exc:
            job.status = TransferJobStatus.FAILED
            job.error = str(exc)
        if staged.exists():
            shutil.rmtree(staged)
        return job

    def list_jobs(self) -> List[TransferJob]:
        return list(self._jobs.values())

    def save_jobs(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps([j.to_dict() for j in self._jobs.values()], indent=2) + "\n", encoding="utf-8")
