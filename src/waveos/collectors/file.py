from __future__ import annotations

from pathlib import Path
from typing import Any, List

from waveos.utils import CircuitBreaker, read_csv, read_json, read_jsonl, retry


_breakers: dict[str, CircuitBreaker] = {}


def load_records(path: Path) -> List[Any]:
    breaker = _breakers.setdefault(str(path), CircuitBreaker())
    def _load() -> List[Any]:
        if path.suffix == ".json":
            payload = read_json(path)
            if isinstance(payload, list):
                return payload
            return payload.get("records", [])
        if path.suffix == ".jsonl":
            return read_jsonl(path)
        if path.suffix == ".csv":
            return read_csv(path)
        raise ValueError(f"Unsupported file type: {path}")

    if not breaker.allow():
        raise RuntimeError("Circuit breaker open for file collector")
    try:
        result = retry(_load)
        breaker.record_success()
        return result
    except Exception:
        breaker.record_failure()
        raise
