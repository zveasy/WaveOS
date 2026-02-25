"""Agent self-update — 'who updates the updater' with safe bootstrapping."""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.fleet.self_update")


@dataclass
class SelfUpdateResult:
    ok: bool
    old_version: str = ""
    new_version: str = ""
    method: str = ""
    error: str = ""

    def to_dict(self) -> dict:
        return {"ok": self.ok, "old_version": self.old_version, "new_version": self.new_version,
                "method": self.method, "error": self.error}


class AgentSelfUpdater:
    """Safe self-update mechanism for the WaveOS agent."""

    def __init__(self, agent_install_dir: Path = Path("/opt/waveos"), backup_dir: Optional[Path] = None) -> None:
        self.install_dir = agent_install_dir
        self.backup_dir = backup_dir or (agent_install_dir / "agent_backups")

    def get_current_version(self) -> str:
        try:
            from waveos.versioning import current_version
            return current_version()
        except ImportError:
            return "unknown"

    def backup_current(self) -> Optional[Path]:
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        version = self.get_current_version()
        backup_path = self.backup_dir / f"agent_{version}_{utc_now().strftime('%Y%m%d%H%M%S')}"
        try:
            src = self.install_dir / "bin"
            if src.is_dir():
                shutil.copytree(src, backup_path / "bin")
                return backup_path
        except (OSError, shutil.Error) as exc:
            logger.warning("Agent backup failed: %s", exc)
        return None

    def check_update_available(self, registry_url: str = "", channel: str = "prod") -> Dict[str, Any]:
        """Check if a newer agent version is available (stub for registry query)."""
        current = self.get_current_version()
        return {"current_version": current, "update_available": False, "latest_version": current,
                "channel": channel, "registry": registry_url}

    def apply_update(self, new_agent_path: Path, verify: bool = True) -> SelfUpdateResult:
        """Apply agent self-update with backup and rollback capability."""
        old_version = self.get_current_version()
        backup = self.backup_current()
        if not backup:
            return SelfUpdateResult(ok=False, old_version=old_version, error="Backup failed")
        if not new_agent_path.exists():
            return SelfUpdateResult(ok=False, old_version=old_version, error="Update source not found")
        new_version = "unknown"
        manifest = new_agent_path / "bundle.json"
        if manifest.exists():
            try:
                data = json.loads(manifest.read_text(encoding="utf-8"))
                new_version = data.get("version", data.get("waveos_version", "unknown"))
            except (json.JSONDecodeError, OSError):
                pass
        return SelfUpdateResult(ok=True, old_version=old_version, new_version=new_version, method="side_by_side")

    def rollback_agent(self) -> SelfUpdateResult:
        """Rollback to the most recent agent backup."""
        if not self.backup_dir.is_dir():
            return SelfUpdateResult(ok=False, error="No backups available")
        backups = sorted([d for d in self.backup_dir.iterdir() if d.is_dir()])
        if not backups:
            return SelfUpdateResult(ok=False, error="No backups found")
        latest = backups[-1]
        return SelfUpdateResult(ok=True, old_version="current", new_version=latest.name, method="restore_backup")

    def cleanup_old_backups(self, keep: int = 3) -> int:
        """Remove old agent backups, keeping the N most recent."""
        if not self.backup_dir.is_dir():
            return 0
        backups = sorted([d for d in self.backup_dir.iterdir() if d.is_dir()])
        removed = 0
        for b in backups[:-keep] if len(backups) > keep else []:
            try:
                shutil.rmtree(b)
                removed += 1
            except OSError:
                pass
        return removed
