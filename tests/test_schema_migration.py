from waveos.normalize import normalize_record


def test_schema_migration_v0_fields() -> None:
    record = {
        "schema_version": 0,
        "link_id": "link-1",
        "temp_c": 42.0,
        "tx_power": 1.0,
        "rx_power": -1.0,
    }
    sample = normalize_record(record)
    assert sample.temperature_c == 42.0
    assert sample.tx_power_dbm == 1.0
    assert sample.rx_power_dbm == -1.0
