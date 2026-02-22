"""Tests for schema registry (Data plane Phase 2)."""

from waveos.schema_registry import (
    get_supported_versions,
    validate_telemetry_schema,
)


def test_get_supported_versions() -> None:
    versions = get_supported_versions()
    assert "1" in versions
    assert "0" in versions


def test_validate_telemetry_schema_valid() -> None:
    records = [
        {"timestamp": "2025-01-01T00:00:00Z", "link_id": "L1"},
        {"link_id": "L2", "temperature_c": 25},
    ]
    ok, errors = validate_telemetry_schema(records, version="1")
    assert ok
    assert not errors


def test_validate_telemetry_schema_invalid() -> None:
    records = [{"unknown_only": 1}]
    ok, errors = validate_telemetry_schema(records, version="1")
    assert not ok
    assert len(errors) >= 1
    assert "required" in errors[0].lower() or "missing" in errors[0].lower()


def test_validate_telemetry_schema_unsupported_version() -> None:
    ok, errors = validate_telemetry_schema([{"timestamp": "now"}], version="99")
    assert not ok
    assert any("99" in e or "Unsupported" in e for e in errors)
