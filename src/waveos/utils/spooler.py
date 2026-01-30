from __future__ import annotations

from pathlib import Path


def _rotate(path: Path, max_bytes: int, max_files: int) -> None:
    if not path.exists() or path.stat().st_size < max_bytes:
        return
    for idx in range(max_files - 1, 0, -1):
        src = Path(f"{path}.{idx}")
        dst = Path(f"{path}.{idx + 1}")
        if src.exists():
            src.replace(dst)
    path.replace(f"{path}.1")


class LogSpooler:
    def __init__(self, path: Path, max_bytes: int = 5_000_000, max_files: int = 5) -> None:
        self.path = path
        self.max_bytes = max_bytes
        self.max_files = max_files

    def append(self, line: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        _rotate(self.path, max_bytes=self.max_bytes, max_files=self.max_files)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(line.rstrip() + "\n")
