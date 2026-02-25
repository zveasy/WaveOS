"""WaveOS Agent — target-side installer, supervisor, and lifecycle manager."""

from waveos.agent.state_machine import AgentState, AgentStateMachine
from waveos.agent.manager import AgentManager
from waveos.agent.service_runner import ServiceRunner, ServiceStatus
from waveos.agent.evidence import DeploymentEvidence, collect_deployment_evidence

__all__ = [
    "AgentState",
    "AgentStateMachine",
    "AgentManager",
    "ServiceRunner",
    "ServiceStatus",
    "DeploymentEvidence",
    "collect_deployment_evidence",
]
