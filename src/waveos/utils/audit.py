from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


def _rotate(path: Path, max_bytes: int, max_files: int) -> None:
    if not path.exists() or path.stat().st_size < max_bytes:
        return
    for idx in range(max_files - 1, 0, -1):
        src = Path(f"{path}.{idx}")
        dst = Path(f"{path}.{idx + 1}")
        if src.exists():
            src.replace(dst)
    path.replace(f"{path}.1")


def append_audit(path: Path, payload: Dict[str, Any], max_bytes: int = 5_000_000, max_files: int = 5) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _rotate(path, max_bytes=max_bytes, max_files=max_files)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, default=str))
        handle.write("\n")
