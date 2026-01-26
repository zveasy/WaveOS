from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List


class Role(str, Enum):
    VIEWER = "viewer"
    OPERATOR = "operator"
    ADMIN = "admin"


class Permission(str, Enum):
    VIEW_REPORTS = "view_reports"
    RUN_PIPELINE = "run_pipeline"
    MODIFY_POLICY = "modify_policy"


ROLE_PERMISSIONS: Dict[Role, List[Permission]] = {
    Role.VIEWER: [Permission.VIEW_REPORTS],
    Role.OPERATOR: [Permission.VIEW_REPORTS, Permission.RUN_PIPELINE],
    Role.ADMIN: [Permission.VIEW_REPORTS, Permission.RUN_PIPELINE, Permission.MODIFY_POLICY],
}


@dataclass
class Principal:
    name: str
    role: Role


def authorize(principal: Principal, permission: Permission) -> bool:
    return permission in ROLE_PERMISSIONS.get(principal.role, [])
