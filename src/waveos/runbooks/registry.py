"""
Runbook registry: id, title, trigger condition, steps, optional script.

Use: waveos runbook list, waveos runbook run <id>
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from waveos.utils import get_logger

logger = get_logger("waveos.runbooks")


@dataclass
class RunbookStep:
    title: str
    command: Optional[str] = None  # human-readable or script path
    description: str = ""


@dataclass
class Runbook:
    id: str
    title: str
    trigger: str  # e.g. "telemetry_stale", "actuator_down", "scoring_spike"
    steps: List[RunbookStep] = field(default_factory=list)
    description: str = ""


_REGISTRY: Dict[str, Runbook] = {}


def _register(rb: Runbook) -> None:
    _REGISTRY[rb.id] = rb


def _default_runbooks() -> None:
    if _REGISTRY:
        return
    _register(
        Runbook(
            id="telemetry_stale",
            title="Telemetry stale or missing",
            trigger="telemetry_stale",
            description="When telemetry ingest has not received data within the expected window.",
            steps=[
                RunbookStep("Check ingestion endpoint", description="Verify WAVEOS_INGESTION_URL or file input path is reachable."),
                RunbookStep("Check collector", command="waveos health-check", description="Run health-check to validate config and license."),
                RunbookStep("Review last run", command="ls -la out/", description="Inspect out/ for last run_meta.json and report.html."),
            ],
        )
    )
    _register(
        Runbook(
            id="actuator_down",
            title="Actuator unreachable or failing",
            trigger="actuator_down",
            description="When action outcomes show failed or actuator HTTP/timeout errors.",
            steps=[
                RunbookStep("Check actuator URL", description="Verify WAVEOS_ACTUATOR_SDN_URL or adapter gateway URLs."),
                RunbookStep("Inspect outcomes", command="cat out/actuator/action_outcomes.jsonl", description="Review action_outcomes.jsonl for failure messages."),
                RunbookStep("Disable enforce if needed", description="Set WAVEOS_ENFORCE_ACTIONS=false to run in advisory-only mode."),
            ],
        )
    )
    _register(
        Runbook(
            id="scoring_spike",
            title="Scoring spike or widespread FAIL",
            trigger="scoring_spike",
            description="When health scores drop or many entities go FAIL.",
            steps=[
                RunbookStep("Review health summary", command="cat out/health_summary.json", description="Check which entities and drivers failed."),
                RunbookStep("Compare to baseline", description="Ensure baseline was built from a known-good period; consider re-baseline if topology changed."),
                RunbookStep("Check incidents", description="Query persistence for recent incidents: get_recent_incidents()."),
            ],
        )
    )


def list_runbooks() -> List[Runbook]:
    _default_runbooks()
    return list(_REGISTRY.values())


def get_runbook(runbook_id: str) -> Optional[Runbook]:
    _default_runbooks()
    return _REGISTRY.get(runbook_id)


def run_runbook(runbook_id: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Execute a runbook (run steps; optional script hooks). Returns summary.
    Currently steps are informational; no automatic script execution.
    """
    rb = get_runbook(runbook_id)
    if not rb:
        return {"ok": False, "error": f"Runbook not found: {runbook_id}"}
    context = context or {}
    results: List[Dict[str, Any]] = []
    for i, step in enumerate(rb.steps):
        results.append({"step": i + 1, "title": step.title, "description": step.description, "command": step.command, "executed": False})
    logger.info("Runbook %s: %s steps (informational)", runbook_id, len(rb.steps))
    return {"ok": True, "runbook_id": runbook_id, "title": rb.title, "steps": results}
