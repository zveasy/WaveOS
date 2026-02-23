"""
Incident lifecycle: open/close, timeline, escalation rules, postmortem pack generation.

Production incident object with status, escalation (notify operator, require approval, lock enforcement),
and postmortem pack for forensics.
"""

from __future__ import annotations

import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from waveos.utils import get_logger

logger = get_logger("waveos.incident_lifecycle")


INCIDENT_STATUS_OPEN = "open"
INCIDENT_STATUS_ESCALATED = "escalated"
INCIDENT_STATUS_CLOSED = "closed"


def incident_create(
    incident_id: str,
    run_id: str,
    severity: str,
    summary: str,
    timeline: List[Dict[str, Any]],
    actions_taken: List[Dict[str, Any]],
    outcomes: Dict[str, Any],
    recommended_next_steps: List[str],
    run_meta_snapshot: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Create incident record with status=open."""
    now = datetime.now(timezone.utc).isoformat()
    return {
        "incident_id": incident_id,
        "run_id": run_id,
        "status": INCIDENT_STATUS_OPEN,
        "severity": severity,
        "summary": summary,
        "timeline": timeline,
        "actions_taken": actions_taken,
        "outcomes": outcomes,
        "recommended_next_steps": recommended_next_steps,
        "run_meta_snapshot": run_meta_snapshot or {},
        "created_at": now,
        "closed_at": None,
        "escalated_at": None,
        "escalation_reason": None,
        "postmortem_path": None,
    }


def incident_escalate(
    incident: Dict[str, Any],
    reason: str,
    notify_operator: bool = True,
    require_approval: bool = False,
    lock_enforcement: bool = False,
) -> Dict[str, Any]:
    """Mark incident as escalated; optional flags for operator notify, approval, lock enforcement."""
    now = datetime.now(timezone.utc).isoformat()
    out = dict(incident)
    out["status"] = INCIDENT_STATUS_ESCALATED
    out["escalated_at"] = now
    out["escalation_reason"] = reason
    out["escalation_notify_operator"] = notify_operator
    out["escalation_require_approval"] = require_approval
    out["escalation_lock_enforcement"] = lock_enforcement
    return out


def incident_close(incident: Dict[str, Any], postmortem_path: Optional[str] = None) -> Dict[str, Any]:
    """Mark incident closed; optional path to postmortem doc."""
    now = datetime.now(timezone.utc).isoformat()
    out = dict(incident)
    out["status"] = INCIDENT_STATUS_CLOSED
    out["closed_at"] = now
    if postmortem_path:
        out["postmortem_path"] = postmortem_path
    return out


def build_postmortem_pack(
    incident: Dict[str, Any],
    output_dir: Path,
    include_artifacts: Optional[List[Path]] = None,
) -> Path:
    """Generate postmortem zip: incident JSON + timeline + optional artifact paths."""
    pack_name = f"postmortem_{incident.get('incident_id', 'inc')}.zip"
    pack_path = output_dir / pack_name
    output_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(pack_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("incident.json", json.dumps(incident, indent=2, default=str))
        zf.writestr("timeline.json", json.dumps(incident.get("timeline", []), indent=2, default=str))
        if include_artifacts:
            for p in include_artifacts:
                if p.is_file():
                    zf.write(p, p.name)
    logger.info("Postmortem pack written to %s", pack_path)
    return pack_path
