"""WaveOS Bridge — legacy system integration layer."""

from waveos.bridge.orchestrator import BridgeOrchestrator, BridgeMode, BridgeState
from waveos.bridge.patterns import BRIDGE_PATTERNS, get_pattern_description

__all__ = [
    "BridgeOrchestrator",
    "BridgeMode",
    "BridgeState",
    "BRIDGE_PATTERNS",
    "get_pattern_description",
]
