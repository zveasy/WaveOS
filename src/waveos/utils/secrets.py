from __future__ import annotations

import json
import os
from typing import Optional

_strict_secrets_override: Optional[bool] = None


def set_strict_secrets(strict: bool | None) -> None:
    """Set strict_secrets from config (Security Phase 2). Overrides WAVEOS_STRICT_SECRETS when set. None clears override."""
    global _strict_secrets_override
    _strict_secrets_override = strict


def _is_production() -> bool:
    """True if running in production (license required). JSON secrets fallback is disabled in production."""
    return os.getenv("WAVEOS_LICENSE_SKIP", "").strip() != "1"


def _strict_secrets() -> bool:
    """When True, no env fallback for secrets (Security Phase 2). Set via config or WAVEOS_STRICT_SECRETS=1."""
    if _strict_secrets_override is not None:
        return _strict_secrets_override
    v = os.getenv("WAVEOS_STRICT_SECRETS", "").strip().lower()
    return v in ("1", "true", "yes", "on")


def _json_fallback_allowed() -> bool:
    """In production or when strict_secrets, do not fall back to WAVEOS_*_SECRETS_JSON."""
    return not _is_production() and not _strict_secrets()


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
    """Vault integration via hvac."""
    try:
        import hvac
    except ImportError:
        if _json_fallback_allowed():
            return _load_env_json("WAVEOS_VAULT_SECRETS_JSON").get(key)
        return None
    addr = os.getenv("WAVEOS_VAULT_ADDR")
    token = os.getenv("WAVEOS_VAULT_TOKEN")
    path = os.getenv("WAVEOS_VAULT_PATH", "secret/data/waveos")
    if not addr or not token:
        if _json_fallback_allowed():
            return _load_env_json("WAVEOS_VAULT_SECRETS_JSON").get(key)
        return None
    client = hvac.Client(url=addr, token=token)
    result = client.secrets.kv.v2.read_secret_version(path=path)
    return result["data"]["data"].get(key)


def get_secret_from_aws(key: str) -> Optional[str]:
    """AWS Secrets Manager integration via boto3."""
    try:
        import boto3
    except ImportError:
        if _json_fallback_allowed():
            return _load_env_json("WAVEOS_AWS_SECRETS_JSON").get(key)
        return None
    secret_id = os.getenv("WAVEOS_AWS_SECRET_ID", key)
    region = os.getenv("WAVEOS_AWS_REGION")
    if not region:
        if _json_fallback_allowed():
            return _load_env_json("WAVEOS_AWS_SECRETS_JSON").get(key)
        return None
    client = boto3.client("secretsmanager", region_name=region)
    response = client.get_secret_value(SecretId=secret_id)
    secret_string = response.get("SecretString")
    if secret_string:
        try:
            payload = json.loads(secret_string)
            return payload.get(key) or payload.get("value")
        except json.JSONDecodeError:
            return secret_string
    return None


def get_secret_from_gcp(key: str) -> Optional[str]:
    """GCP Secret Manager integration via google-cloud-secret-manager."""
    try:
        from google.cloud import secretmanager
    except ImportError:
        if _json_fallback_allowed():
            return _load_env_json("WAVEOS_GCP_SECRETS_JSON").get(key)
        return None
    project = os.getenv("WAVEOS_GCP_PROJECT")
    if not project:
        if _json_fallback_allowed():
            return _load_env_json("WAVEOS_GCP_SECRETS_JSON").get(key)
        return None
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{project}/secrets/{key}/versions/latest"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("utf-8")
