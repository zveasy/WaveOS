"""V3: Shadow mode — run pipeline without actuation, return diff for what-if."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from waveos.utils import get_logger

logger = get_logger("waveos.shadow")


@dataclass
class ShadowResult:
    """Result of a shadow run: recommended actions and diff vs live (no actuation)."""
    run_id: str
    shadow: bool = True
    actions_count: int = 0
    scores_count: int = 0
    events_count: int = 0
    diff_vs_live: Dict[str, Any] = field(default_factory=dict)
    meta: Dict[str, Any] = field(default_factory=dict)


def run_shadow(
    run_id: str,
    scores: List[Any],
    events: List[Any],
    actions: List[Any],
    live_run_meta: Optional[Dict[str, Any]] = None,
) -> ShadowResult:
    """Build shadow result (no actuation). If live_run_meta provided, compute simple diff."""
    diff: Dict[str, Any] = {}
    if live_run_meta:
        diff["action_count_delta"] = len(actions) - live_run_meta.get("action_count", 0)
        diff["event_count_delta"] = len(events) - live_run_meta.get("event_count", 0)
    return ShadowResult(
        run_id=run_id,
        shadow=True,
        actions_count=len(actions),
        scores_count=len(scores),
        events_count=len(events),
        diff_vs_live=diff,
        meta={"mode": "shadow"},
    )
