"""License check for production. Enforced unless WAVEOS_LICENSE_SKIP=1 or valid key present."""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Optional

# Accept keys that look like WAVEOS-<id>-<suffix> or WAVEOS-CI-* for CI/test.
# Suffix can be a date YYYYMMDD (expiry) or other id.
LICENSE_PATTERN = re.compile(r"^WAVEOS-[A-Z0-9-]+-[A-Z0-9]+$", re.IGNORECASE)
# Last segment of key may be YYYYMMDD for expiry
# Tier in key: WAVEOS-ENTERPRISE-*, WAVEOS-DOD-*, WAVEOS-STANDARD-*
TIER_PATTERN = re.compile(r"^WAVEOS-(STANDARD|ENTERPRISE|DOD|CI)-", re.IGNORECASE)


class LicenseError(RuntimeError):
    """Raised when license is missing or invalid."""

    pass


def _read_license_from_path(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8") as f:
            raw = (f.read() or "").strip()
        return raw if raw else None
    except OSError:
        return None


def _parse_expiry(key: str) -> Optional[datetime]:
    """Parse expiry date from key suffix (last segment YYYYMMDD). Returns None if not present."""
    parts = key.split("-")
    if len(parts) < 2:
        return None
    suffix = parts[-1]
    if len(suffix) == 8 and suffix.isdigit():
        try:
            return datetime.strptime(suffix, "%Y%m%d").replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def _is_expired(key: str, now: Optional[datetime] = None) -> bool:
    """True if key has an expiry date that has passed."""
    expiry = _parse_expiry(key)
    if expiry is None:
        return False
    return (now or datetime.now(timezone.utc)) >= expiry


def get_license_tier(key: Optional[str] = None) -> str:
    """Return license tier: standard, enterprise, dod, or evaluation (default)."""
    if not key:
        key = (os.getenv("WAVEOS_LICENSE_KEY") or "").strip()
        if not key and os.getenv("WAVEOS_LICENSE_PATH"):
            key = (_read_license_from_path(os.environ["WAVEOS_LICENSE_PATH"]) or "").strip()
    if not key:
        return "evaluation"
    m = TIER_PATTERN.match(key)
    if m:
        return m.group(1).lower()
    return "standard"


def require_license() -> None:
    """Validate that a license is present and not expired. Raises LicenseError if not.
    Set WAVEOS_LICENSE_KEY or WAVEOS_LICENSE_PATH. Set WAVEOS_LICENSE_SKIP=1 for dev only.
    """
    if os.getenv("WAVEOS_LICENSE_SKIP", "").strip() == "1":
        return

    key = (os.getenv("WAVEOS_LICENSE_KEY") or "").strip()
    if not key and os.getenv("WAVEOS_LICENSE_PATH"):
        key = (_read_license_from_path(os.environ["WAVEOS_LICENSE_PATH"]) or "").strip()

    if not key or not LICENSE_PATTERN.match(key):
        raise LicenseError(
            "Valid Wave OS license required. Set WAVEOS_LICENSE_KEY or WAVEOS_LICENSE_PATH. "
            "See docs for licensing. (Use WAVEOS_LICENSE_SKIP=1 only for local development.)"
        )

    if _is_expired(key):
        raise LicenseError("Wave OS license has expired. Contact licensing@omniandluci.com.")
