from waveos.normalize import normalize_record


def test_normalize_record_parses_timestamp_and_aliases() -> None:
    record = {
        "ts": "2025-01-01T00:00:00Z",
        "link": "link-1",
        "errors": 5,
        "temperature_c": 45.0,
    }
    sample = normalize_record(record)
    assert sample.link_id == "link-1"
    assert sample.timestamp.isoformat().startswith("2025-01-01T00:00:00")
    assert sample.errors == 5
    assert sample.temperature_c == 45.0
