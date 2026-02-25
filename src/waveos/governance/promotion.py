"""Promotion gates — dev -> staging -> prod requires approvals, signed policy, separation of duties."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.governance.promotion")

CHANNEL_ORDER = ["dev", "staging", "prod", "mission-critical"]


@dataclass
class PromotionGate:
    """A gate that must pass for promotion to succeed."""
    name: str
    gate_type: str = "approval"  # approval | signature | ci_only | health | sbom | attestation
    required: bool = True
    threshold: float = 0.0

    def to_dict(self) -> dict:
        return {"name": self.name, "gate_type": self.gate_type, "required": self.required, "threshold": self.threshold}

    @classmethod
    def from_dict(cls, d: dict) -> PromotionGate:
        return cls(**{k: d[k] for k in d if k in cls.__dataclass_fields__})


@dataclass
class PromotionRequest:
    """Request to promote a bundle from one channel to another."""
    bundle_id: str
    from_channel: str
    to_channel: str
    requester: str
    approvers: List[str] = field(default_factory=list)
    builder: str = ""
    has_signature: bool = False
    has_attestation: bool = False
    has_sbom: bool = False
    health_score: float = 100.0
    is_ci: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"bundle_id": self.bundle_id, "from_channel": self.from_channel,
                "to_channel": self.to_channel, "requester": self.requester,
                "approvers": self.approvers, "builder": self.builder,
                "has_signature": self.has_signature, "has_attestation": self.has_attestation,
                "has_sbom": self.has_sbom, "health_score": self.health_score,
                "is_ci": self.is_ci, "metadata": self.metadata}


@dataclass
class PromotionResult:
    """Result of evaluating a promotion request."""
    approved: bool
    gates_passed: List[Dict[str, Any]] = field(default_factory=list)
    gates_failed: List[Dict[str, Any]] = field(default_factory=list)
    violations: List[str] = field(default_factory=list)
    timestamp: str = ""

    def to_dict(self) -> dict:
        return {"approved": self.approved, "gates_passed": self.gates_passed,
                "gates_failed": self.gates_failed, "violations": self.violations,
                "timestamp": self.timestamp or utc_now().isoformat()}


DEFAULT_PROMOTION_GATES: Dict[str, List[PromotionGate]] = {
    "staging": [PromotionGate(name="signature", gate_type="signature"), PromotionGate(name="ci_build", gate_type="ci_only")],
    "prod": [PromotionGate(name="signature", gate_type="signature"), PromotionGate(name="attestation", gate_type="attestation"),
             PromotionGate(name="sbom", gate_type="sbom"), PromotionGate(name="approval", gate_type="approval"),
             PromotionGate(name="separation", gate_type="approval"), PromotionGate(name="health", gate_type="health", threshold=70.0)],
    "mission-critical": [PromotionGate(name="signature", gate_type="signature"), PromotionGate(name="attestation", gate_type="attestation"),
                         PromotionGate(name="sbom", gate_type="sbom"), PromotionGate(name="dual_approval", gate_type="approval", threshold=2),
                         PromotionGate(name="health", gate_type="health", threshold=90.0)],
}


def evaluate_promotion(request: PromotionRequest, gates: Optional[List[PromotionGate]] = None) -> PromotionResult:
    """Evaluate a promotion request against gates."""
    if gates is None:
        gates = DEFAULT_PROMOTION_GATES.get(request.to_channel, [])
    result = PromotionResult(approved=True, timestamp=utc_now().isoformat())
    from_idx = CHANNEL_ORDER.index(request.from_channel) if request.from_channel in CHANNEL_ORDER else -1
    to_idx = CHANNEL_ORDER.index(request.to_channel) if request.to_channel in CHANNEL_ORDER else -1
    if to_idx <= from_idx and from_idx >= 0:
        result.violations.append(f"Cannot promote backwards: {request.from_channel} -> {request.to_channel}")
        result.approved = False
        return result
    for gate in gates:
        passed = True
        detail: Dict[str, Any] = {"gate": gate.name, "type": gate.gate_type}
        if gate.gate_type == "signature" and not request.has_signature:
            passed = False
            detail["reason"] = "Bundle not signed"
        elif gate.gate_type == "attestation" and not request.has_attestation:
            passed = False
            detail["reason"] = "No build attestation"
        elif gate.gate_type == "sbom" and not request.has_sbom:
            passed = False
            detail["reason"] = "No SBOM"
        elif gate.gate_type == "ci_only" and not request.is_ci:
            passed = False
            detail["reason"] = "Only CI/CD can promote to this channel"
        elif gate.gate_type == "approval":
            min_approvers = int(gate.threshold) if gate.threshold > 0 else 1
            if len(request.approvers) < min_approvers:
                passed = False
                detail["reason"] = f"Need {min_approvers} approvers, got {len(request.approvers)}"
            if request.builder and request.builder in request.approvers:
                passed = False
                detail["reason"] = f"Builder ({request.builder}) cannot approve own promotion (separation of duties)"
        elif gate.gate_type == "health":
            if request.health_score < gate.threshold:
                passed = False
                detail["reason"] = f"Health {request.health_score} < {gate.threshold}"
        detail["passed"] = passed
        if passed:
            result.gates_passed.append(detail)
        else:
            result.gates_failed.append(detail)
            if gate.required:
                result.approved = False
                result.violations.append(detail.get("reason", gate.name))
    return result
