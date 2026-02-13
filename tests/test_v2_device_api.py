"""Tests for V2 device API and list-devices CLI."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from waveos.device_api import (
    DeviceCapability,
    get_device_registry,
    get_driver_instance,
)
from waveos.device_api.base import DeviceTelemetry
from waveos.policy.gates import check_soc_limit, check_temp_limit, check_health_gate, run_gates
from waveos.models import HealthScore, HealthStatus
from waveos.utils.time import utc_now


def test_device_registry_has_stub_drivers() -> None:
    reg = get_device_registry()
    assert "charger:stub" in reg
    assert "inverter:stub" in reg
    assert "bess:stub" in reg


def test_stub_charger_telemetry() -> None:
    driver = get_driver_instance(DeviceCapability.CHARGER, "stub")
    assert driver is not None
    telemetry = driver.read_telemetry("charger-1")
    assert telemetry is not None
    assert isinstance(telemetry, DeviceTelemetry)
    assert telemetry.capability == DeviceCapability.CHARGER
    assert telemetry.power_kw is not None


def test_list_devices_cli() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "-m", "waveos.cli", "list-devices"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        env={**os.environ, "WAVEOS_LICENSE_KEY": "WAVEOS-CI-20991231-TEST"},
    )
    assert result.returncode == 0
    assert "charger:stub" in result.stdout or "bess:stub" in result.stdout


def test_policy_gates_soc() -> None:
    r = check_soc_limit(85.0, 20.0)
    assert r.passed is True
    r2 = check_soc_limit(15.0, 20.0)
    assert r2.passed is False


def test_policy_gates_temp() -> None:
    r = check_temp_limit(50.0, 60.0)
    assert r.passed is True
    r2 = check_temp_limit(70.0, 60.0)
    assert r2.passed is False


def test_policy_gates_health() -> None:
    scores = [
        HealthScore(
            entity_type="link",
            entity_id="L1",
            score=80.0,
            status=HealthStatus.WARN,
            drivers=[],
            details={},
            window_start=utc_now(),
            window_end=utc_now(),
        ),
    ]
    r = check_health_gate(scores, allow_warn=True)
    assert r.passed is True
    r2 = check_health_gate(scores, allow_warn=False)
    assert r2.passed is False


def test_run_gates() -> None:
    config = [
        {"gate": "soc_min", "min_soc_pct": 20},
        {"gate": "temp_max", "max_temp_c": 60},
    ]
    results = run_gates(config, telemetry_aggregates={"soc_pct": 50.0, "temperature_c": 40.0})
    assert len(results) == 2
    assert results[0].passed is True
    assert results[1].passed is True
