"""Optional ingestion auth: require token for telemetry collection (commercial)."""

from __future__ import annotations

import hmac
from pathlib import Path
from typing import Optional

from waveos.utils import get_logger, get_secret

logger = get_logger("waveos.collectors.auth")


class IngestionAuthError(PermissionError):
    """Raised when ingestion token is required but missing or invalid."""

    pass


def verify_ingestion_token(
    token_path: Optional[Path] = None,
    expected_env: str = "WAVEOS_INGESTION_TOKEN",
) -> None:
    """Require that a token file exists and matches the expected secret. Raises IngestionAuthError if not."""
    expected = get_secret(expected_env)
    if not expected:
        raise IngestionAuthError(
            "Ingestion token required. Set WAVEOS_INGESTION_TOKEN or configure ingestion_token_path."
        )
    path = token_path or Path("out/ingestion.token")
    if not path.is_file():
        raise IngestionAuthError(f"Ingestion token file not found: {path}")
    actual = path.read_text(encoding="utf-8").strip()
    if not hmac.compare_digest(actual, expected):
        raise IngestionAuthError("Ingestion token invalid.")