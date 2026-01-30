# Telemetry Mapping Guide

Use this to map real device payloads into `TelemetrySample`.

## Microgrid
Source fields -> WaveOS fields:
- `active_power_kw` -> `power_kw`
- `energy_kwh_total` -> `energy_kwh`
- `line_voltage_v` -> `voltage_v`
- `line_current_a` -> `current_a`

## EV Charger
Source fields -> WaveOS fields:
- `charger_power_kw` -> `power_kw`
- `metered_energy_kwh` -> `energy_kwh`
- `dc_voltage_v` -> `voltage_v`
- `dc_current_a` -> `current_a`
- `soc_pct` -> `battery_soc_pct`
- `status` -> `charger_status`
- `fault_code` -> `charger_fault_code`

## Validation
Run:
```
waveos validate-telemetry --in telemetry.jsonl --profile microgrid --out validation.json
```
