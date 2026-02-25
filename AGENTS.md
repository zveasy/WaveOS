# AGENTS.md

## Cursor Cloud specific instructions

### Overview

Wave OS is a Python 3.11+ CLI application (`waveos`) — a vendor-neutral intelligence layer for optical/energy-aware networks. It is entirely self-contained: no external databases, message brokers, or services are required. All persistence uses stdlib SQLite.

### Environment variables

- `WAVEOS_LICENSE_KEY` must be set or the pipeline exits with code 3. For dev/CI use `WAVEOS-CI-20991231-TEST`.
- `PATH` must include `~/.local/bin` (where `pip install --user` places scripts like `waveos`, `pytest`, `ruff`).
- Both are already configured in `~/.bashrc`.

### Common commands

See `Makefile` for standard targets:

| Task | Command |
|------|---------|
| Lint | `make lint` (runs `ruff check` + `ruff format --check`) |
| Test | `make test` (runs `pytest -q`) |
| Coverage | `make coverage` (fail-under 45%) |

### Running the pipeline (hello world)

```bash
waveos sim --out demo_data
waveos baseline --in demo_data/baseline
waveos run --in demo_data/run --baseline demo_data/baseline --out out
waveos report --in out --open   # optional: re-render + open report
```

### Non-obvious caveats

- **Lint has pre-existing warnings**: `ruff check` reports ~1472 issues (mostly import sorting and deprecated `typing` aliases). These are known; `ruff format --check` also shows many files needing reformatting. The test suite passes cleanly regardless.
- **No Docker needed for dev**: Docker is only needed for production image builds (`make docker-build`/`make docker-smoke`), not for local development or testing.
- **Optional extras** (`[mqtt]`, `[ocpp]`, `[modbus]`, `[secrets]`, `[alerts]`, `[otel]`, `[encryption]`) are only needed for specific hardware/cloud integrations, not for the core dev workflow.

### Secure release platform modules

The secure release platform adds these subsystems (all self-contained, no new deps):

| Module | Path | Purpose |
|--------|------|---------|
| Bundle V2 | `src/waveos/bundle_v2.py` | Enhanced manifest with targets, services, bridge, rollback, policy gates |
| Attestation | `src/waveos/attestation.py` | Build provenance (commit, CI, builder identity) |
| SBOM | `src/waveos/sbom.py` | CycloneDX generation + blocklist/allowlist verification |
| Agent | `src/waveos/agent/` | State machine, side-by-side install, activate, rollback, evidence packs |
| Compat | `src/waveos/compat/` | Preflight checks (OS/arch/libs/disk) + runtime strategies |
| Registry | `src/waveos/registry/` | File-system bundle registry + networked transport (mTLS server, client, mirror sync, device auth) |
| Bridge | `src/waveos/bridge/` | Legacy bridge orchestrator (mirror/canary/cutover) |
| Crypto | `src/waveos/crypto/` | Public-key signing (Ed25519/HMAC-SHA512), LocalKMS, anti-rollback epochs |
| Rollout | `src/waveos/rollout_controls.py` | Channel policies, health gates, auto-rollback triggers |
| Transfer | `src/waveos/transfer/` | Gateway adaptors (DMZ scan/approve/publish), diode sync, hash-chained audit trail |

CLI commands: `waveos bundle inspect/verify/sign`, `waveos attest generate`, `waveos sbom generate/verify`, `waveos agent-v2 install/status/activate/rollback/logs/update`, `waveos compat check`, `waveos registry publish/list/get`.

Documentation: `docs/BUNDLE_SPEC.md`, `docs/AGENT_STATE_MACHINE.md`, `docs/DEPENDENCY_STRATEGIES.md`, `docs/BRIDGE_PATTERNS.md`, `docs/CONTROLLED_TRANSFER_INTEGRATION.md`, `docs/AUDIT_MODEL.md`. Schema: `schemas/bundle_manifest.schema.json`.
