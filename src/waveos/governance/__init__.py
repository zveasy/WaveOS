"""WaveOS Governance — promotion gates, separation of duties, immutable audit, channel classification."""

from waveos.governance.promotion import PromotionGate, PromotionRequest, PromotionResult, evaluate_promotion
from waveos.governance.audit_chain import GovernanceAuditChain, GovernanceEvent
from waveos.governance.separation import SeparationOfDuties, DutyRole

__all__ = [
    "PromotionGate", "PromotionRequest", "PromotionResult", "evaluate_promotion",
    "GovernanceAuditChain", "GovernanceEvent",
    "SeparationOfDuties", "DutyRole",
]
