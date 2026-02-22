"""HTTP pull collector: fetch telemetry from a URL (JSON array or JSONL)."""

from __future__ import annotations

import json
from typing import Any, List
from urllib.request import Request, urlopen

from waveos.utils import get_logger

logger = get_logger("waveos.collectors.http")

# Maximum response body size (bytes) to avoid OOM / DoS. Default 50 MB.
DEFAULT_MAX_RESPONSE_BYTES = 50 * 1024 * 1024
_CHUNK_SIZE = 64 * 1024


def load_records_from_url(
    url: str,
    timeout: float = 10.0,
    headers: dict | None = None,
    max_response_bytes: int | None = None,
) -> List[Any]:
    """
    Fetch telemetry from a URL. Expects response body as:
    - JSON array of records, or
    - JSON object with key "records" (array), or
    - Newline-delimited JSON (one record per line).
    Returns a list of dicts suitable for normalize_records().
    Response body is capped at max_response_bytes (default 50 MB) to avoid OOM.
    """
    limit = max_response_bytes if max_response_bytes is not None else DEFAULT_MAX_RESPONSE_BYTES
    req = Request(url, headers=headers or {})
    with urlopen(req, timeout=timeout) as resp:
        chunks: List[bytes] = []
        total = 0
        while True:
            chunk = resp.read(_CHUNK_SIZE)
            if not chunk:
                break
            total += len(chunk)
            if total > limit:
                logger.warning("HTTP response exceeded max size (%s bytes); truncating", limit)
                chunks.append(chunk[: limit - (total - len(chunk))])
                break
            chunks.append(chunk)
        raw = b"".join(chunks).decode("utf-8", errors="replace")
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
