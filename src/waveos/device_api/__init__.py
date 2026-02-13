"""V2: Standard device API for charger, inverter, BESS, microgrid, and telemetry."""

from waveos.device_api.base import (
    DeviceCapability,
    DeviceCommand,
    DeviceDriver,
    DeviceTelemetry,
)
from waveos.device_api.registry import get_device_registry, get_driver_instance, register_driver
from waveos.device_api.adapters import register_stub_drivers

register_stub_drivers()

__all__ = [
    "DeviceDriver",
    "DeviceCommand",
    "DeviceTelemetry",
    "DeviceCapability",
    "get_device_registry",
    "get_driver_instance",
    "register_driver",
]
