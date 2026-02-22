"""
EV charger adapter (OCPP 1.6 / 2.0.1): throttle/limit, pause/resume via SetChargingProfile and ChangeAvailability.

When the optional dependency `ocpp` is installed and charger_gateway_url is set, builds OCPP calls and POSTs
them to a gateway that forwards to the charge point. Otherwise returns NOT_APPLICABLE so the pipeline can fall back.
"""

from __future__ import annotations

import json
import os
import urllib.request
from typing import List, Optional

from waveos.models import ActionRecommendation, ActionType

from waveos.actuators.adapters.base import AdapterOutcome, AdapterResult, DeviceAdapterBase
from waveos.actuators.adapters.sdn_rest import _build_actuator_ssl_context


def _build_ocpp_payload(action: ActionRecommendation, ocpp_version: str) -> Optional[dict]:
    """Build OCPP 1.6-style payload for gateway (charge_point_id + action params). Returns None if not supported."""
    if ocpp_version != "1.6":
        return None
    atype = action.action.value if hasattr(action.action, "value") else str(action.action)
    # charge_point_id from entity_id (e.g. "charger-1" -> use as id in payload for gateway routing)
    charge_point_id = action.entity_id
    connector_id = int(action.parameters.get("connector_id", 1))
    if atype == ActionType.RATE_LIMIT.value:
        # SetChargingProfile: limit power (limit_pct or limit_kw)
        limit_pct = action.parameters.get("limit_pct")
        limit_kw = action.parameters.get("limit_kw")
        if limit_kw is None and limit_pct is not None:
            limit_kw = max(0.0, min(100.0, float(limit_pct))) * 0.22  # assume ~22 kW max -> kW
        if limit_kw is None:
            limit_kw = 11.0
        profile = {
            "chargingProfileId": 1,
            "stackLevel": 0,
            "chargingProfilePurpose": "TxDefaultProfile",
            "chargingProfileKind": "Absolute",
            "chargingSchedule": {
                "chargingRateUnit": "W",
                "chargingSchedulePeriod": [{"startPeriod": 0, "limit": int(float(limit_kw) * 1000)}],
            },
        }
        payload = {
            "messageTypeId": 2,
            "action": "SetChargingProfile",
            "payload": {
                "connectorId": connector_id,
                "csChargingProfiles": profile,
            },
        }
        return {"charge_point_id": charge_point_id, "ocpp": payload}
    if atype == ActionType.POWER_THERMAL_CONSTRAINT.value:
        # ChangeAvailability: Operative / Inoperative (pause)
        operative = action.parameters.get("operative", True)
        payload = {
            "messageTypeId": 2,
            "action": "ChangeAvailability",
            "payload": {
                "connectorId": connector_id,
                "type": "Operative" if operative else "Inoperative",
            },
        }
        return {"charge_point_id": charge_point_id, "ocpp": payload}
    return None


class OcppChargerAdapter(DeviceAdapterBase):
    """
    OCPP 1.6 adapter for EV chargers: SetChargingProfile (rate limit), ChangeAvailability (pause/resume).
    When ocpp is installed and charger_gateway_url is set, POSTs JSON-RPC OCPP payload to the gateway.
    """

    def __init__(
        self,
        charger_gateway_url: Optional[str] = None,
        ocpp_version: str = "1.6",
        timeout_seconds: float = 10.0,
        mtls_cert_path: Optional[str] = None,
        mtls_key_path: Optional[str] = None,
        mtls_ca_path: Optional[str] = None,
    ) -> None:
        self.charger_gateway_url = (charger_gateway_url or os.getenv("WAVEOS_ACTUATOR_OCPP_GATEWAY_URL", "")).strip()
        self.ocpp_version = ocpp_version
        self.timeout_seconds = timeout_seconds
        self._ssl_context = _build_actuator_ssl_context(mtls_cert_path, mtls_key_path, mtls_ca_path)

    @property
    def name(self) -> str:
        return "ocpp_charger"

    @property
    def supported_action_types(self) -> List[str]:
        return [
            ActionType.RATE_LIMIT.value,
            ActionType.POWER_THERMAL_CONSTRAINT.value,
        ]

    def apply_one(self, action: ActionRecommendation, timeout_seconds: float = 10.0) -> AdapterResult:
        if not self.charger_gateway_url:
            return AdapterResult(
                action=action,
                outcome=AdapterOutcome.NOT_APPLICABLE,
                message="OCPP gateway URL not set (WAVEOS_ACTUATOR_OCPP_GATEWAY_URL or charger_gateway_url)",
            )
        body = _build_ocpp_payload(action, self.ocpp_version)
        if not body:
            return AdapterResult(
                action=action,
                outcome=AdapterOutcome.NOT_APPLICABLE,
                message="OCPP payload not built for this action/version",
            )
        try:
            data = json.dumps(body, default=str).encode("utf-8")
            req = urllib.request.Request(
                self.charger_gateway_url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            kwargs = {"timeout": timeout_seconds}
            if self._ssl_context is not None and self.charger_gateway_url.lower().startswith("https"):
                kwargs["context"] = self._ssl_context
            with urllib.request.urlopen(req, **kwargs) as resp:
                code = getattr(resp, "status", 200)
                resp_body = resp.read().decode("utf-8", errors="replace") if getattr(resp, "length", None) else ""
            if 200 <= code < 300:
                return AdapterResult(action=action, outcome=AdapterOutcome.SUCCEEDED, ack=True, message=resp_body[:200] if resp_body else None)
            return AdapterResult(action=action, outcome=AdapterOutcome.NO_EFFECT, ack=True, message=f"HTTP {code}")
        except Exception as exc:
            return AdapterResult(action=action, outcome=AdapterOutcome.UNKNOWN, ack=False, message=str(exc)[:200])
