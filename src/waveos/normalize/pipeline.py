from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Iterable, List

from pydantic import ValidationError

from waveos.models import TelemetrySample
from waveos.utils import counters, get_logger, histograms, parse_timestamp, span, utc_now

logger = get_logger("waveos.normalize")


def normalize_record(record: Dict[str, Any]) -> TelemetrySample:
    payload = dict(record)
    schema_version = int(payload.get("schema_version", 1))
    if schema_version < 1:
        payload = _migrate_telemetry(payload, schema_version)
    timestamp = payload.get("timestamp") or payload.get("ts")
    if isinstance(timestamp, str):
        payload["timestamp"] = parse_timestamp(timestamp)
    elif isinstance(timestamp, datetime):
        payload["timestamp"] = timestamp
    else:
        payload["timestamp"] = utc_now()
    if "link_id" not in payload and "link" in payload:
        payload["link_id"] = payload["link"]
    if "port_id" not in payload and "port" in payload:
        payload["port_id"] = payload["port"]
    try:
        return TelemetrySample(**payload)
    except ValidationError as exc:
        logger.warning("Invalid telemetry record: %s", exc)
        raise


def normalize_records(records: Iterable[Dict[str, Any]], run_id: str | None = None) -> List[TelemetrySample]:
    normalized: List[TelemetrySample] = []
    records_list = list(records)
    metrics_counters = counters()
    duration = histograms()["normalize_duration"]
    with duration.time(), span("normalize_records") as active_span:
        if run_id:
            active_span.set_attribute("waveos.run_id", run_id)
        active_span.set_attribute("waveos.sample_count", len(records_list))
        for record in records_list:
            try:
                normalized.append(normalize_record(record))
                metrics_counters["telemetry_ingested"].inc()
            except ValidationError:
                metrics_counters["normalize_errors"].inc()
                continue
    return normalized


def _migrate_telemetry(payload: Dict[str, Any], schema_version: int) -> Dict[str, Any]:
    migrated = dict(payload)
    if schema_version == 0:
        if "temp_c" in migrated and "temperature_c" not in migrated:
            migrated["temperature_c"] = migrated.pop("temp_c")
        if "tx_power" in migrated and "tx_power_dbm" not in migrated:
            migrated["tx_power_dbm"] = migrated.pop("tx_power")
        if "rx_power" in migrated and "rx_power_dbm" not in migrated:
            migrated["rx_power_dbm"] = migrated.pop("rx_power")
        if "power_w" in migrated and "power_kw" not in migrated:
            migrated["power_kw"] = migrated.pop("power_w") / 1000.0
        if "energy_wh" in migrated and "energy_kwh" not in migrated:
            migrated["energy_kwh"] = migrated.pop("energy_wh") / 1000.0
    migrated["schema_version"] = 1
    return migrated
