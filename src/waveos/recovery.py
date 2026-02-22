from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

from waveos.models import Event
from waveos.utils import utc_now, write_jsonl, get_logger

logger = get_logger("waveos.recovery")

# Shell metacharacters that would make shell=True unsafe; reject if present in recovery commands.
# Space is allowed (shlex.split handles it); reject ;|&$()`<> newlines and backslash.
_UNSAFE_SHELL_CHARS = frozenset(";|&$()`<>\\\n\r\t")


@dataclass
class RecoveryAction:
    timestamp: str
    action: str
    reason: str
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None


def _recovery_approved(approval_path: Path | None, env_approved: bool = False) -> bool:
    """True if recovery commands are allowed (no approval required, or approval file/env present)."""
    if env_approved:
        return True
    if not approval_path:
        return True
    if not approval_path.exists():
        return False
    try:
        return approval_path.read_text(encoding="utf-8").strip().lower() == "approved"
    except OSError as exc:
        logger.debug("Could not read recovery approval file %s: %s", approval_path, exc)
        return False


class RecoveryOrchestrator:
    def __init__(
        self,
        restart_command: str | None = None,
        degrade_command: str | None = None,
        reboot_command: str | None = None,
        require_approval: bool = False,
        approval_path: Path | None = None,
        env_approved: bool = False,
    ) -> None:
        self.logger = get_logger("waveos.recovery")
        self.restart_command = restart_command
        self.degrade_command = degrade_command
        self.reboot_command = reboot_command
        self.require_approval = require_approval
        self.approval_path = approval_path
        self.env_approved = env_approved

    def handle_events(self, events: Iterable[Event], out_dir: Path) -> List[RecoveryAction]:
        actions: List[RecoveryAction] = []
        for event in events:
            if event.level.value == "ERROR":
                actions.append(
                    RecoveryAction(
                        timestamp=utc_now().isoformat(),
                        action="restart_service",
                        reason=event.message,
                        entity_type=event.entity_type,
                        entity_id=event.entity_id,
                    )
                )
                if self.restart_command and self._may_run_commands():
                    self._run_command(self.restart_command)
            elif event.level.value == "WARN":
                actions.append(
                    RecoveryAction(
                        timestamp=utc_now().isoformat(),
                        action="degrade_features",
                        reason=event.message,
                        entity_type=event.entity_type,
                        entity_id=event.entity_id,
                    )
                )
                if self.degrade_command and self._may_run_commands():
                    self._run_command(self.degrade_command)
        if actions:
            out_path = out_dir / "recovery_actions.jsonl"
            write_jsonl(out_path, [action.__dict__ for action in actions])
            for action in actions:
                self.logger.warning("Recovery action=%s entity=%s/%s reason=%s", action.action, action.entity_type, action.entity_id, action.reason)
            if self.require_approval and not self._may_run_commands():
                self.logger.warning("Recovery commands not run: operator approval required (set WAVEOS_RECOVERY_APPROVED=true or create approval file)")
        return actions

    def _may_run_commands(self) -> bool:
        if not self.require_approval:
            return True
        return _recovery_approved(self.approval_path, self.env_approved)

    def _run_command(self, command: str) -> None:
        """Run recovery command without shell to avoid injection. Command must be a single executable and args (no shell metacharacters)."""
        cmd = (command or "").strip()
        if not cmd:
            return
        if _UNSAFE_SHELL_CHARS.intersection(cmd):
            self.logger.warning(
                "Recovery command rejected: contains unsafe shell metacharacters. Use a single executable and arguments only (no ;|&$() etc.)."
            )
            return
        try:
            args = shlex.split(cmd, posix=True)
            if not args:
                return
            subprocess.run(args, shell=False, check=False, timeout=60)
        except (ValueError, FileNotFoundError, subprocess.TimeoutExpired) as exc:
            self.logger.warning("Recovery command failed: %s", type(exc).__name__)
        except Exception as exc:
            self.logger.warning("Recovery command failed: %s", type(exc).__name__)


def watchdog_ping(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(utc_now().isoformat() + "\n", encoding="utf-8")
