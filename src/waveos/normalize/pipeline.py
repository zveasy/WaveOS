from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Iterable, List

from pydantic import ValidationError

from waveos.models import TelemetrySample
from waveos.utils import counters, get_logger, histograms, parse_timestamp, span, utc_now

logger = get_logger("waveos.normalize")


def normalize_record(record: Dict[str, Any]) -> TelemetrySample:
    payload = dict(record)
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
