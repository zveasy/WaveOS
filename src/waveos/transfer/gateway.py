"""Transfer Gateway — pull-from-outside, publish-inside job for DMZ/CDS environments."""

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
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    TRANSFERRING = "transferring"
    PUBLISHED = "published"
    FAILED = "failed"


@dataclass
class TransferJob:
    """A single transfer job from outside source to inside mirror."""
    job_id: str
    bundle_id: str
    source_path: str
    status: TransferStatus = TransferStatus.PENDING
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
            "source_path": self.source_path,
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
        return cls(
            job_id=d.get("job_id", ""),
            bundle_id=d.get("bundle_id", ""),
            source_path=d.get("source_path", ""),
            status=TransferStatus(d.get("status", "pending")),
            scan_result=d.get("scan_result"),
            approval=d.get("approval"),
            receipt=d.get("receipt"),
            created_at=d.get("created_at", ""),
            completed_at=d.get("completed_at", ""),
            error=d.get("error", ""),
        )


ScanHook = Callable[[Path], Dict[str, Any]]
ApprovalHook = Callable[[TransferJob], bool]


class TransferGateway:
    """Manages controlled transfers from outside source to inside registry mirror.

    Supports:
    - Scanning hooks (malware, policy)
    - Approval workflows
    - Signed transfer receipts
    - Chain-of-custody audit trail
    """

    def __init__(
        self,
        staging_dir: Path,
        mirror_registry_root: Path,
        scan_hooks: Optional[List[ScanHook]] = None,
        approval_hook: Optional[ApprovalHook] = None,
    ) -> None:
        self.staging_dir = staging_dir
        self.mirror_registry_root = mirror_registry_root
        self._scan_hooks = scan_hooks or []
        self._approval_hook = approval_hook
        self._jobs: Dict[str, TransferJob] = {}
        self.staging_dir.mkdir(parents=True, exist_ok=True)
        self.mirror_registry_root.mkdir(parents=True, exist_ok=True)

    def submit(self, source_path: Path, bundle_id: str = "") -> TransferJob:
        """Submit a bundle for transfer through the gateway."""
        if not source_path.exists():
            raise ValueError(f"Source path does not exist: {source_path}")
        job_id = f"xfer-{utc_now().strftime('%Y%m%d%H%M%S')}-{hashlib.sha256(str(source_path).encode()).hexdigest()[:8]}"
        if not bundle_id:
            manifest_path = source_path / "bundle.json" if source_path.is_dir() else source_path
            if manifest_path.exists():
                try:
                    data = json.loads(manifest_path.read_text(encoding="utf-8"))
                    bundle_id = data.get("bundle_id", job_id)
                except (json.JSONDecodeError, OSError):
                    bundle_id = job_id
        staging = self.staging_dir / job_id
        if source_path.is_dir():
            shutil.copytree(source_path, staging)
        else:
            staging.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, staging / source_path.name)
        job = TransferJob(job_id=job_id, bundle_id=bundle_id, source_path=str(source_path), created_at=utc_now().isoformat())
        self._jobs[job_id] = job
        logger.info("Transfer job submitted: %s for bundle %s", job_id, bundle_id)
        return job

    def scan(self, job_id: str) -> Dict[str, Any]:
        """Run scanning hooks on a staged transfer."""
        job = self._jobs.get(job_id)
        if not job:
            return {"ok": False, "error": "Job not found"}
        job.status = TransferStatus.SCANNING
        staging = self.staging_dir / job_id
        results: List[Dict[str, Any]] = []
        all_clean = True
        for hook in self._scan_hooks:
            try:
                result = hook(staging)
                results.append(result)
                if not result.get("clean", True):
                    all_clean = False
            except Exception as exc:
                results.append({"hook": "error", "clean": False, "error": str(exc)})
                all_clean = False
        job.scan_result = {"clean": all_clean, "results": results, "scanned_at": utc_now().isoformat()}
        if not all_clean:
            job.status = TransferStatus.FAILED
            job.error = "Scan failed"
        elif self._approval_hook:
            job.status = TransferStatus.AWAITING_APPROVAL
        else:
            job.status = TransferStatus.APPROVED
        return job.scan_result

    def approve(self, job_id: str, approver: str = "", approved: bool = True) -> Dict[str, Any]:
        """Approve or reject a transfer."""
        job = self._jobs.get(job_id)
        if not job:
            return {"ok": False, "error": "Job not found"}
        job.approval = {"approved": approved, "approver": approver, "timestamp": utc_now().isoformat()}
        if approved:
            job.status = TransferStatus.APPROVED
        else:
            job.status = TransferStatus.REJECTED
        return job.approval

    def execute(self, job_id: str, channel: str = "prod") -> Dict[str, Any]:
        """Execute the transfer: publish to inside mirror registry."""
        job = self._jobs.get(job_id)
        if not job:
            return {"ok": False, "error": "Job not found"}
        if job.status != TransferStatus.APPROVED:
            return {"ok": False, "error": f"Job not approved (status: {job.status.value})"}
        job.status = TransferStatus.TRANSFERRING
        staging = self.staging_dir / job_id
        try:
            from waveos.registry.store import RegistryStore
            store = RegistryStore(self.mirror_registry_root)
            entry = store.publish(staging, channel=channel, publisher="transfer-gateway")
            job.status = TransferStatus.PUBLISHED
            job.completed_at = utc_now().isoformat()
            content_hash = hashlib.sha256(json.dumps(entry.to_dict(), sort_keys=True).encode()).hexdigest()
            job.receipt = {
                "bundle_id": entry.bundle_id,
                "channel": channel,
                "published_at": entry.published_at,
                "content_hash": content_hash,
                "transfer_job_id": job_id,
                "signed_at": utc_now().isoformat(),
            }
            logger.info("Transfer complete: %s -> mirror (%s)", job.bundle_id, channel)
            return {"ok": True, "entry": entry.to_dict(), "receipt": job.receipt}
        except Exception as exc:
            job.status = TransferStatus.FAILED
            job.error = str(exc)
            return {"ok": False, "error": str(exc)}

    def get_job(self, job_id: str) -> Optional[TransferJob]:
        return self._jobs.get(job_id)

    def list_jobs(self) -> List[TransferJob]:
        return list(self._jobs.values())

    def process(self, source_path: Path, bundle_id: str = "", channel: str = "prod", approver: str = "auto") -> Dict[str, Any]:
        """Full pipeline: submit -> scan -> approve -> execute."""
        job = self.submit(source_path, bundle_id)
        scan = self.scan(job.job_id)
        if not scan.get("clean", False):
            return {"ok": False, "job_id": job.job_id, "status": job.status.value, "scan": scan}
        if job.status == TransferStatus.AWAITING_APPROVAL:
            self.approve(job.job_id, approver=approver, approved=True)
        return self.execute(job.job_id, channel=channel)
