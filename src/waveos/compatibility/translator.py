"""V3: Runtime translation — map vendor/kernel-specific payloads to WaveOS canonical form."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from waveos.models.core import TelemetrySample
from waveos.utils import get_logger

logger = get_logger("waveos.compatibility")


class RuntimeTranslator:
    """V3: Translate from vendor/kernel/RTOS-specific format to WaveOS TelemetrySample."""

    def __init__(self, source_format: str = "generic") -> None:
        self.source_format = source_format  # e.g. vxworks_6, linux_5, abb_protocol

    def translate(self, raw: Dict[str, Any]) -> Optional[TelemetrySample]:
        """Convert a single raw record to TelemetrySample, or None if invalid."""
        try:
            return translate_telemetry(raw, self.source_format)
        except Exception as exc:
            logger.debug("Translation failed for %s: %s", self.source_format, type(exc).__name__)
            return None

    def translate_batch(self, raw_list: List[Dict[str, Any]]) -> List[TelemetrySample]:
        """Convert a list of raw records; skip invalid ones."""
        out: List[TelemetrySample] = []
        for raw in raw_list:
            sample = self.translate(raw)
            if sample is not None:
                out.append(sample)
        return out


def translate_telemetry(raw: Dict[str, Any], source_format: str = "generic") -> TelemetrySample:
    """Translate a raw telemetry record to TelemetrySample. Handles generic and common vendor shapes."""
    # Normalize timestamp
    ts = raw.get("timestamp") or raw.get("ts") or raw.get("time")
    if isinstance(ts, (int, float)):
        dt = datetime.fromtimestamp(float(ts), tz=timezone.utc)
    elif isinstance(ts, str):
        from waveos.utils.time import parse_timestamp
        dt = parse_timestamp(ts)
    else:
        dt = datetime.now(timezone.utc)

    link_id = str(raw.get("link_id") or raw.get("link") or raw.get("entity_id") or "unknown")
    port_id = raw.get("port_id") or raw.get("port")

    def _num(key: str, default: float = 0.0) -> float:
        v = raw.get(key)
        if v is None:
            return default
        try:
            return float(v)
        except (TypeError, ValueError):
            return default

    def _opt(key: str) -> Optional[float]:
        v = raw.get(key)
        if v is None:
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    return TelemetrySample(
        timestamp=dt,
        link_id=link_id,
        port_id=str(port_id) if port_id is not None else None,
        errors=int(_num("errors")),
        drops=int(_num("drops")),
        retries=int(_num("retries")),
        fec_corrected=int(raw.get("fec_corrected", 0) or 0),
        fec_uncorrected=int(raw.get("fec_uncorrected", 0) or 0),
        ber=_opt("ber"),
        tx_power_dbm=_opt("tx_power_dbm"),
        rx_power_dbm=_opt("rx_power_dbm"),
        temperature_c=_opt("temperature_c") or _opt("temp_c"),
        congestion_pct=_opt("congestion_pct"),
        power_kw=_opt("power_kw"),
        energy_kwh=_opt("energy_kwh"),
        charger_status=raw.get("charger_status"),
        charger_fault_code=raw.get("charger_fault_code"),
        battery_soc_pct=_opt("battery_soc_pct") or _opt("soc_pct"),
        voltage_v=_opt("voltage_v"),
        current_a=_opt("current_a"),
        meta={k: v for k, v in raw.items() if k not in {
            "timestamp", "ts", "time", "link_id", "link", "entity_id", "port_id", "port",
            "errors", "drops", "retries", "fec_corrected", "fec_uncorrected", "ber",
            "tx_power_dbm", "rx_power_dbm", "temperature_c", "temp_c", "congestion_pct",
            "power_kw", "energy_kwh", "charger_status", "charger_fault_code",
            "battery_soc_pct", "soc_pct", "voltage_v", "current_a",
        }},
    )
