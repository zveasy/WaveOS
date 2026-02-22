"""
Device adapters for real infrastructure: SDN (gNMI/NETCONF/REST), EV charger (OCPP), Inverter/BESS (Modbus/SunSpec).

Each adapter translates WaveOS ActionRecommendation into device-specific calls and returns
outcome (succeeded / no_effect / degraded / unknown) with optional ACK/timeout/retry.
"""

from waveos.actuators.adapters.base import DeviceAdapterBase, AdapterResult
from waveos.actuators.adapters.sdn_rest import SdnRestAdapter
from waveos.actuators.adapters.ocpp_charger import OcppChargerAdapter
from waveos.actuators.adapters.modbus_inverter import ModbusInverterAdapter

__all__ = [
    "DeviceAdapterBase",
    "AdapterResult",
    "SdnRestAdapter",
    "OcppChargerAdapter",
    "ModbusInverterAdapter",
]
