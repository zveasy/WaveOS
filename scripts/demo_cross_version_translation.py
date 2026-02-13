#!/usr/bin/env python3
"""
Demo: cross-version / multi-RTOS translation.
Shows that different "runtimes" (e.g. VxWorks 6 vs 7, or different vendors)
can send different field names; WaveOS normalizes them to the same schema.
Run: python scripts/demo_cross_version_translation.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running from repo root
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from waveos.compatibility import RuntimeTranslator, translate_telemetry


def main() -> int:
    # Payload "from" a VxWorks 6–style app (short names, ts)
    vxworks6_style = {
        "ts": "2026-02-13T12:00:00Z",
        "link": "L1",
        "errors": 0,
        "drops": 0,
        "temp_c": 45.5,
        "soc_pct": 78.0,
    }

    # Payload "from" a Linux / vendor-style app (long names, timestamp)
    linux_style = {
        "timestamp": "2026-02-13T12:00:00Z",
        "entity_id": "L1",
        "errors": 0,
        "drops": 0,
        "temperature_c": 45.5,
        "battery_soc_pct": 78.0,
    }

    # Third shape: another vendor (port_id, congestion_pct)
    vendor_style = {
        "time": "2026-02-13T12:00:00Z",
        "link_id": "L1",
        "port_id": "P1",
        "congestion_pct": 12.5,
    }

    translator = RuntimeTranslator(source_format="generic")

    for name, raw in [
        ("VxWorks 6-style (ts, link, temp_c, soc_pct)", vxworks6_style),
        ("Linux/vendor (timestamp, entity_id, temperature_c, battery_soc_pct)", linux_style),
        ("Vendor (time, link_id, port_id, congestion_pct)", vendor_style),
    ]:
        sample = translator.translate(raw)
        if sample is None:
            print(f"  {name}: FAILED to translate")
            continue
        print(f"  {name}:")
        print(f"    -> link_id={sample.link_id!r} port_id={sample.port_id!r} "
              f"temperature_c={sample.temperature_c} battery_soc_pct={sample.battery_soc_pct} "
              f"congestion_pct={sample.congestion_pct}")

    # Show they normalize to same link_id and compatible fields
    s1 = translate_telemetry(vxworks6_style, "generic")
    s2 = translate_telemetry(linux_style, "generic")
    assert s1.link_id == s2.link_id == "L1"
    assert s1.temperature_c == s2.temperature_c == 45.5
    assert s1.battery_soc_pct == s2.battery_soc_pct == 78.0
    print("\nCross-version check: VxWorks6 and Linux payloads normalized to same link_id, temperature_c, battery_soc_pct.")
    return 0


if __name__ == "__main__":
    print("WaveOS cross-version translation demo (different runtimes -> same schema)\n")
    raise SystemExit(main())
