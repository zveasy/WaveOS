from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional


class Role(str, Enum):
    VIEWER = "viewer"
    OPERATOR = "operator"
    ADMIN = "admin"


class Clearance(str, Enum):
    """V3: Clearance level for DoD/sensitive distribution. Higher ordinal = more sensitive."""
    UNCLASSIFIED = "unclassified"
    RESTRICTED = "restricted"
    CONFIDENTIAL = "confidential"
    SECRET = "secret"


class Permission(str, Enum):
    VIEW_REPORTS = "view_reports"
    RUN_PIPELINE = "run_pipeline"
    MODIFY_POLICY = "modify_policy"
    DEPLOY_BUNDLE = "deploy_bundle"  # V3: gated by clearance
    MANAGE_NODES = "manage_nodes"  # V3: federated control


ROLE_PERMISSIONS: Dict[Role, List[Permission]] = {
    Role.VIEWER: [Permission.VIEW_REPORTS],
    Role.OPERATOR: [Permission.VIEW_REPORTS, Permission.RUN_PIPELINE],
    Role.ADMIN: [Permission.VIEW_REPORTS, Permission.RUN_PIPELINE, Permission.MODIFY_POLICY, Permission.DEPLOY_BUNDLE, Permission.MANAGE_NODES],
}

# V3: Minimum clearance required for permission (optional)
PERMISSION_CLEARANCE: Dict[Permission, Clearance] = {
    Permission.DEPLOY_BUNDLE: Clearance.CONFIDENTIAL,
    Permission.MANAGE_NODES: Clearance.RESTRICTED,
}


@dataclass
class Principal:
    name: str
    role: Role
    clearance: Optional[Clearance] = None  # V3


def authorize(principal: Principal, permission: Permission) -> bool:
    if permission not in ROLE_PERMISSIONS.get(principal.role, []):
        return False
    required = PERMISSION_CLEARANCE.get(permission)
    if required is not None and principal.clearance is not None:
        clearances = list(Clearance)
        if clearances.index(principal.clearance) < clearances.index(required):
            return False
    return True
