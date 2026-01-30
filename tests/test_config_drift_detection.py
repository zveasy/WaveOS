from __future__ import annotations

import argparse
import json
from pathlib import Path

from waveos.cli import cmd_baseline, cmd_run
from waveos.sim import build_demo_dataset
from waveos.utils.config import WaveOSConfig


def test_config_drift_file_written(tmp_path: Path) -> None:
    baseline_dir, run_dir = build_demo_dataset(tmp_path / "dataset")
    config_a = WaveOSConfig(log_level="INFO")
    config_b = WaveOSConfig(log_level="DEBUG")
    baseline_args = argparse.Namespace(
        input=str(baseline_dir),
        role="operator",
        token=None,
        config_obj=config_a,
    )
    cmd_baseline(baseline_args)
    out_dir = tmp_path / "out"
    run_args = argparse.Namespace(
        input=str(run_dir),
        baseline=str(baseline_dir),
        output=str(out_dir),
        role="operator",
        token=None,
        config_obj=config_b,
    )
    cmd_run(run_args)
    drift_path = out_dir / "config_drift.json"
    assert drift_path.exists()
    payload = json.loads(drift_path.read_text(encoding="utf-8"))
    assert payload["baseline"] != payload["run"]
