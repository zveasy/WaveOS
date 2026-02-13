"""Tests for license check and health-check CLI."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from waveos.licensing import LicenseError, get_license_tier, require_license


def test_require_license_accepts_valid_key_format(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WAVEOS_LICENSE_SKIP", "")
    monkeypatch.setenv("WAVEOS_LICENSE_KEY", "WAVEOS-CI-20991231-TEST")
    monkeypatch.delenv("WAVEOS_LICENSE_PATH", raising=False)
    require_license()  # no raise


def test_require_license_accepts_skip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WAVEOS_LICENSE_SKIP", "1")
    monkeypatch.setenv("WAVEOS_LICENSE_KEY", "")
    monkeypatch.delenv("WAVEOS_LICENSE_PATH", raising=False)
    require_license()  # no raise


def test_require_license_raises_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WAVEOS_LICENSE_SKIP", "")
    monkeypatch.setenv("WAVEOS_LICENSE_KEY", "")
    monkeypatch.delenv("WAVEOS_LICENSE_PATH", raising=False)
    with pytest.raises(LicenseError, match="Valid Wave OS license required"):
        require_license()


def test_require_license_accepts_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    license_file = tmp_path / "license.key"
    license_file.write_text("WAVEOS-PROD-20991231", encoding="utf-8")
    monkeypatch.setenv("WAVEOS_LICENSE_SKIP", "")
    monkeypatch.delenv("WAVEOS_LICENSE_KEY", raising=False)
    monkeypatch.setenv("WAVEOS_LICENSE_PATH", str(license_file))
    require_license()  # no raise


def test_require_license_raises_when_expired(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WAVEOS_LICENSE_SKIP", "")
    monkeypatch.setenv("WAVEOS_LICENSE_KEY", "WAVEOS-PROD-20200101")  # past date
    monkeypatch.delenv("WAVEOS_LICENSE_PATH", raising=False)
    with pytest.raises(LicenseError, match="expired"):
        require_license()


def test_get_license_tier(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WAVEOS_LICENSE_KEY", "WAVEOS-ENTERPRISE-ABC-20991231")
    assert get_license_tier() == "enterprise"
    monkeypatch.setenv("WAVEOS_LICENSE_KEY", "WAVEOS-DOD-XYZ-20991231")
    assert get_license_tier() == "dod"
    monkeypatch.delenv("WAVEOS_LICENSE_KEY", raising=False)
    monkeypatch.delenv("WAVEOS_LICENSE_PATH", raising=False)
    assert get_license_tier() == "evaluation"


def test_health_check_cli_exits_zero() -> None:
    """health-check subcommand exits 0 (for K8s exec probe)."""
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env.setdefault("WAVEOS_LICENSE_KEY", "WAVEOS-CI-20991231-TEST")
    result = subprocess.run(
        ["waveos", "health-check"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0
    assert "ok" in (result.stdout or "").lower()


def test_validate_config_cli_exits_zero() -> None:
    """validate-config subcommand exits 0 when config is valid."""
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env.setdefault("WAVEOS_LICENSE_KEY", "WAVEOS-CI-20991231-TEST")
    result = subprocess.run(
        ["waveos", "validate-config"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0
    assert "valid" in (result.stdout or "").lower()
