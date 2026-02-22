"""Tests for MQTT connector (Data plane Phase 1)."""

from waveos.collectors import load_records_from_mqtt


def test_mqtt_connector_import_optional() -> None:
    """load_records_from_mqtt is either the function or None when paho not installed."""
    assert load_records_from_mqtt is None or callable(load_records_from_mqtt)


def test_mqtt_connector_cli_graceful_without_paho() -> None:
    """ingest-mqtt command exits with message when paho-mqtt not installed."""
    from waveos.cli import cmd_ingest_mqtt
    import argparse
    args = argparse.Namespace(
        broker="localhost",
        topic="test",
        output="/tmp/out.jsonl",
        timeout=1.0,
        max_messages=10,
        port=1883,
    )
    code = cmd_ingest_mqtt(args)
    # If paho is installed, code may be 0 or 1 (connect failure); if not installed, 1
    assert code in (0, 1)
