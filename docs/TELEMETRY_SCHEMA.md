# Telemetry Schema

## Core Fields
- `timestamp` (ISO8601)
- `link_id` (string)
- `errors`, `drops`, `retries`, `fec_corrected`, `fec_uncorrected`
- `ber`, `tx_power_dbm`, `rx_power_dbm`, `temperature_c`, `congestion_pct`

## Microgrid / EV Charger Fields
- `power_kw`: instantaneous power (kW)
- `energy_kwh`: cumulative energy (kWh)
- `voltage_v`: voltage (V)
- `current_a`: current (A)
- `battery_soc_pct`: state of charge (%)
- `charger_status`: string status (`idle`, `charging`, `fault`, etc.)
- `charger_fault_code`: string fault code if present

## Backward Compatibility
- `schema_version` defaults to 1 if missing.
- Version 0 migrations:
  - `power_w` -> `power_kw`
  - `energy_wh` -> `energy_kwh`
