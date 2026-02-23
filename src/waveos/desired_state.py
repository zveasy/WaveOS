"""
Desired-state reconciliation (fleet-grade ops): desired state model, reconcile loop, drift correction.

Per site/device we maintain desired state; periodic reconcile compares desired vs actual (from runs/telemetry)
and applies drift correction with safe fallback.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from waveos.utils import get_logger

logger = get_logger("waveos.desired_state")


class DriftStrategy(str, Enum):
    """How to correct drift when desired != actual."""
    APPLY = "apply"          # Apply desired (safe actions only when gate passes)
    ALERT_ONLY = "alert_only"
    FALLBACK_SAFE = "fallback_safe"  # Revert to last known good or safe default


@dataclass
class DesiredStateRecord:
    """Desired state for a site or device."""
    entity_type: str  # "site" | "device"
    entity_id: str
    desired: Dict[str, Any]
    version: str
    updated_at: str
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DriftResult:
    """Result of comparing desired vs actual."""
    entity_id: str
    in_sync: bool
    desired: Dict[str, Any]
    actual: Dict[str, Any]
    diff_keys: List[str]
    recommended_action: Optional[str] = None


# In-memory store; can be backed by persistence later
_desired: Dict[tuple, DesiredStateRecord] = {}  # (entity_type, entity_id) -> record


def set_desired(entity_type: str, entity_id: str, desired: Dict[str, Any], version: str = "1") -> None:
    now = datetime.now(timezone.utc).isoformat()
    key = (entity_type, entity_id)
    _desired[key] = DesiredStateRecord(
        entity_type=entity_type,
        entity_id=entity_id,
        desired=desired,
        version=version,
        updated_at=now,
        meta={},
    )


def get_desired(entity_type: str, entity_id: str) -> Optional[DesiredStateRecord]:
    return _desired.get((entity_type, entity_id))


def list_desired(entity_type: Optional[str] = None) -> List[DesiredStateRecord]:
    if entity_type is None:
        return list(_desired.values())
    return [r for r in _desired.values() if r.entity_type == entity_type]


def reconcile_one(
    entity_type: str,
    entity_id: str,
    actual: Dict[str, Any],
    strategy: DriftStrategy = DriftStrategy.APPLY,
) -> Optional[DriftResult]:
    """Compare desired vs actual for one entity; return drift result."""
    record = get_desired(entity_type, entity_id)
    if not record:
        return None
    desired = record.desired
    diff_keys = [k for k in set(desired) | set(actual) if desired.get(k) != actual.get(k)]
    in_sync = len(diff_keys) == 0
    action = None
    if not in_sync and strategy == DriftStrategy.APPLY:
        action = "correct_drift"
    elif not in_sync and strategy == DriftStrategy.ALERT_ONLY:
        action = "alert"
    elif not in_sync and strategy == DriftStrategy.FALLBACK_SAFE:
        action = "fallback_safe"
    return DriftResult(
        entity_id=entity_id,
        in_sync=in_sync,
        desired=desired,
        actual=actual,
        diff_keys=diff_keys,
        recommended_action=action,
    )


def reconcile_loop(
    actual_lookup: Callable[[str, str], Optional[Dict[str, Any]]],
    entity_type: str = "device",
    strategy: DriftStrategy = DriftStrategy.APPLY,
) -> List[DriftResult]:
    """Run reconciliation for all desired state records of given type. actual_lookup(entity_type, entity_id) -> actual state dict."""
    results: List[DriftResult] = []
    for record in list_desired(entity_type):
        actual = actual_lookup(entity_type, record.entity_id)
        if actual is None:
            continue
        r = reconcile_one(entity_type, record.entity_id, actual, strategy=strategy)
        if r:
            results.append(r)
    return results
