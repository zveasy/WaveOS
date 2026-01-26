from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Iterable, List

from pydantic import ValidationError

from waveos.models import TelemetrySample
from waveos.utils import get_logger, parse_timestamp, utc_now

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


def normalize_records(records: Iterable[Dict[str, Any]]) -> List[TelemetrySample]:
    normalized: List[TelemetrySample] = []
    for record in records:
        try:
            normalized.append(normalize_record(record))
        except ValidationError:
            continue
    return normalized
