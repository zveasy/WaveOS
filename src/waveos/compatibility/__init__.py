"""V3: Multi-RTOS / runtime translation layer — normalize vendor/kernel formats to WaveOS schema."""

from waveos.compatibility.translator import RuntimeTranslator, translate_telemetry

__all__ = ["RuntimeTranslator", "translate_telemetry"]
