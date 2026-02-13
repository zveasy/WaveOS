"""V3: Load policy rules from template files (e.g. NERC, DoD)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from waveos.utils import get_logger

logger = get_logger("waveos.policy.templates")


def load_policy_templates(path: Path) -> List[Dict[str, Any]]:
    """Load policy rules from a JSON template file (e.g. docs/templates/policy/nerc.json)."""
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "rules" in data:
            return data["rules"]
        return []
    except Exception as exc:
        logger.warning("Failed to load policy templates from %s: %s", path, type(exc).__name__)
        return []
