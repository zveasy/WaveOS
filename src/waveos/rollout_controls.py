"""WaveOS Rollout Controls — channel policies, health gates, and automatic rollback."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.rollout_controls")


class DeploymentChannel(str, Enum):
    DEV = "dev"
    STAGING = "staging"
    PROD = "prod"
    MISSION_CRITICAL = "mission-critical"


@dataclass
class ChannelPolicy:
    """Policy for a deployment channel."""
    channel: DeploymentChannel
    require_signature: bool = False
    require_attestation: bool = False
    require_sbom: bool = False
    min_health_score: float = 0.0
    require_approval: bool = False
    approval_count: int = 1
    allowed_sources: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "channel": self.channel.value,
            "require_signature": self.require_signature,
            "require_attestation": self.require_attestation,
            "require_sbom": self.require_sbom,
            "min_health_score": self.min_health_score,
            "require_approval": self.require_approval,
            "approval_count": self.approval_count,
            "allowed_sources": self.allowed_sources,
        }

    @classmethod
    def from_dict(cls, d: dict) -> ChannelPolicy:
        return cls(
            channel=DeploymentChannel(d.get("channel", "dev")),
            require_signature=d.get("require_signature", False),
            require_attestation=d.get("require_attestation", False),
            require_sbom=d.get("require_sbom", False),
            min_health_score=d.get("min_health_score", 0.0),
            require_approval=d.get("require_approval", False),
            approval_count=d.get("approval_count", 1),
            allowed_sources=d.get("allowed_sources", []),
        )


DEFAULT_POLICIES: Dict[str, ChannelPolicy] = {
    "dev": ChannelPolicy(channel=DeploymentChannel.DEV),
    "staging": ChannelPolicy(channel=DeploymentChannel.STAGING, require_signature=True, min_health_score=50.0),
    "prod": ChannelPolicy(channel=DeploymentChannel.PROD, require_signature=True, require_attestation=True, require_sbom=True, min_health_score=70.0, require_approval=True),
    "mission-critical": ChannelPolicy(channel=DeploymentChannel.MISSION_CRITICAL, require_signature=True, require_attestation=True, require_sbom=True, min_health_score=90.0, require_approval=True, approval_count=2),
}


def get_channel_policy(channel: str) -> ChannelPolicy:
    return DEFAULT_POLICIES.get(channel, DEFAULT_POLICIES["dev"])


@dataclass
class HealthGate:
    """Health gate for activation decisions."""
    name: str
    check_type: str = "health_score"  # health_score | check_passed | no_crash_loop | latency_ok
    threshold: float = 70.0
    required: bool = True

    def to_dict(self) -> dict:
        return {"name": self.name, "check_type": self.check_type, "threshold": self.threshold, "required": self.required}


@dataclass
class RollbackTrigger:
    """Condition that triggers automatic rollback."""
    name: str
    trigger_type: str  # crash_loop | health_below | latency_regression | invariant_failure | drift_exceeded
    threshold: float = 0.0
    window_sec: int = 300

    def to_dict(self) -> dict:
        return {"name": self.name, "trigger_type": self.trigger_type, "threshold": self.threshold, "window_sec": self.window_sec}


DEFAULT_ROLLBACK_TRIGGERS: List[RollbackTrigger] = [
    RollbackTrigger(name="crash_loop", trigger_type="crash_loop", threshold=3, window_sec=300),
    RollbackTrigger(name="health_degraded", trigger_type="health_below", threshold=30.0),
    RollbackTrigger(name="latency_spike", trigger_type="latency_regression", threshold=2.0),
    RollbackTrigger(name="drift_exceeded", trigger_type="drift_exceeded", threshold=50.0),
]


def evaluate_health_gates(
    gates: List[HealthGate],
    health_score: float = 100.0,
    checks_passed: Optional[Dict[str, bool]] = None,
) -> tuple[bool, List[Dict[str, Any]]]:
    """Evaluate health gates. Returns (all_passed, results)."""
    results: List[Dict[str, Any]] = []
    all_passed = True
    for gate in gates:
        passed = True
        if gate.check_type == "health_score":
            passed = health_score >= gate.threshold
        elif gate.check_type == "check_passed" and checks_passed:
            passed = checks_passed.get(gate.name, False)
        results.append({"gate": gate.name, "passed": passed, "required": gate.required})
        if not passed and gate.required:
            all_passed = False
    return all_passed, results


def evaluate_rollback_triggers(
    triggers: List[RollbackTrigger],
    crash_count: int = 0,
    health_score: float = 100.0,
    latency_ratio: float = 1.0,
    drift_score: float = 0.0,
) -> tuple[bool, List[Dict[str, Any]]]:
    """Check if any rollback triggers fire. Returns (should_rollback, triggered_list)."""
    triggered: List[Dict[str, Any]] = []
    for trigger in triggers:
        fired = False
        if trigger.trigger_type == "crash_loop":
            fired = crash_count >= trigger.threshold
        elif trigger.trigger_type == "health_below":
            fired = health_score < trigger.threshold
        elif trigger.trigger_type == "latency_regression":
            fired = latency_ratio >= trigger.threshold
        elif trigger.trigger_type == "drift_exceeded":
            fired = drift_score >= trigger.threshold
        if fired:
            triggered.append({"trigger": trigger.name, "type": trigger.trigger_type, "threshold": trigger.threshold})
    return len(triggered) > 0, triggered


def check_channel_requirements(
    channel: str,
    has_signature: bool = False,
    has_attestation: bool = False,
    has_sbom: bool = False,
    health_score: float = 100.0,
    has_approval: bool = False,
) -> tuple[bool, List[str]]:
    """Check if a bundle meets channel requirements. Returns (ok, violations)."""
    policy = get_channel_policy(channel)
    violations: List[str] = []
    if policy.require_signature and not has_signature:
        violations.append(f"Channel {channel} requires signature")
    if policy.require_attestation and not has_attestation:
        violations.append(f"Channel {channel} requires attestation")
    if policy.require_sbom and not has_sbom:
        violations.append(f"Channel {channel} requires SBOM")
    if health_score < policy.min_health_score:
        violations.append(f"Channel {channel} requires health score >= {policy.min_health_score}, got {health_score}")
    if policy.require_approval and not has_approval:
        violations.append(f"Channel {channel} requires approval")
    return len(violations) == 0, violations
