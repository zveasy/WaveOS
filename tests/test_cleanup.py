from __future__ import annotations

import os
import time
from pathlib import Path

from waveos.cli import cmd_cleanup
import argparse


def test_cleanup_removes_old_files(tmp_path: Path) -> None:
    old_file = tmp_path / "old.txt"
    new_file = tmp_path / "new.txt"
    old_file.write_text("old", encoding="utf-8")
    new_file.write_text("new", encoding="utf-8")
    old_mtime = time.time() - (10 * 86400)
    os.utime(old_file, (old_mtime, old_mtime))
    args = argparse.Namespace(path=str(tmp_path), days=5)
    cmd_cleanup(args)
    assert not old_file.exists()
    assert new_file.exists()
