from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any, Dict, Optional, Literal

from pydantic import BaseModel, Field
import hashlib
import json


class WaveOSConfig(BaseModel):
    schema_version: int = 1
    log_format: Literal["json", "text"] = Field(default="json")
    log_level: str = Field(default="INFO")
    metrics_port: Optional[int] = None
    otel_endpoint: Optional[str] = None
    alert_webhook_url: Optional[str] = None
    alert_slack_webhook_url: Optional[str] = None
    alert_email_to: Optional[str] = None
    alert_email_from: Optional[str] = None
    alert_email_provider: Literal["smtp", "ses"] = "smtp"
    alert_email_smtp_host: Optional[str] = None
    alert_email_smtp_port: Optional[int] = 587
    alert_email_smtp_user: Optional[str] = None
    alert_email_smtp_password_secret: Optional[str] = None
    alert_email_ses_region: Optional[str] = None
    feature_flags: Dict[str, bool] = Field(default_factory=dict)
    auth_tokens: Dict[str, str] = Field(default_factory=dict)
    secrets_provider: Literal["env", "vault", "aws", "gcp"] = "env"
    audit_log_path: Optional[str] = "out/audit.jsonl"
    audit_enabled: bool = True
    audit_max_bytes: int = 5_000_000
    audit_max_files: int = 5
    retry_count: int = 3
    retry_base_delay: float = 0.2
    retry_max_delay: float = 2.0
    breaker_max_failures: int = 3
    breaker_reset_after: float = 5.0


def _load_file(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    if path.suffix in {".toml", ".tml"}:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    if path.suffix == ".json":
        import json

        return json.loads(path.read_text(encoding="utf-8"))
    raise ValueError(f"Unsupported config format: {path.suffix}")


def load_config(path: Optional[Path] = None) -> WaveOSConfig:
    config_path = path or (Path(os.getenv("WAVEOS_CONFIG")) if os.getenv("WAVEOS_CONFIG") else None)
    payload: Dict[str, Any] = {}
    if config_path:
        payload.update(_load_file(config_path))

    env = {
        "log_format": os.getenv("WAVEOS_LOG_FORMAT"),
        "log_level": os.getenv("WAVEOS_LOG_LEVEL"),
        "metrics_port": os.getenv("WAVEOS_METRICS_PORT"),
        "otel_endpoint": os.getenv("WAVEOS_OTEL_ENDPOINT"),
        "alert_webhook_url": os.getenv("WAVEOS_ALERT_WEBHOOK_URL"),
        "alert_slack_webhook_url": os.getenv("WAVEOS_ALERT_SLACK_WEBHOOK_URL"),
        "alert_email_to": os.getenv("WAVEOS_ALERT_EMAIL_TO"),
        "alert_email_from": os.getenv("WAVEOS_ALERT_EMAIL_FROM"),
        "alert_email_provider": os.getenv("WAVEOS_ALERT_EMAIL_PROVIDER"),
        "alert_email_smtp_host": os.getenv("WAVEOS_ALERT_EMAIL_SMTP_HOST"),
        "alert_email_smtp_port": os.getenv("WAVEOS_ALERT_EMAIL_SMTP_PORT"),
        "alert_email_smtp_user": os.getenv("WAVEOS_ALERT_EMAIL_SMTP_USER"),
        "alert_email_smtp_password_secret": os.getenv("WAVEOS_ALERT_EMAIL_SMTP_PASSWORD_SECRET"),
        "alert_email_ses_region": os.getenv("WAVEOS_ALERT_EMAIL_SES_REGION"),
        "secrets_provider": os.getenv("WAVEOS_SECRETS_PROVIDER"),
        "audit_log_path": os.getenv("WAVEOS_AUDIT_LOG_PATH"),
        "audit_enabled": os.getenv("WAVEOS_AUDIT_ENABLED"),
        "audit_max_bytes": os.getenv("WAVEOS_AUDIT_LOG_MAX_BYTES"),
        "audit_max_files": os.getenv("WAVEOS_AUDIT_LOG_MAX_FILES"),
    }
    env = {key: value for key, value in env.items() if value is not None}
    if "metrics_port" in env:
        try:
            env["metrics_port"] = int(env["metrics_port"])
        except ValueError as exc:
            raise ValueError("metrics_port must be an integer") from exc
    if "audit_max_bytes" in env and env["audit_max_bytes"] is not None:
        try:
            env["audit_max_bytes"] = int(env["audit_max_bytes"])
        except ValueError as exc:
            raise ValueError("audit_max_bytes must be an integer") from exc
    if "audit_max_files" in env and env["audit_max_files"] is not None:
        try:
            env["audit_max_files"] = int(env["audit_max_files"])
        except ValueError as exc:
            raise ValueError("audit_max_files must be an integer") from exc
    if "audit_enabled" in env and env["audit_enabled"] is not None:
        env["audit_enabled"] = str(env["audit_enabled"]).lower() in {"1", "true", "yes", "on"}
    if "alert_email_smtp_port" in env and env["alert_email_smtp_port"] is not None:
        try:
            env["alert_email_smtp_port"] = int(env["alert_email_smtp_port"])
        except ValueError as exc:
            raise ValueError("alert_email_smtp_port must be an integer") from exc
    payload.update(env)
    config = WaveOSConfig(**payload)
    if config.schema_version != 1:
        raise ValueError(f"Unsupported config schema_version: {config.schema_version}")
    return config


def config_fingerprint(config: WaveOSConfig) -> str:
    payload = config.model_dump()
    encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
