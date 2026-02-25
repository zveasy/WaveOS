"""Bridge deployment patterns documentation and helpers."""

from __future__ import annotations

from typing import Any, Dict, List


BRIDGE_PATTERNS: List[Dict[str, Any]] = [
    {
        "name": "adapter_facade",
        "description": "Adapter process mediates between legacy and new system APIs. Legacy system unchanged.",
        "use_case": "Legacy system has a stable API but uses an incompatible protocol or data format.",
        "manifest_fields": {"bridge.adapter_service": "required", "bridge.legacy_service": "required"},
    },
    {
        "name": "protocol_translation",
        "description": "Translate protocol/file formats between legacy and new systems in real-time.",
        "use_case": "Legacy uses files/proprietary protocol; new system uses REST/gRPC.",
        "manifest_fields": {"bridge.routing_rules.translation_type": "protocol|file|format"},
    },
    {
        "name": "mirror_canary_cutover",
        "description": "Three-phase rollout: mirror all traffic, then canary partial, then full cutover.",
        "use_case": "Zero-downtime migration from legacy to new system with validation at each step.",
        "manifest_fields": {"bridge.mode": "mirror|canary|cutover"},
    },
]


def get_pattern_description(pattern_name: str) -> Dict[str, Any]:
    """Get description of a bridge pattern by name."""
    for p in BRIDGE_PATTERNS:
        if p["name"] == pattern_name:
            return p
    return {"name": pattern_name, "description": "Unknown pattern", "use_case": "", "manifest_fields": {}}


def list_patterns() -> List[str]:
    return [p["name"] for p in BRIDGE_PATTERNS]
