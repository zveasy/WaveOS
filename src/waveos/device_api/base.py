"""V2: Standard device API — abstract interface for charger, inverter, BESS, etc."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class DeviceCapability(str, Enum):
    """Device type / capability for the standard API."""
    CHARGER = "charger"
    INVERTER = "inverter"
    BESS = "bess"
    MICROGRID = "microgrid"
    RELAY = "relay"
    METER = "meter"


@dataclass
class DeviceTelemetry:
    """Standard telemetry read from a device (vendor-agnostic)."""
    device_id: str
    capability: DeviceCapability
    timestamp: datetime
    voltage_v: Optional[float] = None
    current_a: Optional[float] = None
    power_kw: Optional[float] = None
    energy_kwh: Optional[float] = None
    soc_pct: Optional[float] = None  # state of charge (BESS)
    temperature_c: Optional[float] = None
    frequency_hz: Optional[float] = None
    status: Optional[str] = None  # e.g. charging, idle, fault
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DeviceCommand:
    """Standard command to send to a device (vendor-agnostic)."""
    device_id: str
    capability: DeviceCapability
    action: str  # e.g. set_power_kw, set_soc_limit, island, throttle
    params: Dict[str, Any] = field(default_factory=dict)


class DeviceDriver(ABC):
    """Abstract driver for a device (charger, inverter, BESS, etc.)."""

    @property
    @abstractmethod
    def capability(self) -> DeviceCapability:
        """Device capability this driver supports."""
        ...

    @property
    @abstractmethod
    def vendor(self) -> str:
        """Vendor or protocol name (e.g. ABB, Modbus, OpenADR)."""
        ...

    @abstractmethod
    def read_telemetry(self, device_id: str) -> Optional[DeviceTelemetry]:
        """Read current telemetry from the device. Return None if unavailable."""
        ...

    def send_command(self, cmd: DeviceCommand) -> bool:
        """Send a command to the device. Return True if accepted. Default: no-op."""
        return False  # V2 stub; override in real adapters

    def list_devices(self) -> List[str]:
        """List device IDs this driver can reach. Default: empty."""
        return []
