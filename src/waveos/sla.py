"""V3: SLA metrics — uptime, error rate, cross-site/tenant labels for dashboards."""

from __future__ import annotations

from typing import Any, Dict, Optional

from waveos.utils import get_logger

logger = get_logger("waveos.sla")

_sla_counters: Optional[Dict[str, Any]] = None


def _get_sla_registry() -> Any:
    global _sla_counters
    if _sla_counters is not None:
        return _sla_counters
    try:
        from waveos.utils.metrics import init_registry
        registry = init_registry()
        from prometheus_client import Counter
        _sla_counters = {
            "runs_total": Counter("waveos_sla_runs_total", "Total pipeline runs", ["tenant_id", "site_id"], registry=registry),
            "runs_failed": Counter("waveos_sla_runs_failed_total", "Failed pipeline runs", ["tenant_id", "site_id"], registry=registry),
            "run_duration_seconds": None,  # Histogram if needed
        }
        return _sla_counters
    except Exception as exc:
        logger.debug("SLA metrics not available: %s", type(exc).__name__)
        _sla_counters = {}
        return _sla_counters


def record_run_success(tenant_id: str = "", site_id: str = "") -> None:
    """Record a successful run for SLA (tenant/site labels)."""
    reg = _get_sla_registry()
    if reg and "runs_total" in reg:
        reg["runs_total"].labels(tenant_id=tenant_id or "default", site_id=site_id or "default").inc()


def record_run_failure(tenant_id: str = "", site_id: str = "") -> None:
    """Record a failed run for SLA."""
    reg = _get_sla_registry()
    if reg and "runs_failed" in reg:
        reg["runs_failed"].labels(tenant_id=tenant_id or "default", site_id=site_id or "default").inc()
