"""V2: Device state registry and compatibility matrix — track what runs where."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from waveos.utils import get_logger
from waveos.utils.time import utc_now

logger = get_logger("waveos.state_registry")


def load_compatibility_matrix(path: Optional[Path] = None) -> Dict[str, Any]:
    """Load compatibility matrix (kernel/firmware/software versions). Returns dict with keys like kernel_versions, firmware_versions, waveos_versions."""
    if path is None or not path.is_file():
        return {
            "schema_version": 1,
            "kernel_versions": [],
            "firmware_versions": [],
            "waveos_versions": [],
            "compatible_pairs": [],
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        logger.warning("Failed to load compatibility matrix from %s: %s", path, type(exc).__name__)
        return {}


def save_compatibility_matrix(path: Path, matrix: Dict[str, Any]) -> None:
    """Save compatibility matrix to JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(matrix, indent=2, default=str), encoding="utf-8")


def record_device_state(
    registry_path: Path,
    device_id: str,
    capability: str,
    vendor: str,
    version: str,
    state: Dict[str, Any],
) -> None:
    """Append a device state record to the registry (JSONL)."""
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": utc_now().isoformat(),
        "device_id": device_id,
        "capability": capability,
        "vendor": vendor,
        "version": version,
        "state": state,
    }
    with registry_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")


def read_device_states(registry_path: Path, device_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Read state records from registry (latest per device if device_id given)."""
    if not registry_path.is_file():
        return []
    records: List[Dict[str, Any]] = []
    with registry_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                if device_id is None or rec.get("device_id") == device_id:
                    records.append(rec)
            except json.JSONDecodeError:
                continue
    return records
