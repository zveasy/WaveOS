from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List

from waveos.models import TelemetrySample
from waveos.utils import read_jsonl, write_json


@dataclass
class ValidationProfile:
    name: str
    required_fields: List[str]


PROFILES = {
    "microgrid": ValidationProfile(
        name="microgrid",
        required_fields=["power_kw", "energy_kwh", "voltage_v", "current_a"],
    ),
    "ev_charger": ValidationProfile(
        name="ev_charger",
        required_fields=["power_kw", "energy_kwh", "voltage_v", "current_a", "battery_soc_pct", "charger_status"],
    ),
}


def validate_records(records: Iterable[Dict[str, Any]], profile: ValidationProfile) -> Dict[str, Any]:
    total = 0
    valid = 0
    errors: List[str] = []
    missing_required = {field: 0 for field in profile.required_fields}
    stats: Dict[str, Dict[str, float]] = {}

    for record in records:
        total += 1
        try:
            sample = TelemetrySample(**record)
        except Exception as exc:
            errors.append(str(exc))
            continue
        valid += 1
        for field in profile.required_fields:
            if getattr(sample, field, None) is None:
                missing_required[field] += 1
        for field in profile.required_fields:
            value = getattr(sample, field, None)
            if value is None:
                continue
            if not isinstance(value, (int, float)):
                continue
            entry = stats.setdefault(field, {"min": float(value), "max": float(value)})
            entry["min"] = min(entry["min"], float(value))
            entry["max"] = max(entry["max"], float(value))

    return {
        "profile": profile.name,
        "total_records": total,
        "valid_records": valid,
        "invalid_records": total - valid,
        "missing_required": missing_required,
        "stats": stats,
        "sample_errors": errors[:5],
    }


def validate_file(path: Path, profile_name: str, out_path: Path | None = None) -> Dict[str, Any]:
    records = read_jsonl(path)
    profile = PROFILES.get(profile_name)
    if not profile:
        raise ValueError(f"Unknown profile: {profile_name}")
    payload = validate_records(records, profile)
    if out_path:
        write_json(out_path, payload)
    return payload
