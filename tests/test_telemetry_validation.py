from __future__ import annotations

from pathlib import Path

from waveos.sim import build_demo_dataset
from waveos.validation import validate_file


def test_validate_telemetry_microgrid(tmp_path: Path) -> None:
    _, run_dir = build_demo_dataset(tmp_path / "dataset")
    payload = validate_file(run_dir / "telemetry.jsonl", "microgrid")
    assert payload["invalid_records"] == 0
    assert payload["missing_required"]["power_kw"] == 0
