"""License check for production. Enforced unless WAVEOS_LICENSE_SKIP=1 or valid key present."""

from __future__ import annotations

import os
import re

# Accept keys that look like WAVEOS-<id>-<date> or WAVEOS-CI-* for CI/test
LICENSE_PATTERN = re.compile(r"^WAVEOS-[A-Z0-9-]+-[A-Z0-9]+$", re.IGNORECASE)


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


def require_license() -> None:
    """Validate that a license is present. Raises LicenseError if not.
    Set WAVEOS_LICENSE_KEY to a valid key, or WAVEOS_LICENSE_PATH to a file containing one.
    Set WAVEOS_LICENSE_SKIP=1 to bypass (dev/local only).
    """
    if os.getenv("WAVEOS_LICENSE_SKIP", "").strip() == "1":
        return

    key = (os.getenv("WAVEOS_LICENSE_KEY") or "").strip()
    if not key and os.getenv("WAVEOS_LICENSE_PATH"):
        key = (_read_license_from_path(os.environ["WAVEOS_LICENSE_PATH"]) or "").strip()

    if key and LICENSE_PATTERN.match(key):
        return

    raise LicenseError(
        "Valid Wave OS license required. Set WAVEOS_LICENSE_KEY or WAVEOS_LICENSE_PATH. "
        "See docs for licensing. (Use WAVEOS_LICENSE_SKIP=1 only for local development.)"
    )
