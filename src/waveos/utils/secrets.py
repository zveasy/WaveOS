from __future__ import annotations

import os
from typing import Optional
import json


def _load_env_json(var_name: str) -> dict:
    raw = os.getenv(var_name, "")
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def get_secret(key: str, provider: str = "env") -> Optional[str]:
    """Resolve secrets from env or provider-specific JSON maps."""
    if provider == "env":
        return os.getenv(key)
    if provider == "vault":
        return get_secret_from_vault(key)
    if provider == "aws":
        return get_secret_from_aws(key)
    if provider == "gcp":
        return get_secret_from_gcp(key)
    return None


def get_secret_from_vault(key: str) -> Optional[str]:
    """Vault integration placeholder."""
    return _load_env_json("WAVEOS_VAULT_SECRETS_JSON").get(key)


def get_secret_from_aws(key: str) -> Optional[str]:
    """AWS Secrets Manager integration placeholder."""
    return _load_env_json("WAVEOS_AWS_SECRETS_JSON").get(key)


def get_secret_from_gcp(key: str) -> Optional[str]:
    """GCP Secret Manager integration placeholder."""
    return _load_env_json("WAVEOS_GCP_SECRETS_JSON").get(key)
