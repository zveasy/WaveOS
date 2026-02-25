"""Data diode / one-way sync — bundles flow one direction only."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.transfer.diode")


@dataclass
class DiodeSyncResult:
    direction: str = "outside_to_inside"
    synced: List[str] = field(default_factory=list)
    blocked: List[str] = field(default_factory=list)
    timestamp: str = ""

    def to_dict(self) -> dict:
        return {
            "direction": self.direction,
            "synced": self.synced,
            "blocked": self.blocked,
            "timestamp": self.timestamp or utc_now().isoformat(),
        }


class DiodeSync:
    """One-way sync simulating data diode constraints.
    
    Only metadata and bundles flow from outside → inside.
    No data flows from inside → outside (enforced in code).
    """

    def __init__(self, outside_registry: Path, inside_registry: Path) -> None:
        self.outside = outside_registry
        self.inside = inside_registry
        self._allow_reverse = False

    def sync_inbound(
        self,
        channel: Optional[str] = None,
        hmac_key: Optional[str] = None,
    ) -> DiodeSyncResult:
        """Sync bundles from outside to inside (permitted direction)."""
        from waveos.registry.mirror import RegistryMirror
        mirror = RegistryMirror(self.outside, self.inside)
        result = mirror.sync(channel=channel, hmac_key=hmac_key)
        return DiodeSyncResult(
            direction="outside_to_inside",
            synced=result.synced,
            blocked=result.failed,
            timestamp=utc_now().isoformat(),
        )

    def sync_outbound(self) -> DiodeSyncResult:
        """Attempt outbound sync (blocked by diode — always returns empty)."""
        logger.warning("Outbound sync blocked by data diode policy")
        return DiodeSyncResult(
            direction="inside_to_outside_BLOCKED",
            synced=[],
            blocked=["ALL — diode policy enforced"],
            timestamp=utc_now().isoformat(),
        )

    def verify_one_way_constraint(self) -> Dict[str, Any]:
        """Verify that diode constraint is enforced."""
        return {
            "allow_inbound": True,
            "allow_outbound": self._allow_reverse,
            "policy": "one_way_outside_to_inside",
            "enforced": not self._allow_reverse,
        }
