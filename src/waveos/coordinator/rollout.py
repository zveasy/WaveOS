"""
Rollouts at scale: staged rollout across nodes (percent/cell-based), promotion gates, fleet rollback.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from waveos.utils import get_logger

logger = get_logger("waveos.coordinator.rollout")


class RolloutStatus(str, Enum):
    PENDING = "pending"
    CANARY = "canary"
    PROMOTING = "promoting"
    COMPLETED = "completed"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"


@dataclass
class RolloutSpec:
    deployment_id: str
    bundle_id: str
    policy_version: str
    node_ids: List[str]
    canary_percent: int = 0  # 0-100; 0 = full rollout
    canary_site_ids: Optional[List[str]] = None  # optional: canary by site first
    promotion_min_healthy_pct: float = 100.0  # promote only if this % of canary nodes healthy
    promotion_min_runs_ok: int = 1  # require at least N successful runs on canary before promote


def select_canary_nodes(
    node_ids: List[str],
    canary_percent: int,
    canary_site_ids: Optional[List[str]] = None,
    nodes_by_site: Optional[Dict[str, List[str]]] = None,
) -> List[str]:
    """Select which nodes get canary first (percent or by site)."""
    if canary_percent <= 0:
        return []
    if canary_site_ids and nodes_by_site:
        canary = []
        for sid in (canary_site_ids or []):
            canary.extend(nodes_by_site.get(sid, []))
        return [n for n in canary if n in node_ids]
    n = max(1, int(len(node_ids) * canary_percent / 100))
    return node_ids[:n]


def promotion_gate_passed(
    canary_node_ids: List[str],
    healthy_node_ids: List[str],
    run_ok_count_by_node: Dict[str, int],
    spec: RolloutSpec,
) -> bool:
    """True if canary nodes are healthy enough and have enough successful runs to promote."""
    if not canary_node_ids:
        return True
    healthy_set = set(healthy_node_ids)
    canary_healthy = [n for n in canary_node_ids if n in healthy_set]
    pct = 100.0 * len(canary_healthy) / len(canary_node_ids) if canary_node_ids else 100
    if pct < spec.promotion_min_healthy_pct:
        return False
    runs_ok = sum(run_ok_count_by_node.get(n, 0) for n in canary_node_ids)
    return runs_ok >= spec.promotion_min_runs_ok


def rollback_reason(
    canary_node_ids: List[str],
    healthy_node_ids: List[str],
    fail_count_by_node: Dict[str, int],
    max_failures_per_node: int = 2,
) -> Optional[str]:
    """If any canary node has too many failures, return rollback reason."""
    healthy_set = set(healthy_node_ids)
    for nid in canary_node_ids:
        if nid not in healthy_set:
            return f"node {nid} unhealthy"
        if fail_count_by_node.get(nid, 0) >= max_failures_per_node:
            return f"node {nid} exceeded failure threshold"
    return None
