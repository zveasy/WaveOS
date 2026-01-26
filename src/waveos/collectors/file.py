from __future__ import annotations

from pathlib import Path
from typing import Any, List

from waveos.utils import read_csv, read_json, read_jsonl, retry


def load_records(path: Path) -> List[Any]:
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

    return retry(_load)
