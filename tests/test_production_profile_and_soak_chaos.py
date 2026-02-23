"""Test production profile config load, soak runner report output, and chaos runner report output."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from waveos.sim import build_demo_dataset
from waveos.utils.config import load_config


def test_production_toml_loads_with_expected_values() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    config_path = repo_root / "configs" / "production.toml"
    if not config_path.exists():
        pytest.skip("configs/production.toml not present")
    c = load_config(config_path)
    assert c.action_signing_required is True
    assert c.strict_secrets is True
    assert c.drift_strategy_default == "fallback_safe"
    assert c.enforcement_locked_path == "out/enforcement_locked"
    assert c.enforcement_require_approval_path == "out/enforcement_approval"


def test_soak_runner_pipeline_writes_report(tmp_path: Path) -> None:
    """Soak runner writes report JSON and .md even when child waveos runs fail (e.g. no -m waveos in env)."""
    repo_root = Path(__file__).resolve().parents[1]
    baseline_dir, run_dir = build_demo_dataset(tmp_path / "dataset")
    out_dir = tmp_path / "soak_out"
    report_path = tmp_path / "soak_report.json"
    cmd = [
        sys.executable,
        str(repo_root / "scripts" / "soak_runner.py"),
        "pipeline",
        "--iterations",
        "2",
        "--in",
        str(run_dir),
        "--baseline",
        str(baseline_dir),
        "--out",
        str(out_dir),
        "--report",
        str(report_path),
    ]
    result = subprocess.run(cmd, cwd=str(repo_root), capture_output=True, text=True, timeout=120)
    assert report_path.exists(), (result.stdout, result.stderr)
    report = json.loads(report_path.read_text())
    assert report["mode"] == "pipeline"
    assert report["run_count"] == 2
    assert report["success_count"] + report["failure_count"] == 2
    assert "duration_sec" in report
    assert "recovery_behavior" in report
    assert (report_path.with_suffix(".md")).exists()
    # When waveos is runnable as -m waveos, returncode is 0 and success_count==2
    if result.returncode == 0:
        assert report["success_count"] == 2


def test_chaos_runner_list_prints_scenarios() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "scripts" / "chaos_runner.py"
    if not script.exists():
        pytest.skip("scripts/chaos_runner.py not present")
    result = subprocess.run(
        [sys.executable, str(script), "--list"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0
    assert "kill_coordinator" in result.stdout
    assert "backpressure" in result.stdout
    assert "duplicate_join" in result.stdout


def test_chaos_runner_kill_coordinator_writes_report(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "scripts" / "chaos_runner.py"
    if not script.exists():
        pytest.skip("scripts/chaos_runner.py not present")
    report_path = tmp_path / "chaos_outcomes.json"
    result = subprocess.run(
        [sys.executable, str(script), "--scenario", "kill_coordinator", "--report", str(report_path)],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert report_path.exists()
    outcomes = json.loads(report_path.read_text())
    assert isinstance(outcomes, list)
    assert len(outcomes) >= 1
    r = outcomes[0]
    assert r["scenario"] == "kill_coordinator"
    assert r["outcome"] in ("passed", "agent_crash", "error", "coordinator_exit_early")
    assert "duration_sec" in r
    assert "details" in r
