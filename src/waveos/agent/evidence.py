"""Deployment evidence packs for audit and compliance."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.agent.evidence")


@dataclass
class DeploymentEvidence:
    """Evidence pack for a single deployment event."""
    bundle_id: str
    timestamp: str = ""
    agent_state: str = ""
    steps: List[Dict[str, Any]] = field(default_factory=list)
    verification_result: Optional[Dict[str, Any]] = None
    preflight_result: Optional[Dict[str, Any]] = None
    install_result: Optional[Dict[str, Any]] = None
    activation_result: Optional[Dict[str, Any]] = None
    health_timeline: List[Dict[str, Any]] = field(default_factory=list)
    rollback_events: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "bundle_id": self.bundle_id,
            "timestamp": self.timestamp or utc_now().isoformat(),
            "agent_state": self.agent_state,
            "steps": self.steps,
            "verification_result": self.verification_result,
            "preflight_result": self.preflight_result,
            "install_result": self.install_result,
            "activation_result": self.activation_result,
            "health_timeline": self.health_timeline,
            "rollback_events": self.rollback_events,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict) -> DeploymentEvidence:
        return cls(
            bundle_id=d.get("bundle_id", ""),
            timestamp=d.get("timestamp", ""),
            agent_state=d.get("agent_state", ""),
            steps=d.get("steps", []),
            verification_result=d.get("verification_result"),
            preflight_result=d.get("preflight_result"),
            install_result=d.get("install_result"),
            activation_result=d.get("activation_result"),
            health_timeline=d.get("health_timeline", []),
            rollback_events=d.get("rollback_events", []),
            metadata=d.get("metadata", {}),
        )


def collect_deployment_evidence(
    bundle_id: str,
    steps: Optional[List[Dict[str, Any]]] = None,
    agent_state: str = "",
    verification: Optional[Dict[str, Any]] = None,
    preflight: Optional[Dict[str, Any]] = None,
    health_timeline: Optional[List[Dict[str, Any]]] = None,
    rollback_events: Optional[List[Dict[str, Any]]] = None,
) -> DeploymentEvidence:
    """Collect deployment evidence into a structured pack."""
    return DeploymentEvidence(
        bundle_id=bundle_id,
        timestamp=utc_now().isoformat(),
        agent_state=agent_state,
        steps=steps or [],
        verification_result=verification,
        preflight_result=preflight,
        health_timeline=health_timeline or [],
        rollback_events=rollback_events or [],
    )


def write_evidence_pack(evidence: DeploymentEvidence, output_dir: Path) -> Path:
    """Write evidence pack to disk."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"evidence_{evidence.bundle_id}_{evidence.timestamp.replace(':', '-')[:19]}.json"
    path.write_text(json.dumps(evidence.to_dict(), indent=2) + "\n", encoding="utf-8")
    return path


def load_evidence_pack(path: Path) -> Optional[DeploymentEvidence]:
    """Load evidence pack from disk."""
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return DeploymentEvidence.from_dict(data)
    except (json.JSONDecodeError, KeyError) as exc:
        logger.warning("Failed to load evidence pack: %s", exc)
        return None
