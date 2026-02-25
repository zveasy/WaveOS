"""Atomic installation — symlink activation, power-loss recovery, storage management, delta updates."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.agent.atomic")


@dataclass
class AtomicActivationResult:
    ok: bool
    previous_target: str = ""
    new_target: str = ""
    symlink: str = ""
    error: str = ""
    recovery_marker: str = ""

    def to_dict(self) -> dict:
        return {"ok": self.ok, "previous_target": self.previous_target, "new_target": self.new_target,
                "symlink": self.symlink, "error": self.error, "recovery_marker": self.recovery_marker}


def atomic_activate(apps_dir: Path, app_name: str, new_version: str) -> AtomicActivationResult:
    """Activate a version via atomic symlink swap.
    
    Activation is a single symlink operation: apps_dir/app_name/current -> apps_dir/app_name/<version>.
    This is atomic on POSIX (rename of symlink).
    """
    app_dir = apps_dir / app_name
    new_target = app_dir / new_version
    current_link = app_dir / "current"
    
    if not new_target.is_dir():
        return AtomicActivationResult(ok=False, error=f"Version dir not found: {new_target}")
    
    previous = ""
    if current_link.is_symlink():
        previous = os.readlink(str(current_link))
    elif current_link.exists():
        previous = str(current_link.resolve())
    
    recovery_marker = _write_recovery_marker(app_dir, app_name, new_version, previous)
    
    tmp_link = app_dir / f".current_new_{os.getpid()}"
    try:
        if tmp_link.exists() or tmp_link.is_symlink():
            tmp_link.unlink()
        tmp_link.symlink_to(new_version)
        os.rename(str(tmp_link), str(current_link))
    except OSError as exc:
        if tmp_link.exists() or tmp_link.is_symlink():
            try:
                tmp_link.unlink()
            except OSError:
                pass
        return AtomicActivationResult(ok=False, error=str(exc), previous_target=previous, new_target=str(new_target))
    
    _clear_recovery_marker(app_dir)
    
    return AtomicActivationResult(
        ok=True, previous_target=previous, new_target=new_version,
        symlink=str(current_link), recovery_marker="",
    )


def _write_recovery_marker(app_dir: Path, app_name: str, new_version: str, previous: str) -> str:
    """Write a recovery marker before activation so power-loss recovery knows what was happening."""
    marker_path = app_dir / ".recovery_marker.json"
    data = {
        "app_name": app_name, "new_version": new_version, "previous": previous,
        "started_at": utc_now().isoformat(), "status": "activating",
    }
    marker_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return str(marker_path)


def _clear_recovery_marker(app_dir: Path) -> None:
    marker = app_dir / ".recovery_marker.json"
    if marker.exists():
        marker.unlink()


def recover_from_power_loss(apps_dir: Path) -> List[Dict[str, Any]]:
    """Check all apps for recovery markers left by interrupted activations.
    
    If a marker exists, the activation was interrupted. We revert to the previous version.
    Returns list of recovery actions taken.
    """
    actions: List[Dict[str, Any]] = []
    if not apps_dir.is_dir():
        return actions
    
    for app_dir in sorted(apps_dir.iterdir()):
        if not app_dir.is_dir():
            continue
        marker_path = app_dir / ".recovery_marker.json"
        if not marker_path.exists():
            continue
        try:
            data = json.loads(marker_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        
        previous = data.get("previous", "")
        current_link = app_dir / "current"
        
        if previous and (app_dir / previous).is_dir():
            tmp_link = app_dir / f".current_recovery_{os.getpid()}"
            try:
                if tmp_link.exists() or tmp_link.is_symlink():
                    tmp_link.unlink()
                tmp_link.symlink_to(previous)
                os.rename(str(tmp_link), str(current_link))
                actions.append({"app": app_dir.name, "action": "reverted", "to": previous, "reason": "power_loss_recovery"})
            except OSError as exc:
                actions.append({"app": app_dir.name, "action": "recovery_failed", "error": str(exc)})
                if tmp_link.exists() or tmp_link.is_symlink():
                    try:
                        tmp_link.unlink()
                    except OSError:
                        pass
        else:
            actions.append({"app": app_dir.name, "action": "no_previous", "marker": data})
        
        _clear_recovery_marker(app_dir)
    
    return actions


@dataclass
class StoragePolicy:
    """Retention and storage management policy."""
    max_versions: int = 5
    min_free_disk_mb: int = 500
    protected_versions: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"max_versions": self.max_versions, "min_free_disk_mb": self.min_free_disk_mb,
                "protected_versions": self.protected_versions}


def enforce_storage_policy(apps_dir: Path, app_name: str, policy: StoragePolicy) -> Dict[str, Any]:
    """Enforce retention: keep at most max_versions, never delete protected or current."""
    app_dir = apps_dir / app_name
    if not app_dir.is_dir():
        return {"pruned": [], "kept": []}
    
    current_target = ""
    current_link = app_dir / "current"
    if current_link.is_symlink():
        current_target = os.readlink(str(current_link))
    
    versions = sorted([d for d in app_dir.iterdir() if d.is_dir() and d.name != "current" and not d.name.startswith(".")])
    
    protected = set(policy.protected_versions)
    if current_target:
        protected.add(current_target)
    
    pruned: List[str] = []
    kept: List[str] = []
    
    if len(versions) > policy.max_versions:
        candidates = [v for v in versions if v.name not in protected]
        to_prune = candidates[:len(versions) - policy.max_versions]
        for v in to_prune:
            try:
                shutil.rmtree(v)
                pruned.append(v.name)
            except OSError:
                kept.append(v.name)
    
    try:
        usage = shutil.disk_usage(str(apps_dir))
        free_mb = usage.free // (1024 * 1024)
        if free_mb < policy.min_free_disk_mb:
            candidates = [v for v in versions if v.name not in protected and v.name not in pruned]
            for v in candidates:
                if free_mb >= policy.min_free_disk_mb:
                    break
                try:
                    shutil.rmtree(v)
                    pruned.append(v.name)
                    usage = shutil.disk_usage(str(apps_dir))
                    free_mb = usage.free // (1024 * 1024)
                except OSError:
                    pass
    except OSError:
        pass
    
    remaining = [d.name for d in app_dir.iterdir() if d.is_dir() and d.name != "current" and not d.name.startswith(".")]
    return {"pruned": pruned, "kept": remaining, "app": app_name}


@dataclass
class ChunkedDownloadState:
    """State for a resumable chunked download."""
    bundle_id: str
    total_size: int = 0
    downloaded: int = 0
    chunk_hashes: Dict[str, str] = field(default_factory=dict)
    expected_hash: str = ""
    temp_path: str = ""
    completed: bool = False

    def to_dict(self) -> dict:
        return {"bundle_id": self.bundle_id, "total_size": self.total_size, "downloaded": self.downloaded,
                "chunk_hashes": self.chunk_hashes, "expected_hash": self.expected_hash,
                "temp_path": self.temp_path, "completed": self.completed}

    @classmethod
    def from_dict(cls, d: dict) -> ChunkedDownloadState:
        return cls(**{k: d[k] for k in d if k in cls.__dataclass_fields__})


def verify_download_integrity(file_path: Path, expected_hash: str) -> Tuple[bool, str]:
    """Verify a downloaded file's SHA256 hash."""
    if not file_path.exists():
        return False, "File not found"
    h = hashlib.sha256()
    with file_path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    actual = h.hexdigest()
    if actual != expected_hash:
        return False, f"Hash mismatch: expected {expected_hash[:16]}... got {actual[:16]}..."
    return True, ""


def save_download_state(state: ChunkedDownloadState, state_dir: Path) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / f"download_{state.bundle_id}.json"
    path.write_text(json.dumps(state.to_dict(), indent=2) + "\n", encoding="utf-8")


def load_download_state(state_dir: Path, bundle_id: str) -> Optional[ChunkedDownloadState]:
    path = state_dir / f"download_{bundle_id}.json"
    if not path.exists():
        return None
    try:
        return ChunkedDownloadState.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError):
        return None
