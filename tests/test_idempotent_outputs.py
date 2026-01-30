from __future__ import annotations

import argparse
from pathlib import Path

from waveos.cli import cmd_baseline, cmd_run
from waveos.sim import build_demo_dataset
from waveos.utils.config import WaveOSConfig


def test_idempotent_outputs_creates_run_subdir(tmp_path: Path) -> None:
    baseline_dir, run_dir = build_demo_dataset(tmp_path / "dataset")
    config = WaveOSConfig(idempotent_outputs=True)
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
    cmd_run(run_args)
    subdirs = [path for path in out_dir.iterdir() if path.is_dir()]
    assert subdirs
