from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

from waveos.models import Event
from waveos.utils import utc_now, write_jsonl, get_logger


@dataclass
class RecoveryAction:
    timestamp: str
    action: str
    reason: str
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None


class RecoveryOrchestrator:
    def __init__(
        self,
        restart_command: str | None = None,
        degrade_command: str | None = None,
        reboot_command: str | None = None,
    ) -> None:
        self.logger = get_logger("waveos.recovery")
        self.restart_command = restart_command
        self.degrade_command = degrade_command
        self.reboot_command = reboot_command

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
                if self.restart_command:
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
                if self.degrade_command:
                    self._run_command(self.degrade_command)
        if actions:
            out_path = out_dir / "recovery_actions.jsonl"
            write_jsonl(out_path, [action.__dict__ for action in actions])
            for action in actions:
                self.logger.warning("Recovery action=%s entity=%s/%s reason=%s", action.action, action.entity_type, action.entity_id, action.reason)
        return actions

    def _run_command(self, command: str) -> None:
        import subprocess

        try:
            subprocess.run(command, shell=True, check=False)
        except Exception as exc:
            self.logger.warning("Recovery command failed: %s", exc)


def watchdog_ping(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(utc_now().isoformat() + "\n", encoding="utf-8")
