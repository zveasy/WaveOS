"""Tests for WaveOS Compatibility Engine."""

from __future__ import annotations

import json
from pathlib import Path

from waveos.compat.preflight import (
    _check_arch,
    _check_dependencies,
    _check_disk_space,
    _check_os,
    _check_python_version,
    run_preflight,
)
from waveos.compat.strategies import RuntimeStrategy, describe_strategies, get_strategy


def test_check_os_linux() -> None:
    result = _check_os("linux")
    # On CI this should be Linux
    assert result.name == "os"


def test_check_os_empty() -> None:
    result = _check_os("")
    assert result.passed


def test_check_arch_empty() -> None:
    result = _check_arch("")
    assert result.passed


def test_check_disk_space() -> None:
    result = _check_disk_space(min_mb=1)
    assert result.passed


def test_check_python_version() -> None:
    result = _check_python_version()
    assert result.passed


def test_check_dependencies_available() -> None:
    result = _check_dependencies(["json", "os", "sys"])
    assert result.passed


def test_check_dependencies_missing() -> None:
    result = _check_dependencies(["nonexistent_package_xyz"])
    assert not result.passed
    assert "nonexistent_package_xyz" in result.message


def test_run_preflight_no_manifest(tmp_path: Path) -> None:
    result = run_preflight(tmp_path)
    assert result["outcome"] in ("allow", "warn")


def test_run_preflight_with_manifest(tmp_path: Path) -> None:
    manifest = {
        "bundle_id": "test",
        "version": "1.0",
        "targets": [{"os": "linux", "arch": "x86_64"}],
        "runtimes": {"strategy": "bundled", "dependencies": ["json", "os"]},
    }
    (tmp_path / "bundle.json").write_text(json.dumps(manifest))
    result = run_preflight(tmp_path)
    assert result["outcome"] in ("allow", "warn")
    assert any(c["name"] == "os" for c in result["checks"])


def test_strategies() -> None:
    bundled = get_strategy("bundled")
    assert bundled.strategy == RuntimeStrategy.BUNDLED
    sbs = get_strategy("side_by_side")
    assert sbs.strategy == RuntimeStrategy.SIDE_BY_SIDE


def test_describe_strategies() -> None:
    desc = describe_strategies()
    assert len(desc) == 4
    assert any(s["name"] == "bundled" and s["mvp"] for s in desc)
