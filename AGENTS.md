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

- **Lint has pre-existing warnings**: `ruff check` reports ~1067 issues (mostly import sorting and deprecated `typing` aliases). These are known; `ruff format --check` also shows ~79 files needing reformatting. The test suite passes cleanly regardless.
- **No Docker needed for dev**: Docker is only needed for production image builds (`make docker-build`/`make docker-smoke`), not for local development or testing.
- **Optional extras** (`[mqtt]`, `[ocpp]`, `[modbus]`, `[secrets]`, `[alerts]`, `[otel]`, `[encryption]`) are only needed for specific hardware/cloud integrations, not for the core dev workflow.
