"""V3: Tenant run quotas — enforce max runs per tenant per period."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Optional

from waveos.utils import get_logger

logger = get_logger("waveos.quotas")

_run_timestamps: Dict[str, list] = defaultdict(list)


def check_quota(
    tenant_id: str,
    max_runs_per_hour: Optional[int],
    now: Optional[datetime] = None,
) -> bool:
    """Return True if tenant is under quota (allowed to run)."""
    if max_runs_per_hour is None or max_runs_per_hour <= 0:
        return True
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=1)
    timestamps = _run_timestamps[tenant_id or "default"]
    # prune old
    timestamps[:] = [t for t in timestamps if t >= cutoff]
    if len(timestamps) >= max_runs_per_hour:
        return False
    return True


def record_run(tenant_id: str, now: Optional[datetime] = None) -> None:
    """Record a run for quota accounting."""
    now = now or datetime.now(timezone.utc)
    _run_timestamps[tenant_id or "default"].append(now)
