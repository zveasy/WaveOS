# Threat Model

## Scope
Wave OS local demo pipeline and future production pipeline: collectors, normalization, scoring, policy, reporting, and actuator interfaces.

## Assets
- Telemetry data (potentially sensitive operational data)
- Policy recommendations and actions
- Reports and event timelines
- Build artifacts and SBOMs

## Trust Boundaries
- Ingestion boundary: files, future gNMI/OpenConfig stubs
- Processing boundary: normalization/scoring/policy runtime
- Output boundary: reports and JSON artifacts

## Threats
- Data tampering: malicious or corrupted telemetry inputs
- Supply-chain attacks: dependency compromise, artifact tampering
- Privilege misuse: unauthorized policy execution
- Information leakage: sensitive telemetry in logs or reports
- Denial of service: large inputs or malformed data

## Mitigations
- Input validation with Pydantic models
- Schema versioning and strict bounds
- Signed artifacts and SBOMs
- Least-privilege operational access
- Structured logging with redaction guidance
- SCA scans in CI

## Open Items
- Authentication/authorization for collectors
- Encryption at rest for reports
- Secrets management for future integrations
