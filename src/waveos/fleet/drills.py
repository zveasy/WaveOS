"""Failure drills framework — simulate registry outage, network partition, clock drift, mirror staleness."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.fleet.drills")


class DrillType(str, Enum):
    REGISTRY_OUTAGE = "registry_outage"
    NETWORK_PARTITION = "network_partition"
    MIRROR_STALE = "mirror_stale"
    CLOCK_DRIFT = "clock_drift"
    AGENT_CRASH = "agent_crash"
    DISK_FULL = "disk_full"


@dataclass
class FailureDrill:
    """Definition of a failure drill."""
    name: str
    drill_type: DrillType
    description: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)
    expected_behavior: str = ""
    recovery_steps: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"name": self.name, "drill_type": self.drill_type.value, "description": self.description,
                "parameters": self.parameters, "expected_behavior": self.expected_behavior,
                "recovery_steps": self.recovery_steps}


@dataclass
class DrillResult:
    """Result of executing a failure drill."""
    drill_name: str
    passed: bool
    observations: List[str] = field(default_factory=list)
    recovery_verified: bool = False
    duration_sec: float = 0.0
    timestamp: str = ""

    def to_dict(self) -> dict:
        return {"drill_name": self.drill_name, "passed": self.passed,
                "observations": self.observations, "recovery_verified": self.recovery_verified,
                "duration_sec": self.duration_sec, "timestamp": self.timestamp or utc_now().isoformat()}


DEFAULT_DRILLS: List[FailureDrill] = [
    FailureDrill(name="registry_down", drill_type=DrillType.REGISTRY_OUTAGE,
                 description="Simulate registry becoming unreachable",
                 expected_behavior="Agent continues with cached state, logs warning, retries with backoff",
                 recovery_steps=["Restore registry", "Agent auto-reconnects", "Verify state convergence"]),
    FailureDrill(name="network_split", drill_type=DrillType.NETWORK_PARTITION,
                 description="Simulate site disconnected for extended period",
                 expected_behavior="Agent operates in offline mode, local mirror serves cached bundles",
                 recovery_steps=["Restore connectivity", "Mirror sync", "Fleet reconciliation"]),
    FailureDrill(name="stale_mirror", drill_type=DrillType.MIRROR_STALE,
                 description="Mirror has not synced in >30 days",
                 expected_behavior="Agent reports stale mirror warning, blocks risky updates",
                 recovery_steps=["Force mirror sync", "Verify bundle freshness", "Resume normal updates"]),
    FailureDrill(name="clock_skew", drill_type=DrillType.CLOCK_DRIFT,
                 description="System clock is significantly wrong (hours/days)",
                 expected_behavior="Agent detects clock anomaly, uses monotonic counters for ordering",
                 recovery_steps=["Sync NTP", "Verify cert validity", "Resume operations"]),
    FailureDrill(name="disk_pressure", drill_type=DrillType.DISK_FULL,
                 description="Disk is nearly full during update",
                 expected_behavior="Storage policy triggers cleanup, install fails safely without corruption",
                 recovery_steps=["Run storage policy", "Verify rollback capability", "Retry update"]),
]


def run_drill(drill: FailureDrill, simulate_fn: Optional[Callable] = None) -> DrillResult:
    """Execute a failure drill (or return a plan if no simulate_fn)."""
    import time
    start = time.monotonic()
    observations: List[str] = []
    passed = True
    if simulate_fn:
        try:
            sim_result = simulate_fn(drill)
            observations.append(f"Simulation executed: {sim_result}")
            passed = bool(sim_result)
        except Exception as exc:
            observations.append(f"Simulation error: {exc}")
            passed = False
    else:
        observations.append("Dry run — no simulation function provided")
        observations.append(f"Expected: {drill.expected_behavior}")
        for i, step in enumerate(drill.recovery_steps, 1):
            observations.append(f"Recovery step {i}: {step}")
    duration = time.monotonic() - start
    return DrillResult(drill_name=drill.name, passed=passed, observations=observations,
                       recovery_verified=simulate_fn is not None, duration_sec=round(duration, 3),
                       timestamp=utc_now().isoformat())


def list_drills() -> List[FailureDrill]:
    return list(DEFAULT_DRILLS)
