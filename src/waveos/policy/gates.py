"""V2: Policy enforcement gates — hard limits (SOC, temp, transformer) and deployment gates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from waveos.models import HealthScore, HealthStatus
from waveos.utils import get_logger

logger = get_logger("waveos.policy.gates")


@dataclass
class GateResult:
    """Result of a single gate check."""
    gate_id: str
    passed: bool
    message: str
    value: Optional[float] = None
    limit: Optional[float] = None


def check_soc_limit(soc_pct: Optional[float], min_soc_pct: float) -> GateResult:
    """Gate: do not discharge below min_soc_pct (e.g. 20%)."""
    if soc_pct is None:
        return GateResult("soc_min", True, "no SOC value to check")
    passed = soc_pct >= min_soc_pct
    return GateResult(
        "soc_min",
        passed,
        f"SOC {soc_pct}% {'>=' if passed else 'below'} limit {min_soc_pct}%",
        value=soc_pct,
        limit=min_soc_pct,
    )


def check_temp_limit(temp_c: Optional[float], max_temp_c: float) -> GateResult:
    """Gate: do not exceed max_temp_c."""
    if temp_c is None:
        return GateResult("temp_max", True, "no temperature to check")
    passed = temp_c <= max_temp_c
    return GateResult(
        "temp_max",
        passed,
        f"Temperature {temp_c}C {'<=' if passed else 'above'} limit {max_temp_c}C",
        value=temp_c,
        limit=max_temp_c,
    )


def check_health_gate(scores: List[HealthScore], allow_warn: bool = True) -> GateResult:
    """Gate: no FAIL health; optionally no WARN (deployment gate)."""
    fails = [s for s in scores if s.status == HealthStatus.FAIL]
    warns = [s for s in scores if s.status == HealthStatus.WARN]
    if fails:
        return GateResult(
            "health_no_fail",
            False,
            f"{len(fails)} entity(ies) in FAIL",
        )
    if not allow_warn and warns:
        return GateResult(
            "health_no_warn",
            False,
            f"{len(warns)} entity(ies) in WARN",
        )
    return GateResult("health_no_fail", True, "no FAIL; WARN allowed" if allow_warn else "no FAIL or WARN")


def run_gates(
    gates_config: List[Dict[str, Any]],
    scores: Optional[List[HealthScore]] = None,
    telemetry_aggregates: Optional[Dict[str, float]] = None,
) -> List[GateResult]:
    """Run configured gates. gates_config: list of {gate: soc_min|temp_max|health, ...params}."""
    results: List[GateResult] = []
    telemetry_aggregates = telemetry_aggregates or {}
    for cfg in gates_config:
        gate = cfg.get("gate")
        if gate == "soc_min":
            min_soc = float(cfg.get("min_soc_pct", 20))
            soc = telemetry_aggregates.get("soc_pct") or telemetry_aggregates.get("battery_soc_pct")
            results.append(check_soc_limit(soc, min_soc))
        elif gate == "temp_max":
            max_temp = float(cfg.get("max_temp_c", 60))
            temp = telemetry_aggregates.get("temperature_c") or telemetry_aggregates.get("temp_c")
            results.append(check_temp_limit(temp, max_temp))
        elif gate == "health":
            allow_warn = cfg.get("allow_warn", True)
            results.append(check_health_gate(scores or [], allow_warn=allow_warn))
    return results
