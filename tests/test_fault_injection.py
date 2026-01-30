from waveos.normalize import normalize_records


def test_fault_injection_invalid_record() -> None:
    records = [
        {"link_id": "link-1", "errors": 1, "drops": 0},
        {"link_id": "link-2", "errors": -5, "drops": 0},
    ]
    normalized = normalize_records(records)
    assert len(normalized) == 1
