"""Separation of duties — ensure builder != approver, enforce role-based access for governance actions."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Tuple

from waveos.utils import get_logger

logger = get_logger("waveos.governance.separation")


class DutyRole(str, Enum):
    BUILDER = "builder"
    APPROVER = "approver"
    DEPLOYER = "deployer"
    AUDITOR = "auditor"
    ADMIN = "admin"


@dataclass
class DutyAssignment:
    identity: str
    roles: List[DutyRole] = field(default_factory=list)
    site_scope: List[str] = field(default_factory=list)
    channel_scope: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"identity": self.identity, "roles": [r.value for r in self.roles],
                "site_scope": self.site_scope, "channel_scope": self.channel_scope}


class SeparationOfDuties:
    """Enforces separation of duties for governance actions."""

    def __init__(self) -> None:
        self._assignments: Dict[str, DutyAssignment] = {}

    def assign(self, identity: str, roles: List[DutyRole],
               site_scope: List[str] = None, channel_scope: List[str] = None) -> None:
        self._assignments[identity] = DutyAssignment(
            identity=identity, roles=roles,
            site_scope=site_scope or [], channel_scope=channel_scope or [],
        )

    def check_can_approve(self, approver: str, builder: str) -> Tuple[bool, str]:
        if approver == builder:
            return False, "Builder cannot approve own build (separation of duties)"
        assignment = self._assignments.get(approver)
        if assignment and DutyRole.APPROVER not in assignment.roles and DutyRole.ADMIN not in assignment.roles:
            return False, f"{approver} does not have approver role"
        return True, ""

    def check_can_deploy(self, deployer: str, channel: str) -> Tuple[bool, str]:
        assignment = self._assignments.get(deployer)
        if not assignment:
            return True, ""
        if DutyRole.DEPLOYER not in assignment.roles and DutyRole.ADMIN not in assignment.roles:
            return False, f"{deployer} does not have deployer role"
        if assignment.channel_scope and channel not in assignment.channel_scope:
            return False, f"{deployer} not authorized for channel {channel}"
        return True, ""

    def check_can_build(self, builder: str) -> Tuple[bool, str]:
        assignment = self._assignments.get(builder)
        if not assignment:
            return True, ""
        if DutyRole.BUILDER not in assignment.roles and DutyRole.ADMIN not in assignment.roles:
            return False, f"{builder} does not have builder role"
        return True, ""

    def get_assignments(self) -> List[Dict[str, Any]]:
        return [a.to_dict() for a in self._assignments.values()]
