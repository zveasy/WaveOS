from __future__ import annotations

import argparse
import json
from pathlib import Path

from waveos.cli import cmd_baseline, cmd_run
from waveos.sim import build_demo_dataset
from waveos.utils.config import WaveOSConfig


def test_pipeline_integration_outputs(tmp_path: Path) -> None:
    baseline_dir, run_dir = build_demo_dataset(tmp_path / "dataset")
    config = WaveOSConfig()
    baseline_args = argparse.Namespace(
        input=str(baseline_dir),
        role="operator",
        token=None,
        config_obj=config,
    )
    cmd_baseline(baseline_args)

    out_dir = tmp_path / "out"
    run_args = argparse.Namespace(
        input=str(run_dir),
        baseline=str(baseline_dir),
        output=str(out_dir),
        role="operator",
        token=None,
        config_obj=config,
    )
    cmd_run(run_args)

    output_root = _resolve_output_dir(out_dir)
    assert (output_root / "health_summary.json").exists()
    assert (output_root / "events.jsonl").exists()
    assert (output_root / "actions.json").exists()
    assert (output_root / "report.html").exists()


def test_regression_health_statuses(tmp_path: Path) -> None:
    baseline_dir, run_dir = build_demo_dataset(tmp_path / "dataset")
    config = WaveOSConfig()
    baseline_args = argparse.Namespace(
        input=str(baseline_dir),
        role="operator",
        token=None,
        config_obj=config,
    )
    cmd_baseline(baseline_args)
    out_dir = tmp_path / "out"
    run_args = argparse.Namespace(
        input=str(run_dir),
        baseline=str(baseline_dir),
        output=str(out_dir),
        role="operator",
        token=None,
        config_obj=config,
    )
    cmd_run(run_args)
    output_root = _resolve_output_dir(out_dir)
    payload = json.loads((output_root / "health_summary.json").read_text(encoding="utf-8"))
    statuses = [entry["status"] for entry in payload]
    assert statuses.count("PASS") == 2
    assert statuses.count("WARN") == 1
    assert statuses.count("FAIL") == 1


def _resolve_output_dir(out_dir: Path) -> Path:
    if (out_dir / "run_meta.json").exists():
        return out_dir
    subdirs = [path for path in out_dir.iterdir() if path.is_dir()]
    if not subdirs:
        return out_dir
    return sorted(subdirs)[0]
