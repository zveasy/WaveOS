"""V2: Device driver registry — register and resolve drivers by capability/vendor."""

from __future__ import annotations

from typing import Dict, List, Optional, Type

from waveos.device_api.base import DeviceCapability, DeviceDriver
from waveos.utils import get_logger

logger = get_logger("waveos.device_api")

_registry: Dict[str, Type[DeviceDriver]] = {}  # key = f"{capability.value}:{vendor}" -> driver class
_instances: Dict[str, DeviceDriver] = {}  # key -> instance (optional singleton per key)


def register_driver(capability: DeviceCapability, vendor: str, driver_class: Type[DeviceDriver]) -> None:
    """Register a device driver for a capability and vendor."""
    key = f"{capability.value}:{vendor}"
    _registry[key] = driver_class
    logger.debug("Registered device driver %s", key)


def get_driver(capability: DeviceCapability, vendor: str) -> Optional[Type[DeviceDriver]]:
    """Get a driver class for capability and vendor."""
    key = f"{capability.value}:{vendor}"
    return _registry.get(key)


def get_driver_instance(
    capability: DeviceCapability,
    vendor: str,
    config: Optional[dict] = None,
    singleton: bool = True,
) -> Optional[DeviceDriver]:
    """Get or create a driver instance. If singleton=True, reuse same instance per key."""
    key = f"{capability.value}:{vendor}"
    cls = _registry.get(key)
    if cls is None:
        return None
    if singleton and key in _instances:
        return _instances[key]
    try:
        instance = cls(**(config or {}))
        if singleton:
            _instances[key] = instance
        return instance
    except TypeError:
        try:
            instance = cls()
            if singleton:
                _instances[key] = instance
            return instance
        except Exception as exc:
            logger.warning("Failed to instantiate driver %s: %s", key, type(exc).__name__)
            return None
    except Exception as exc:
        logger.warning("Failed to instantiate driver %s: %s", key, type(exc).__name__)
        return None


def get_device_registry() -> Dict[str, Type[DeviceDriver]]:
    """Return a copy of the driver registry (read-only)."""
    return dict(_registry)


def list_capabilities() -> List[str]:
    """List registered capability:vendor keys."""
    return list(_registry.keys())
