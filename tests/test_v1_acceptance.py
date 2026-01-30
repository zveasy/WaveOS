from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

from waveos.bundle import build_manifest, sign_manifest, verify_manifest, write_manifest
from waveos.sim import build_demo_dataset
from waveos.update_agent import install_bundle, rollback_bundle
from waveos.utils.config import WaveOSConfig
from waveos.cli import cmd_baseline, cmd_run
from waveos.utils.supervisor import supervise


def test_bundle_install_and_rollback() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        bundle_dir = temp_path / "bundle"
        bundle_dir.mkdir()
        (bundle_dir / "config.toml").write_text("key = 'value'\n", encoding="utf-8")
        manifest = build_manifest(bundle_dir, "0.1.0", "policy-1", "bundle-1")
        manifest_path = write_manifest(bundle_dir, manifest)
        key = "test-key"
        sign_manifest(manifest_path, key)
        assert verify_manifest(bundle_dir, key)

        active_dir = temp_path / "active"
        history_dir = temp_path / "history"
        state_dir = temp_path / "state"
        install_bundle(bundle_dir, active_dir, history_dir, state_dir, hmac_key=key)
        assert (active_dir / "bundle.json").exists()

        bundle_dir_2 = temp_path / "bundle2"
        bundle_dir_2.mkdir()
        (bundle_dir_2 / "config.toml").write_text("key = 'value2'\n", encoding="utf-8")
        manifest2 = build_manifest(bundle_dir_2, "0.1.0", "policy-2", "bundle-2")
        manifest2_path = write_manifest(bundle_dir_2, manifest2)
        sign_manifest(manifest2_path, key)
        install_bundle(bundle_dir_2, active_dir, history_dir, state_dir, hmac_key=key)
        assert (active_dir / "bundle.json").exists()

        rollback_bundle(active_dir, history_dir, state_dir)
        assert (active_dir / "bundle.json").exists()


def test_bundle_install_rejects_bad_signature() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        bundle_dir = temp_path / "bundle"
        bundle_dir.mkdir()
        (bundle_dir / "config.toml").write_text("key = 'value'\n", encoding="utf-8")
        manifest = build_manifest(bundle_dir, "0.1.0", "policy-1", "bundle-1")
        manifest_path = write_manifest(bundle_dir, manifest)
        sign_manifest(manifest_path, "good-key")

        active_dir = temp_path / "active"
        history_dir = temp_path / "history"
        state_dir = temp_path / "state"
        try:
            install_bundle(bundle_dir, active_dir, history_dir, state_dir, hmac_key="bad-key")
        except ValueError:
            pass
        else:
            raise AssertionError("Expected signature verification failure")


def test_run_outputs_include_evidence_and_recovery() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        baseline_dir, run_dir = build_demo_dataset(temp_path / "dataset")
        config = WaveOSConfig(
            enforce_actions=True,
            recovery_enabled=True,
            recovery_restart_command="true",
            recovery_degrade_command="true",
            watchdog_enabled=True,
            watchdog_path=str(temp_path / "watchdog.txt"),
            evidence_pack_enabled=True,
        )
        baseline_args = argparse.Namespace(
            input=str(baseline_dir),
            role="operator",
            token=None,
            config_obj=config,
        )
        cmd_baseline(baseline_args)

        out_dir = temp_path / "out"
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
        assert (output_root / "run_meta.json").exists()
        assert (output_root / "metrics.csv").exists()
        assert (output_root / "enforced_actions.jsonl").exists()
        assert (output_root / "recovery_actions.jsonl").exists()
        assert Path(config.watchdog_path).exists()
        assert any(path.name.startswith("evidence_pack_") for path in output_root.iterdir())


def test_supervisor_restarts_on_failure() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        marker = temp_path / "marker.txt"
        script = temp_path / "crash_once.sh"
        script.write_text(
            "#!/bin/sh\n"
            "if [ ! -f \"$1\" ]; then\n"
            "  touch \"$1\"\n"
            "  exit 1\n"
            "fi\n"
            "exit 0\n",
            encoding="utf-8",
        )
        script.chmod(0o755)
        exit_code = supervise([str(script), str(marker)], max_restarts=2, backoff_seconds=0.1)
        assert exit_code == 0


def _resolve_output_dir(out_dir: Path) -> Path:
    if (out_dir / "run_meta.json").exists():
        return out_dir
    subdirs = [path for path in out_dir.iterdir() if path.is_dir()]
    if not subdirs:
        return out_dir
    return sorted(subdirs)[0]
