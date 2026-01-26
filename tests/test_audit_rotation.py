from pathlib import Path

from waveos.utils import append_audit


def test_audit_rotation(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    for idx in range(10):
        append_audit(path, {"event": idx}, max_bytes=50, max_files=2)
    assert path.exists()
    rotated = Path(f"{path}.1")
    assert rotated.exists()
