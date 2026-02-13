"""V3: Zero-trust / IDS — device identity, secure boot flag, anomaly callback."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

from waveos.utils import get_logger

logger = get_logger("waveos.security")


@dataclass
class DeviceIdentity:
    """V3: Device identity for zero-trust (device_id + credential hint)."""
    device_id: str
    credential_hint: Optional[str] = None  # e.g. "x509", "spiffe"
    site_id: Optional[str] = None
    meta: Dict[str, Any] = field(default_factory=dict)


_anomaly_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None


def set_anomaly_callback(callback: Callable[[str, Dict[str, Any]], None]) -> None:
    """V3: Register IDS-style callback invoked on anomaly (e.g. telemetry spike)."""
    global _anomaly_callback
    _anomaly_callback = callback


def on_anomaly(rule_id: str, context: Dict[str, Any]) -> None:
    """V3: Invoke registered IDS anomaly callback if set."""
    if _anomaly_callback:
        try:
            _anomaly_callback(rule_id, context)
        except Exception as exc:
            logger.warning("Anomaly callback failed: %s", type(exc).__name__)
