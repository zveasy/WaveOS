"""HTTP pull collector: fetch telemetry from a URL (JSON array or JSONL)."""

from __future__ import annotations

import json
from typing import Any, List
from urllib.request import Request, urlopen

from waveos.utils import get_logger

logger = get_logger("waveos.collectors.http")


def load_records_from_url(
    url: str,
    timeout: float = 10.0,
    headers: dict | None = None,
) -> List[Any]:
    """
    Fetch telemetry from a URL. Expects response body as:
    - JSON array of records, or
    - JSON object with key "records" (array), or
    - Newline-delimited JSON (one record per line).
    Returns a list of dicts suitable for normalize_records().
    """
    req = Request(url, headers=headers or {})
    with urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
    if not raw.strip():
        return []
    # Try JSON array or {"records": [...]}
    if raw.strip().startswith("["):
        return json.loads(raw)
    if raw.strip().startswith("{"):
        data = json.loads(raw)
        if isinstance(data, list):
            return data
        if "records" in data:
            return data["records"]
        return [data]
    # JSONL
    records: List[Any] = []
    for line in raw.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            logger.warning("Skipping non-JSON line in HTTP response")
    return records
