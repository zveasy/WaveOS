"""
Inverter/BESS adapter (Modbus TCP/RTU, SunSpec): setpoints, curtailment, SOC constraints.

When the optional dependency `pymodbus` is installed and host is set, connects via Modbus TCP
and writes to common SunSpec/register map (e.g. power limit, curtailment). Otherwise returns NOT_APPLICABLE.
"""

from __future__ import annotations

import os
from typing import List, Optional

from waveos.models import ActionRecommendation, ActionType

from waveos.actuators.adapters.base import AdapterOutcome, AdapterResult, DeviceAdapterBase

_PYMODBUS_AVAILABLE = False
try:
    from pymodbus.client import ModbusTcpClient
    _PYMODBUS_AVAILABLE = True
except ImportError:
    pass

# SunSpec common model 103 (inverter): Power limit is often at register 0 (W limit) or vendor-specific.
# We use a configurable base register for power setpoint (default 40000 = 0 in 4xxxx notation).
DEFAULT_POWER_LIMIT_REGISTER = 40000
DEFAULT_UNIT_ID = 1


def _write_power_limit_sync(host: str, port: int, unit_id: int, limit_kw: float, register: int, timeout: float) -> tuple[bool, str]:
    """Write power limit (kW) to one register as uint16 (scale 0.1 kW). Returns (success, message)."""
    if not _PYMODBUS_AVAILABLE:
        return False, "pymodbus not installed (pip install waveos[modbus])"
    try:
        client = ModbusTcpClient(host=host, port=port, timeout=timeout)
        client.connect()
        try:
            # SunSpec often uses 0.1 kW units; clamp to 0-65535 (uint16) -> 0-6553.5 kW
            limit_deci_kw = max(0, min(65535, int(limit_kw * 10)))
            # Modbus register address: 4xxxx -> 0-based register index
            reg_addr = (register - 40000) if register >= 40000 else register
            result = client.write_register(reg_addr, limit_deci_kw, slave=unit_id)
            if result.isError():
                return False, str(result)
            return True, "ok"
        finally:
            client.close()
    except Exception as exc:
        return False, str(exc)[:200]


class ModbusInverterAdapter(DeviceAdapterBase):
    """
    Modbus TCP adapter for inverter/BESS: write power setpoint or curtailment (SunSpec-style register).
    When pymodbus is installed and host is set, connects and writes to the configured register.
    """

    def __init__(
        self,
        host: Optional[str] = None,
        port: int = 502,
        unit_id: int = DEFAULT_UNIT_ID,
        power_limit_register: int = DEFAULT_POWER_LIMIT_REGISTER,
        timeout_seconds: float = 5.0,
    ) -> None:
        self.host = (host or os.getenv("WAVEOS_ACTUATOR_MODBUS_HOST", "")).strip()
        self.port = port
        self.unit_id = unit_id
        self.power_limit_register = power_limit_register
        self.timeout_seconds = timeout_seconds

    @property
    def name(self) -> str:
        return "modbus_inverter"

    @property
    def supported_action_types(self) -> List[str]:
        return [
            ActionType.POWER_THERMAL_CONSTRAINT.value,
            ActionType.RATE_LIMIT.value,
        ]

    def apply_one(self, action: ActionRecommendation, timeout_seconds: float = 10.0) -> AdapterResult:
        if not self.host:
            return AdapterResult(
                action=action,
                outcome=AdapterOutcome.NOT_APPLICABLE,
                message="Modbus host not set (WAVEOS_ACTUATOR_MODBUS_HOST or host)",
            )
        if not _PYMODBUS_AVAILABLE:
            return AdapterResult(
                action=action,
                outcome=AdapterOutcome.NOT_APPLICABLE,
                message="Install optional dependency: pip install waveos[modbus] for Modbus/SunSpec inverter control",
            )
        atype = action.action.value if hasattr(action.action, "value") else str(action.action)
        timeout = min(timeout_seconds, self.timeout_seconds)
        if atype in (ActionType.POWER_THERMAL_CONSTRAINT.value, ActionType.RATE_LIMIT.value):
            limit_kw = action.parameters.get("limit_kw")
            limit_pct = action.parameters.get("limit_pct")
            if limit_kw is None and limit_pct is not None:
                # Assume max 100 kW for percentage
                limit_kw = float(limit_pct) * 1.0  # 1% = 1 kW placeholder; configurable max in production
            if limit_kw is None:
                limit_kw = 0.0  # curtail to zero
            ok, msg = _write_power_limit_sync(
                self.host,
                self.port,
                self.unit_id,
                float(limit_kw),
                self.power_limit_register,
                timeout,
            )
            if ok:
                return AdapterResult(action=action, outcome=AdapterOutcome.SUCCEEDED, ack=True, message=msg)
            return AdapterResult(action=action, outcome=AdapterOutcome.UNKNOWN, ack=False, message=msg)
        return AdapterResult(
            action=action,
            outcome=AdapterOutcome.NOT_APPLICABLE,
            message="Unsupported action for Modbus inverter",
        )
