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
    """Vault integration via hvac."""
    try:
        import hvac
    except Exception:
        return _load_env_json("WAVEOS_VAULT_SECRETS_JSON").get(key)
    addr = os.getenv("WAVEOS_VAULT_ADDR")
    token = os.getenv("WAVEOS_VAULT_TOKEN")
    path = os.getenv("WAVEOS_VAULT_PATH", "secret/data/waveos")
    if not addr or not token:
        return _load_env_json("WAVEOS_VAULT_SECRETS_JSON").get(key)
    client = hvac.Client(url=addr, token=token)
    result = client.secrets.kv.v2.read_secret_version(path=path)
    return result["data"]["data"].get(key)


def get_secret_from_aws(key: str) -> Optional[str]:
    """AWS Secrets Manager integration via boto3."""
    try:
        import boto3
    except Exception:
        return _load_env_json("WAVEOS_AWS_SECRETS_JSON").get(key)
    secret_id = os.getenv("WAVEOS_AWS_SECRET_ID", key)
    region = os.getenv("WAVEOS_AWS_REGION")
    if not region:
        return _load_env_json("WAVEOS_AWS_SECRETS_JSON").get(key)
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
    except Exception:
        return _load_env_json("WAVEOS_GCP_SECRETS_JSON").get(key)
    project = os.getenv("WAVEOS_GCP_PROJECT")
    if not project:
        return _load_env_json("WAVEOS_GCP_SECRETS_JSON").get(key)
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{project}/secrets/{key}/versions/latest"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("utf-8")
