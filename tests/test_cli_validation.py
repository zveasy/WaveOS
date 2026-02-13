"""Tests for CLI input validation and exit codes."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest


def _run_waveos(args: list[str], env: dict | None = None) -> subprocess.CompletedProcess:
    repo_root = Path(__file__).resolve().parents[1]
    e = os.environ.copy()
    e.setdefault("WAVEOS_LICENSE_KEY", "WAVEOS-CI-20991231-TEST")
    if env:
        e.update(env)
    return subprocess.run(
        ["waveos", *args],
        cwd=repo_root,
        capture_output=True,
        text=True,
        env=e,
    )


def test_version_exits_zero_and_prints_version() -> None:
    r = _run_waveos(["-V"])
    assert r.returncode == 0
    assert r.stdout and len(r.stdout.strip()) > 0
    assert "0." in r.stdout or "version" in r.stdout.lower()


def test_version_short_flag() -> None:
    r = _run_waveos(["--version"])
    assert r.returncode == 0


def test_report_missing_dir_exits_one() -> None:
    r = _run_waveos(["report", "--in", "/nonexistent/dir"])
    assert r.returncode == 1
    assert "does not exist" in r.stdout or "Missing" in r.stdout


def test_report_missing_files_exits_one(tmp_path: Path) -> None:
    # Empty dir: no health_summary.json, events.jsonl, actions.json
    r = _run_waveos(["report", "--in", str(tmp_path)])
    assert r.returncode == 1
    assert "Missing" in r.stdout or "required" in r.stdout.lower()


def test_run_missing_input_dir_exits_one(tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    baseline = tmp_path / "baseline"
    baseline.mkdir()
    (baseline / "baseline.json").write_text("[]")
    r = _run_waveos(
        [
            "run",
            "--in", str(tmp_path / "nonexistent"),
            "--baseline", str(baseline),
            "--out", str(out),
        ],
    )
    assert r.returncode == 1
    assert "does not exist" in r.stdout


def test_run_missing_baseline_dir_exits_one(tmp_path: Path) -> None:
    in_dir = tmp_path / "run"
    in_dir.mkdir()
    out = tmp_path / "out"
    out.mkdir()
    r = _run_waveos(
        [
            "run",
            "--in", str(in_dir),
            "--baseline", str(tmp_path / "nonexistent_baseline"),
            "--out", str(out),
        ],
    )
    assert r.returncode == 1
    assert "does not exist" in r.stdout or "baseline" in r.stdout.lower()
