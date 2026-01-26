from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, Optional

from waveos.utils.rbac import Principal, Role


@dataclass
class TokenAuth:
    token_to_role: Dict[str, Role]

    def authenticate(self, token: Optional[str]) -> Optional[Principal]:
        if not token:
            return None
        role = self.token_to_role.get(token)
        if not role:
            return None
        return Principal(name="token-user", role=role)


def load_token_roles_from_env() -> Dict[str, Role]:
    mapping = {}
    raw = os.getenv("WAVEOS_AUTH_TOKENS", "")
    # Format: token1=admin,token2=operator
    for pair in [p.strip() for p in raw.split(",") if p.strip()]:
        if "=" not in pair:
            continue
        token, role = pair.split("=", 1)
        try:
            mapping[token.strip()] = Role(role.strip())
        except ValueError:
            continue
    return mapping


def load_token_roles_from_config(token_roles: Dict[str, str]) -> Dict[str, Role]:
    mapping: Dict[str, Role] = {}
    for token, role_name in token_roles.items():
        try:
            mapping[token] = Role(role_name)
        except ValueError:
            continue
    return mapping
