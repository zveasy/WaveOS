"""
Change workflow: log bundle and policy changes for audit (Compliance Phase 3).
Append-only deployment_changes.jsonl with event, bundle_id, timestamp, optional approver/comment.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.change_log")


def append_change_log(
    log_path: Path,
    event: str,
    bundle_id: Optional[str] = None,
    *,
    approver: Optional[str] = None,
    comment: Optional[str] = None,
    policy_path: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    """Append a change event to the deployment/policy change log (Compliance Phase 3)."""
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    entry: Dict[str, Any] = {
        "timestamp_utc": utc_now().isoformat(),
        "event": event,
    }
    if bundle_id is not None:
        entry["bundle_id"] = bundle_id
    if approver:
        entry["approver"] = approver
    if comment:
        entry["comment"] = comment
    if policy_path:
        entry["policy_path"] = policy_path
    if extra:
        entry.update(extra)
    line = json.dumps(entry, default=str) + "\n"
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(line)
    logger.debug("Change log: %s at %s", event, log_path)


def get_recent_changes(log_path: Path, limit: int = 50) -> List[Dict[str, Any]]:
    """Read recent change log entries (newest first)."""
    log_path = Path(log_path)
    if not log_path.is_file():
        return []
    entries: List[Dict[str, Any]] = []
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    entries.reverse()
    return entries[:limit]
