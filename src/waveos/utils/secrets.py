from __future__ import annotations

import os
from typing import Optional


def get_secret(key: str) -> Optional[str]:
    """Placeholder secrets resolver (env-only for now)."""
    return os.getenv(key)
