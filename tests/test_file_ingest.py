from pathlib import Path

from waveos.collectors import load_records
from waveos.normalize import normalize_records
from waveos.utils import write_jsonl, write_json


def test_load_records_jsonl_and_normalize(tmp_path: Path) -> None:
    records = [
        {"timestamp": "2025-01-01T00:00:00Z", "link_id": "link-1", "errors": 1},
        {"timestamp": "2025-01-01T00:00:01Z", "link_id": "link-1", "errors": 2},
    ]
    path = tmp_path / "telemetry.jsonl"
    write_jsonl(path, records)
    loaded = load_records(path)
    samples = normalize_records(loaded)
    assert len(samples) == 2
    assert samples[0].link_id == "link-1"


def test_load_records_json_array(tmp_path: Path) -> None:
    records = [
        {"timestamp": "2025-01-01T00:00:00Z", "link_id": "link-2", "errors": 3}
    ]
    path = tmp_path / "telemetry.json"
    write_json(path, records)
    loaded = load_records(path)
    assert loaded[0]["link_id"] == "link-2"
