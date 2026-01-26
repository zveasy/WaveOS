from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any, Dict, Optional, Literal

from pydantic import BaseModel, Field


class WaveOSConfig(BaseModel):
    schema_version: int = 1
    log_format: Literal["json", "text"] = Field(default="json")
    log_level: str = Field(default="INFO")
    metrics_port: Optional[int] = None
    otel_endpoint: Optional[str] = None
    alert_webhook_url: Optional[str] = None
    alert_slack_webhook_url: Optional[str] = None
    alert_email_to: Optional[str] = None
    feature_flags: Dict[str, bool] = Field(default_factory=dict)
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
    }
    env = {key: value for key, value in env.items() if value is not None}
    if "metrics_port" in env:
        try:
            env["metrics_port"] = int(env["metrics_port"])
        except ValueError as exc:
            raise ValueError("metrics_port must be an integer") from exc
    payload.update(env)
    config = WaveOSConfig(**payload)
    if config.schema_version != 1:
        raise ValueError(f"Unsupported config schema_version: {config.schema_version}")
    return config
