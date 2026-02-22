"""V3: Node health — mark unhealthy after missed heartbeats; failover support."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Optional, Set

from waveos.heartbeat import read_latest_heartbeats
from waveos.utils import get_logger

logger = get_logger("waveos.node_health")


def healthy_nodes(
    heartbeat_path: Path,
    max_age_seconds: float = 120.0,
    max_per_node: int = 1,
) -> Dict[str, bool]:
    """Return {node_id: True} for nodes with a heartbeat newer than max_age_seconds."""
    latest = read_latest_heartbeats(heartbeat_path, max_per_node=max_per_node)
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=max_age_seconds)
    result: Dict[str, bool] = {}
    for node_id, rec in latest.items():
        ts = rec.get("timestamp")
        if not ts:
            result[node_id] = False
            continue
        try:
            if isinstance(ts, str):
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            else:
                dt = ts
            result[node_id] = dt >= cutoff
        except (ValueError, TypeError) as exc:
            logger.debug("Invalid heartbeat timestamp for node %s: %s", node_id, type(exc).__name__)
            result[node_id] = False
    return result


def unhealthy_node_ids(heartbeat_path: Path, max_age_seconds: float = 120.0) -> Set[str]:
    """Return set of node IDs that have missed heartbeats (for failover exclusion)."""
    status = healthy_nodes(heartbeat_path, max_age_seconds=max_age_seconds)
    return {nid for nid, ok in status.items() if not ok}
