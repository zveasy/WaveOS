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
    alert_min_level: Literal["INFO", "WARN", "ERROR"] = "WARN"
    alert_webhook_min_level: Optional[Literal["INFO", "WARN", "ERROR"]] = None
    alert_slack_min_level: Optional[Literal["INFO", "WARN", "ERROR"]] = None
    alert_email_min_level: Optional[Literal["INFO", "WARN", "ERROR"]] = None
    alert_email_provider: Literal["smtp", "ses"] = "smtp"
    alert_email_smtp_host: Optional[str] = None
    alert_email_smtp_port: Optional[int] = 587
    alert_email_smtp_user: Optional[str] = None
    alert_email_smtp_password_secret: Optional[str] = None
    alert_email_ses_region: Optional[str] = None
    waveos_version: Optional[str] = None
    policy_version: Optional[str] = None
    bundle_id: Optional[str] = None
    bundle_dir: Optional[str] = None
    bundle_active_dir: str = "out/bundles/active"
    bundle_history_dir: str = "out/bundles/history"
    bundle_state_dir: str = "out/bundles/state"
    bundle_hmac_key_secret: Optional[str] = None
    evidence_pack_enabled: bool = True
    enforce_actions: bool = False
    recovery_enabled: bool = False
    recovery_restart_command: Optional[str] = None
    recovery_degrade_command: Optional[str] = None
    recovery_reboot_command: Optional[str] = None
    watchdog_enabled: bool = False
    watchdog_path: Optional[str] = "out/watchdog.txt"
    schedule_interval_seconds: Optional[int] = None
    log_spool_path: Optional[str] = "out/spool.log"
    proxy_enabled: bool = False
    proxy_mode: Optional[str] = None
    proxy_listen_host: str = "127.0.0.1"
    proxy_listen_port: Optional[int] = None
    proxy_target_host: Optional[str] = None
    proxy_target_port: Optional[int] = None
    drop_privileges_user: Optional[str] = None
    drop_privileges_group: Optional[str] = None
    feature_flags: Dict[str, bool] = Field(default_factory=dict)
    auth_tokens: Dict[str, str] = Field(default_factory=dict)
    policy_rules: list[Dict[str, Any]] = Field(default_factory=list)
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
    collector_threads: int = 1
    max_memory_mb: Optional[int] = None
    max_cpu_seconds: Optional[int] = None
    idempotent_outputs: bool = True
    retention_days: Optional[int] = None


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
        "alert_min_level": os.getenv("WAVEOS_ALERT_MIN_LEVEL"),
        "alert_webhook_min_level": os.getenv("WAVEOS_ALERT_WEBHOOK_MIN_LEVEL"),
        "alert_slack_min_level": os.getenv("WAVEOS_ALERT_SLACK_MIN_LEVEL"),
        "alert_email_min_level": os.getenv("WAVEOS_ALERT_EMAIL_MIN_LEVEL"),
        "alert_email_smtp_host": os.getenv("WAVEOS_ALERT_EMAIL_SMTP_HOST"),
        "alert_email_smtp_port": os.getenv("WAVEOS_ALERT_EMAIL_SMTP_PORT"),
        "alert_email_smtp_user": os.getenv("WAVEOS_ALERT_EMAIL_SMTP_USER"),
        "alert_email_smtp_password_secret": os.getenv("WAVEOS_ALERT_EMAIL_SMTP_PASSWORD_SECRET"),
        "alert_email_ses_region": os.getenv("WAVEOS_ALERT_EMAIL_SES_REGION"),
        "waveos_version": os.getenv("WAVEOS_VERSION"),
        "policy_version": os.getenv("WAVEOS_POLICY_VERSION"),
        "bundle_id": os.getenv("WAVEOS_BUNDLE_ID"),
        "bundle_dir": os.getenv("WAVEOS_BUNDLE_DIR"),
        "bundle_active_dir": os.getenv("WAVEOS_BUNDLE_ACTIVE_DIR"),
        "bundle_history_dir": os.getenv("WAVEOS_BUNDLE_HISTORY_DIR"),
        "bundle_state_dir": os.getenv("WAVEOS_BUNDLE_STATE_DIR"),
        "bundle_hmac_key_secret": os.getenv("WAVEOS_BUNDLE_HMAC_KEY_SECRET"),
        "evidence_pack_enabled": os.getenv("WAVEOS_EVIDENCE_PACK_ENABLED"),
        "enforce_actions": os.getenv("WAVEOS_ENFORCE_ACTIONS"),
        "recovery_enabled": os.getenv("WAVEOS_RECOVERY_ENABLED"),
        "recovery_restart_command": os.getenv("WAVEOS_RECOVERY_RESTART_COMMAND"),
        "recovery_degrade_command": os.getenv("WAVEOS_RECOVERY_DEGRADE_COMMAND"),
        "recovery_reboot_command": os.getenv("WAVEOS_RECOVERY_REBOOT_COMMAND"),
        "watchdog_enabled": os.getenv("WAVEOS_WATCHDOG_ENABLED"),
        "watchdog_path": os.getenv("WAVEOS_WATCHDOG_PATH"),
        "schedule_interval_seconds": os.getenv("WAVEOS_SCHEDULE_INTERVAL_SECONDS"),
        "log_spool_path": os.getenv("WAVEOS_LOG_SPOOL_PATH"),
        "proxy_enabled": os.getenv("WAVEOS_PROXY_ENABLED"),
        "proxy_mode": os.getenv("WAVEOS_PROXY_MODE"),
        "proxy_listen_host": os.getenv("WAVEOS_PROXY_LISTEN_HOST"),
        "proxy_listen_port": os.getenv("WAVEOS_PROXY_LISTEN_PORT"),
        "proxy_target_host": os.getenv("WAVEOS_PROXY_TARGET_HOST"),
        "proxy_target_port": os.getenv("WAVEOS_PROXY_TARGET_PORT"),
        "drop_privileges_user": os.getenv("WAVEOS_DROP_PRIVILEGES_USER"),
        "drop_privileges_group": os.getenv("WAVEOS_DROP_PRIVILEGES_GROUP"),
        "secrets_provider": os.getenv("WAVEOS_SECRETS_PROVIDER"),
        "audit_log_path": os.getenv("WAVEOS_AUDIT_LOG_PATH"),
        "audit_enabled": os.getenv("WAVEOS_AUDIT_ENABLED"),
        "audit_max_bytes": os.getenv("WAVEOS_AUDIT_LOG_MAX_BYTES"),
        "audit_max_files": os.getenv("WAVEOS_AUDIT_LOG_MAX_FILES"),
        "collector_threads": os.getenv("WAVEOS_COLLECTOR_THREADS"),
        "max_memory_mb": os.getenv("WAVEOS_MAX_MEMORY_MB"),
        "max_cpu_seconds": os.getenv("WAVEOS_MAX_CPU_SECONDS"),
        "idempotent_outputs": os.getenv("WAVEOS_IDEMPOTENT_OUTPUTS"),
        "retention_days": os.getenv("WAVEOS_RETENTION_DAYS"),
    }
    env = {key: value for key, value in env.items() if value is not None}
    if "metrics_port" in env:
        try:
            env["metrics_port"] = int(env["metrics_port"])
        except ValueError as exc:
            raise ValueError("metrics_port must be an integer") from exc
    for key in (
        "alert_min_level",
        "alert_webhook_min_level",
        "alert_slack_min_level",
        "alert_email_min_level",
    ):
        if key in env and env[key] is not None:
            env[key] = str(env[key]).upper()
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
    if "evidence_pack_enabled" in env and env["evidence_pack_enabled"] is not None:
        env["evidence_pack_enabled"] = str(env["evidence_pack_enabled"]).lower() in {"1", "true", "yes", "on"}
    if "enforce_actions" in env and env["enforce_actions"] is not None:
        env["enforce_actions"] = str(env["enforce_actions"]).lower() in {"1", "true", "yes", "on"}
    if "recovery_enabled" in env and env["recovery_enabled"] is not None:
        env["recovery_enabled"] = str(env["recovery_enabled"]).lower() in {"1", "true", "yes", "on"}
    if "watchdog_enabled" in env and env["watchdog_enabled"] is not None:
        env["watchdog_enabled"] = str(env["watchdog_enabled"]).lower() in {"1", "true", "yes", "on"}
    if "proxy_enabled" in env and env["proxy_enabled"] is not None:
        env["proxy_enabled"] = str(env["proxy_enabled"]).lower() in {"1", "true", "yes", "on"}
    if "schedule_interval_seconds" in env and env["schedule_interval_seconds"] is not None:
        try:
            env["schedule_interval_seconds"] = int(env["schedule_interval_seconds"])
        except ValueError as exc:
            raise ValueError("schedule_interval_seconds must be an integer") from exc
    if "proxy_listen_port" in env and env["proxy_listen_port"] is not None:
        try:
            env["proxy_listen_port"] = int(env["proxy_listen_port"])
        except ValueError as exc:
            raise ValueError("proxy_listen_port must be an integer") from exc
    if "proxy_target_port" in env and env["proxy_target_port"] is not None:
        try:
            env["proxy_target_port"] = int(env["proxy_target_port"])
        except ValueError as exc:
            raise ValueError("proxy_target_port must be an integer") from exc
    if "alert_email_smtp_port" in env and env["alert_email_smtp_port"] is not None:
        try:
            env["alert_email_smtp_port"] = int(env["alert_email_smtp_port"])
        except ValueError as exc:
            raise ValueError("alert_email_smtp_port must be an integer") from exc
    for key in ("collector_threads", "max_memory_mb", "max_cpu_seconds", "retention_days"):
        if key in env and env[key] is not None:
            try:
                env[key] = int(env[key])
            except ValueError as exc:
                raise ValueError(f"{key} must be an integer") from exc
    if "idempotent_outputs" in env and env["idempotent_outputs"] is not None:
        env["idempotent_outputs"] = str(env["idempotent_outputs"]).lower() in {"1", "true", "yes", "on"}
    payload.update(env)
    config = WaveOSConfig(**payload)
    if config.schema_version != 1:
        raise ValueError(f"Unsupported config schema_version: {config.schema_version}")
    return config


def config_fingerprint(config: WaveOSConfig) -> str:
    payload = config.model_dump()
    encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
