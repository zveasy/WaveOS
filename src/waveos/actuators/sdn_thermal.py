"""
Real actuator: SDN reroute + device API for thermal (and rate-limit / QoS).

When enforce_actions=true, the pipeline uses this actuator. It writes requests to
out/actuator/*.jsonl so you can see enforced actions and wire your SDN/device API
to consume them. Optional: call external URL or command via env.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable

from waveos.models import ActionRecommendation, ActionType
from waveos.utils import get_logger, utc_now

from waveos.actuators.base import RealActuator


# Map action type to request log file (SDN/thermal subsystems)
_ACTION_LOG: Dict[ActionType, str] = {
    ActionType.REROUTE: "reroute_requests.jsonl",
    ActionType.POWER_THERMAL_CONSTRAINT: "thermal_requests.jsonl",
    ActionType.RATE_LIMIT: "rate_limit_requests.jsonl",
    ActionType.QOS_PRIORITIZATION: "qos_requests.jsonl",
}


class SdnThermalActuator(RealActuator):
    """
    Real actuator that applies REROUTE (SDN), POWER_THERMAL_CONSTRAINT (device API),
    RATE_LIMIT, and QOS_PRIORITIZATION. Writes to output_dir so requests can be
    consumed by your SDN controller or thermal/device API. Optionally calls
    WAVEOS_ACTUATOR_SDN_URL (POST) or WAVEOS_ACTUATOR_THERMAL_CMD (subprocess) per action.
    """

    def __init__(
        self,
        output_dir: Path,
        run_id: str | None = None,
        name: str = "sdn_thermal",
    ) -> None:
        super().__init__(name=name)
        self.output_dir = Path(output_dir)
        self.run_id = run_id or ""
        self._sdn_url = os.getenv("WAVEOS_ACTUATOR_SDN_URL", "").strip()
        self._thermal_cmd = os.getenv("WAVEOS_ACTUATOR_THERMAL_CMD", "").strip()

    def validate(self, action: ActionRecommendation) -> bool:
        """Allow all action types; reject only if entity is missing."""
        if not action.entity_id or not action.entity_type:
            return False
        return True

    def apply(self, actions: Iterable[ActionRecommendation]) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        for action in actions:
            self._apply_one(action)

    def _apply_one(self, action: ActionRecommendation) -> None:
        log_name = _ACTION_LOG.get(action.action, "other_requests.jsonl")
        log_path = self.output_dir / log_name
        record = {
            "timestamp": utc_now().isoformat(),
            "run_id": self.run_id,
            "entity_type": action.entity_type,
            "entity_id": action.entity_id,
            "action": action.action.value if hasattr(action.action, "value") else str(action.action),
            "rationale": action.rationale,
            "parameters": action.parameters,
        }
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")
        self.logger.info(
            "Applied action=%s entity=%s/%s -> %s",
            action.action,
            action.entity_type,
            action.entity_id,
            log_name,
        )
        # Optional: call external SDN or thermal hook
        if action.action == ActionType.REROUTE and self._sdn_url:
            self._post_sdn(record)
        if action.action == ActionType.POWER_THERMAL_CONSTRAINT and self._thermal_cmd:
            self._run_thermal_cmd(record)

    def _post_sdn(self, record: Dict[str, Any]) -> None:
        """POST record to SDN controller URL (optional)."""
        try:
            import urllib.request
            req = urllib.request.Request(
                self._sdn_url,
                data=json.dumps(record, default=str).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status in (200, 201, 202):
                    self.logger.info("SDN POST succeeded for entity=%s", record.get("entity_id"))
                else:
                    self.logger.warning("SDN POST returned %s", resp.status)
        except Exception as exc:
            self.logger.warning("SDN POST failed: %s", type(exc).__name__)

    def _run_thermal_cmd(self, record: Dict[str, Any]) -> None:
        """Run optional thermal command with record as JSON on stdin (optional)."""
        try:
            import subprocess
            proc = subprocess.run(
                [self._thermal_cmd],
                input=json.dumps(record, default=str).encode("utf-8"),
                capture_output=True,
                timeout=10,
            )
            if proc.returncode == 0:
                self.logger.info("Thermal command succeeded for entity=%s", record.get("entity_id"))
            else:
                self.logger.warning("Thermal command exit %s: %s", proc.returncode, proc.stderr[:200] if proc.stderr else "")
        except Exception as exc:
            self.logger.warning("Thermal command failed: %s", type(exc).__name__)
