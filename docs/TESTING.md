# How to Test WaveOS

## Quick start

```bash
# Install with dev deps (pytest, coverage, ruff)
pip install -e .[dev]

# Run all tests (conftest sets WAVEOS_LICENSE_KEY for CLI tests)
pytest -q

# With coverage (fail-under 45%)
make coverage
# or
pytest --cov=src/waveos --cov-report=term-missing --cov-report=xml
coverage report --fail-under=45

# Verbose
pytest -v
```

No need to set `WAVEOS_LICENSE_KEY` locally: `tests/conftest.py` sets a CI/test key if none is present.

---

## Test suites

| What | Command |
|------|--------|
| **All tests** | `pytest -q` or `make test` |
| **With coverage** | `make coverage` |
| **Single file** | `pytest tests/test_licensing.py -v` |
| **By keyword** | `pytest -k "license or rbac" -v` |
| **Exclude slow/e2e** | `pytest tests/ --ignore=tests/e2e` |

### By area

- **Pipeline (sim → baseline → run → report):** `pytest tests/test_pipeline_integration.py tests/test_pipeline_outputs.py -v`
- **Fault injection / scoring:** `pytest tests/test_fault_injection.py tests/test_scoring.py -v`
- **RBAC / auth:** `pytest tests/test_rbac.py -v`
- **Licensing (incl. expiry, tier):** `pytest tests/test_licensing.py -v`
- **V1 acceptance (bundle install/rollback, evidence, supervisor):** `pytest tests/test_v1_acceptance.py -v`
- **V2 (device API, gates, list-devices):** `pytest tests/test_v2_device_api.py -v`
- **V3 (compatibility, orchestration, GitOps, shadow, compliance, quotas, etc.):** `pytest tests/test_v3.py -v`
- **CLI validation / run/report:** `pytest tests/test_cli_validation.py tests/test_cli_e2e.py -v`
- **Config, drift, audit:** `pytest tests/test_config_drift_detection.py tests/test_audit_config_drift.py -v`
- **Secrets, alerting, cleanup:** `pytest tests/test_secrets.py tests/test_alerting_webhook.py tests/test_cleanup.py -v`

---

## Manual / smoke tests

### Full pipeline (no pytest)

```bash
export WAVEOS_LICENSE_KEY=WAVEOS-CI-20991231-TEST   # or WAVEOS_LICENSE_SKIP=1 for dev

waveos sim --in ./demo_data/sim --out ./demo_data/run --links 5 --samples 100
waveos baseline --in ./demo_data/run --out ./demo_data/baseline
waveos run --in ./demo_data/run --baseline ./demo_data/baseline --out ./out
waveos report --in ./out --open
```

Check `./out` for `run_meta.json`, `health_summary.json`, `report.html`, and the evidence zip.

### Health and config

```bash
waveos health-check
waveos validate-config
waveos -V
```

### Bundle (install, canary, promote, rollback)

```bash
waveos bundle build --dir ./some_bundle --policy-version p1 --bundle-id b1
waveos bundle install --dir ./some_bundle
# Canary: install to canary dir then promote
waveos bundle install --dir ./some_bundle --canary-percent 10 --canary-dir ./out/bundles/canary
waveos bundle promote --canary-dir ./out/bundles/canary
waveos bundle rollback
```

### Docker smoke

```bash
make docker-build
make docker-smoke
# or
docker run --rm -e WAVEOS_LICENSE_KEY=WAVEOS-CI-20991231-TEST waveos:latest health-check
docker run --rm -e WAVEOS_LICENSE_KEY=WAVEOS-CI-20991231-TEST waveos:latest sh -c "waveos sim ... ; waveos baseline ... ; waveos run ... ; test -f /data/out/report.html"
```

---

## Testing specific features

### License expiry and tier

- **Expired key:** `WAVEOS_LICENSE_KEY=WAVEOS-PROD-20200101 waveos health-check` → should exit 3 with “expired”.
- **Tier:** In Python, `from waveos.licensing import get_license_tier`; set `WAVEOS_LICENSE_KEY=WAVEOS-ENTERPRISE-X-20991231` and call `get_license_tier()` → `"enterprise"`.

### Encryption at rest

- Install optional dep: `pip install waveos[encryption]` (adds `cryptography`).
- Set `WAVEOS_ENCRYPTION_KEY` to a Fernet key (e.g. from `cryptography.fernet.Fernet.generate_key().decode()`).
- Set config `encrypt_artifacts=true` (or env `WAVEOS_ENCRYPT_ARTIFACTS=true`) and run a pipeline; check that `run_meta.json.enc` exists and `run_meta.json` is absent when encryption is used.

### Ingestion token (collector auth)

- Set config `require_ingestion_token=true` and `ingestion_token_path` to a path (or use default `out/ingestion.token`).
- Set `WAVEOS_INGESTION_TOKEN` to a secret value; write the same value to the token file.
- Run `waveos run ...` → should succeed.
- Change the token file content or remove it → run should fail with ingestion auth error.

### Compliance report (signed, retention)

- In Python: `from waveos.compliance import generate_report, write_report; r = generate_report("NERC", ...); write_report(r, path, sign_key="my-secret", retention_days=90)`.
- Open the JSON report and confirm `signed_at`, `signature`, and `retention_days` are present.

### Canary and offline cache

- **Canary:** `waveos bundle install --dir <bundle> --canary-percent 10 --canary-dir ./out/bundles/canary` → bundle lands in canary dir; active unchanged. Then `waveos bundle promote --canary-dir ./out/bundles/canary` → active updated.
- **From cache:** Copy a bundle dir into a cache directory, then `waveos bundle install --from-cache <cache_dir> --bundle-id <id>` (no `--dir`).

---

## CI

GitHub Actions (`.github/workflows/ci.yml`) on push/PR:

- Lint (Ruff check + format)
- Full pytest + coverage (fail-under 45%)
- pip-audit
- Build package, SBOM, cosign signing
- Docker build and smoke (health-check + pipeline)

CI sets `WAVEOS_LICENSE_KEY=WAVEOS-CI-20991231-TEST` so all tests pass without manual license setup.

---

## Coverage targets

- **Overall:** ≥ 45% (enforced in CI and `make coverage`).
- **Goal:** Unit tests ≥ 80%; integration tests cover baseline/run/report outputs (see pipeline and V1 acceptance tests).

Coverage config: `pyproject.toml` under `[tool.coverage.*]`, and `pytest.ini` for pytest options.
