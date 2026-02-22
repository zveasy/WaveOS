from __future__ import annotations

import hashlib
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


def _audit_hash(prev_hash: str, payload: Dict[str, Any]) -> str:
    """Compute hash of chain: H(prev_hash + canonical payload)."""
    canonical = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(f"{prev_hash}{canonical}".encode("utf-8")).hexdigest()


def _read_last_audit_hash(path: Path, hash_file: Path) -> str:
    """Return last hash from sidecar file, or empty string."""
    if hash_file.exists():
        try:
            return hash_file.read_text(encoding="utf-8").strip()
        except OSError:
            pass
    return ""


def append_audit(
    path: Path,
    payload: Dict[str, Any],
    max_bytes: int = 5_000_000,
    max_files: int = 5,
    hash_chain: bool = False,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _rotate(path, max_bytes=max_bytes, max_files=max_files)
    if hash_chain:
        hash_file = path.parent / f"{path.name}.last_hash"
        prev_hash = _read_last_audit_hash(path, hash_file)
        line_hash = _audit_hash(prev_hash, payload)
        record = {"prev_hash": prev_hash, "hash": line_hash, "payload": payload}
        line = json.dumps(record, default=str) + "\n"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line)
        hash_file.write_text(line_hash, encoding="utf-8")
    else:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, default=str))
            handle.write("\n")
