"""
SDN adapter: execute reroute, QoS, rate-limit actions via REST API (e.g. gNMI gateway or switch REST).

Uses HTTP POST with JSON body; configurable URL per action type or single base URL.
Timeout and retry yield ACK; response 2xx = succeeded, else no_effect or unknown.
"""

from __future__ import annotations

import json
import os
import ssl
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

from waveos.models import ActionRecommendation, ActionType

from waveos.actuators.adapters.base import AdapterOutcome, AdapterResult, DeviceAdapterBase


def _build_actuator_ssl_context(
    cert_path: Optional[str] = None,
    key_path: Optional[str] = None,
    ca_path: Optional[str] = None,
) -> Optional[ssl.SSLContext]:
    """Build SSL context for mTLS (client cert) when cert/key paths are set."""
    cert_path = (cert_path or os.getenv("WAVEOS_ACTUATOR_MTLS_CERT_PATH", "")).strip()
    key_path = (key_path or os.getenv("WAVEOS_ACTUATOR_MTLS_KEY_PATH", "")).strip()
    ca_path = (ca_path or os.getenv("WAVEOS_ACTUATOR_MTLS_CA_PATH", "")).strip()
    if not cert_path or not key_path:
        return None
    try:
        ctx = ssl.create_default_context()
        if ca_path and Path(ca_path).exists():
            ctx.load_verify_locations(ca_path)
        ctx.load_cert_chain(certfile=cert_path, keyfile=key_path)
        return ctx
    except (ssl.SSLError, OSError):
        return None


class SdnRestAdapter(DeviceAdapterBase):
    """
    Execute SDN-related actions (REROUTE, RATE_LIMIT, QOS_PRIORITIZATION) via REST.
    Env: WAVEOS_ACTUATOR_SDN_URL; optional mTLS: WAVEOS_ACTUATOR_MTLS_CERT_PATH, _KEY_PATH, _CA_PATH.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        urls_by_action: Optional[Dict[str, str]] = None,
        timeout_seconds: float = 5.0,
        mtls_cert_path: Optional[str] = None,
        mtls_key_path: Optional[str] = None,
        mtls_ca_path: Optional[str] = None,
    ) -> None:
        self.base_url = (base_url or os.getenv("WAVEOS_ACTUATOR_SDN_URL", "")).strip()
        self.urls_by_action = urls_by_action or {}
        self.timeout_seconds = timeout_seconds
        self._ssl_context = _build_actuator_ssl_context(mtls_cert_path, mtls_key_path, mtls_ca_path)

    @property
    def name(self) -> str:
        return "sdn_rest"

    @property
    def supported_action_types(self) -> List[str]:
        return [
            ActionType.REROUTE.value,
            ActionType.RATE_LIMIT.value,
            ActionType.QOS_PRIORITIZATION.value,
        ]

    def _url_for(self, action: ActionRecommendation) -> Optional[str]:
        atype = action.action.value if hasattr(action.action, "value") else str(action.action)
        url = self.urls_by_action.get(atype) or os.getenv(f"WAVEOS_ACTUATOR_SDN_URL_{atype.replace('.', '_')}")
        if not url:
            url = self.base_url
        return (url or "").strip() or None

    def apply_one(self, action: ActionRecommendation, timeout_seconds: float = 10.0) -> AdapterResult:
        url = self._url_for(action)
        if not url:
            return AdapterResult(action=action, outcome=AdapterOutcome.NOT_APPLICABLE, message="No SDN URL configured")
        payload = {
            "entity_type": action.entity_type,
            "entity_id": action.entity_id,
            "action": action.action.value if hasattr(action.action, "value") else str(action.action),
            "rationale": action.rationale,
            "parameters": action.parameters,
        }
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload, default=str).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            kwargs: Dict[str, Any] = {"timeout": timeout_seconds}
            if self._ssl_context is not None and url.lower().startswith("https"):
                kwargs["context"] = self._ssl_context
            with urllib.request.urlopen(req, **kwargs) as resp:
                code = resp.status
                body = resp.read().decode("utf-8", errors="replace") if resp.length else ""
            if 200 <= code < 300:
                # Optional state read-back: GET state URL to confirm device state changed (Implementation Priorities §1)
                actual_state = self._read_state_after(action, timeout_seconds)
                return AdapterResult(
                    action=action, outcome=AdapterOutcome.SUCCEEDED, ack=True,
                    message=body[:200] if body else None, actual_state=actual_state,
                )
            return AdapterResult(action=action, outcome=AdapterOutcome.NO_EFFECT, ack=True, message=f"HTTP {code}")
        except Exception as exc:
            return AdapterResult(action=action, outcome=AdapterOutcome.UNKNOWN, ack=False, message=str(exc)[:200])

    def _read_state_after(self, action: ActionRecommendation, timeout_seconds: float) -> Optional[Dict[str, Any]]:
        """Optional: GET state URL (WAVEOS_ACTUATOR_SDN_STATE_URL or env per entity) to confirm device state."""
        state_url = (
            os.getenv("WAVEOS_ACTUATOR_SDN_STATE_URL", "").strip()
            or os.getenv(f"WAVEOS_ACTUATOR_SDN_STATE_URL_{action.entity_id.replace('-', '_').upper()}", "").strip()
        )
        if not state_url:
            return None
        try:
            req = urllib.request.Request(state_url, method="GET")
            kwargs: Dict[str, Any] = {"timeout": min(timeout_seconds, 3.0)}
            if self._ssl_context and state_url.lower().startswith("https"):
                kwargs["context"] = self._ssl_context
            with urllib.request.urlopen(req, **kwargs) as resp:
                if resp.status != 200:
                    return None
                body = resp.read().decode("utf-8", errors="replace")
                data = json.loads(body) if body.strip() else {}
                return {"state_url": state_url, "response": data} if isinstance(data, dict) else {"state_url": state_url, "response": body[:500]}
        except Exception:
            return None
