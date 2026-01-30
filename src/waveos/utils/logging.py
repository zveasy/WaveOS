import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from waveos.utils.spooler import LogSpooler


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        return json.dumps(payload)


class SpoolHandler(logging.Handler):
    def __init__(self, spool_path: Path) -> None:
        super().__init__()
        self.spooler = LogSpooler(spool_path)

    def emit(self, record: logging.LogRecord) -> None:
        msg = self.format(record)
        self.spooler.append(msg)


class RedactFilter(logging.Filter):
    def __init__(self, values: list[str]) -> None:
        super().__init__()
        self.values = [value for value in values if value]

    def filter(self, record: logging.LogRecord) -> bool:
        if not self.values:
            return True
        try:
            message = str(record.getMessage())
        except Exception:
            return True
        for value in self.values:
            if value in message:
                message = message.replace(value, "[REDACTED]")
        record.msg = message
        record.args = ()
        return True


def setup_logging(level: int = logging.INFO, log_format: str | None = None, spool_path: Path | None = None) -> None:
    log_format = (log_format or os.getenv("WAVEOS_LOG_FORMAT", "json")).lower()
    handler = logging.StreamHandler()
    if log_format == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s"))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    redact_values = _default_redact_values()
    if redact_values:
        root.addFilter(RedactFilter(redact_values))
    if spool_path:
        spool_handler = SpoolHandler(spool_path)
        spool_handler.setFormatter(handler.formatter)
        root.addHandler(spool_handler)
    root.setLevel(level)


def _default_redact_values() -> list[str]:
    values: list[str] = []
    for key, value in os.environ.items():
        if not value:
            continue
        key_upper = key.upper()
        if "SECRET" in key_upper or "PASSWORD" in key_upper or "TOKEN" in key_upper:
            values.append(value)
    extra = os.getenv("WAVEOS_REDACT_VALUES")
    if extra:
        values.extend([entry for entry in extra.split(",") if entry])
    return values


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
