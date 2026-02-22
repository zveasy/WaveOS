"""
Schema registry and version negotiation for telemetry (Data plane Phase 2).
Validates raw records against a declared schema version before normalization.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from waveos.utils import get_logger

logger = get_logger("waveos.schema_registry")

# Supported telemetry schema versions: required fields (at least one per record).
TELEMETRY_SCHEMA_VERSIONS: Dict[str, List[str]] = {
    "1": ["timestamp", "ts", "link_id", "port_id"],
    "0": ["timestamp", "ts", "link_id", "link"],
}


def get_supported_versions() -> List[str]:
    """Return list of supported schema version identifiers."""
    return list(TELEMETRY_SCHEMA_VERSIONS.keys())


def validate_telemetry_schema(
    records: List[Dict[str, Any]],
    version: str = "1",
) -> Tuple[bool, List[str]]:
    """
    Validate that each record has at least one required field set for the schema version.
    Returns (ok, list of error messages). Empty records pass.
    """
    if version not in TELEMETRY_SCHEMA_VERSIONS:
        return False, [f"Unsupported schema version: {version}"]
    required_any = TELEMETRY_SCHEMA_VERSIONS[version]
    errors: List[str] = []
    for i, rec in enumerate(records):
        if not isinstance(rec, dict):
            errors.append(f"record[{i}]: expected object")
            continue
        has_any = any(rec.get(f) is not None or f in rec for f in required_any)
        if not has_any:
            errors.append(f"record[{i}]: missing required field (need one of {required_any})")
    return len(errors) == 0, errors
