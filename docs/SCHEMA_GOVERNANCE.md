# Schema Governance

## Telemetry Schema Versioning
- Records may include `schema_version`.
- Missing version defaults to `1`.
- Version `0` fields are migrated (`temp_c`, `tx_power`, `rx_power`).

## Backward Compatibility
- Older schema versions are accepted and migrated in `normalize_record`.
- New fields must be optional with defaults.

## Migration Process
1. Add migration in `normalize/pipeline.py`.
2. Update tests to cover legacy payloads.
3. Bump `schema_version` in docs when breaking changes are introduced.
