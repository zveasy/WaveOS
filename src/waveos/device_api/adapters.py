"""V2: Stub device adapters (charger, inverter, BESS) for testing and integration."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from waveos.device_api.base import (
    DeviceCapability,
    DeviceCommand,
    DeviceDriver,
    DeviceTelemetry,
)
from waveos.device_api.registry import register_driver


class StubChargerDriver(DeviceDriver):
    """Stub charger adapter — returns synthetic telemetry; commands are no-op logged."""

    def __init__(self, **config: Any) -> None:
        self._config = config
        self._last_command: Optional[DeviceCommand] = None

    @property
    def capability(self) -> DeviceCapability:
        return DeviceCapability.CHARGER

    @property
    def vendor(self) -> str:
        return "stub"

    def read_telemetry(self, device_id: str) -> Optional[DeviceTelemetry]:
        return DeviceTelemetry(
            device_id=device_id,
            capability=DeviceCapability.CHARGER,
            timestamp=datetime.now(timezone.utc),
            voltage_v=240.0,
            current_a=32.0,
            power_kw=7.68,
            status="charging",
            meta={"stub": True},
        )

    def send_command(self, cmd: DeviceCommand) -> bool:
        self._last_command = cmd
        return True

    def list_devices(self) -> List[str]:
        return self._config.get("device_ids", ["charger-1"])


class StubInverterDriver(DeviceDriver):
    """Stub inverter adapter."""

    def __init__(self, **config: Any) -> None:
        self._config = config

    @property
    def capability(self) -> DeviceCapability:
        return DeviceCapability.INVERTER

    @property
    def vendor(self) -> str:
        return "stub"

    def read_telemetry(self, device_id: str) -> Optional[DeviceTelemetry]:
        return DeviceTelemetry(
            device_id=device_id,
            capability=DeviceCapability.INVERTER,
            timestamp=datetime.now(timezone.utc),
            power_kw=-5.0,  # export
            frequency_hz=60.0,
            status="exporting",
            meta={"stub": True},
        )

    def list_devices(self) -> List[str]:
        return self._config.get("device_ids", ["inverter-1"])


class StubBESSDriver(DeviceDriver):
    """Stub BESS (battery energy storage) adapter."""

    def __init__(self, **config: Any) -> None:
        self._config = config

    @property
    def capability(self) -> DeviceCapability:
        return DeviceCapability.BESS

    @property
    def vendor(self) -> str:
        return "stub"

    def read_telemetry(self, device_id: str) -> Optional[DeviceTelemetry]:
        return DeviceTelemetry(
            device_id=device_id,
            capability=DeviceCapability.BESS,
            timestamp=datetime.now(timezone.utc),
            power_kw=0.0,
            soc_pct=85.0,
            energy_kwh=100.0,
            status="idle",
            meta={"stub": True},
        )

    def send_command(self, cmd: DeviceCommand) -> bool:
        if cmd.action in ("set_power_kw", "set_soc_limit", "dispatch"):
            return True
        return False

    def list_devices(self) -> List[str]:
        return self._config.get("device_ids", ["bess-1"])


def register_stub_drivers() -> None:
    """Register stub drivers so they appear in the device API registry."""
    register_driver(DeviceCapability.CHARGER, "stub", StubChargerDriver)
    register_driver(DeviceCapability.INVERTER, "stub", StubInverterDriver)
    register_driver(DeviceCapability.BESS, "stub", StubBESSDriver)
