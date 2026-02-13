# Runbooks

Operational procedures for running and supporting Wave OS in production. See also [Production Checklist](PRODUCTION_CHECKLIST.md) and [Deployment](DEPLOYMENT.md).

---

## Startup

1. **Validate environment**
   - Set `WAVEOS_LICENSE_KEY` or `WAVEOS_LICENSE_PATH` (required in production).
   - Optionally set `WAVEOS_CONFIG` to a config file path.
   - Run: `waveos validate-config` (optionally `--config /path/to/config.toml`).
   - Exit 0 = config valid; exit 2 = config invalid (fix before proceeding).

2. **Verify readiness**
   - Run: `waveos health-check`.
   - Expected output: `ok (license and config valid)` or `ok (license valid)`.
   - Exit 0 = process is ready to run the pipeline or serve probes.

3. **Ensure output directories are writable**
   - For `run`: output dir will be created; ensure parent is writable.
   - For audit/logs: ensure `WAVEOS_AUDIT_LOG_PATH` and log spool path parent dirs exist and are writable.

4. **Run the pipeline**
   - Generate data (or use existing): `waveos sim --out ./data` (or ingest real telemetry).
   - Build baseline: `waveos baseline --in ./data/baseline`.
   - Score run: `waveos run --in ./data/run --baseline ./data/baseline --out ./out`.

---

## Shutdown

1. **Send SIGTERM** to the Wave OS process (e.g. from Kubernetes or systemd).
2. **Allow a short grace period** (e.g. 10–30 seconds) so the process can:
   - Flush logs and spooler.
   - Finish in-flight writes (atomic writes use temp files and rename).
3. **Confirm** logs show "Graceful shutdown requested" or similar (from installed signal handler).
4. If the process does not exit within the grace period, orchestrators may send SIGKILL.

---

## Health and readiness probes (Kubernetes)

- **Command:** `waveos health-check`
- **When to use:** As `livenessProbe` and `readinessProbe` with `exec` (see [Deployment](DEPLOYMENT.md#health-and-readiness-k8s)).
- **Interpretation:** Exit 0 = healthy/ready; non-zero = license or config invalid (exit 3) or other failure.
- **Frequency:** Typical: liveness 30s period, readiness 10s period; adjust for your cluster.

---

## Failure recovery

| Symptom | Action |
|--------|--------|
| **Normalization fails** | Inspect input schema; check validation errors in logs. Run `waveos validate-telemetry --in <file> --profile <profile>` to validate inputs. |
| **Scoring fails** | Ensure `baseline.json` exists in baseline dir and matches run entities. Check for missing baseline stats (logs: "Missing baseline for link ..."). |
| **Report fails** | Run `waveos report --in <out_dir>` only after a successful `waveos run`. If files are missing, CLI exits 1 with a clear message; run the pipeline first. |
| **License error (exit 3)** | Set `WAVEOS_LICENSE_KEY` or `WAVEOS_LICENSE_PATH`; do not use `WAVEOS_LICENSE_SKIP` in production. |
| **Config error (exit 2)** | Fix config file or env; run `waveos validate-config` to verify. |
| **Alert routing failed** | Check logs for exception type (URLs/secrets are not logged). Verify webhook/Slack/email settings and network reachability. |

---

## Troubleshooting

- **Missing outputs:** Confirm output directory permissions and disk space. Ensure `waveos run` completed successfully (exit 0).
- **Metrics endpoint not reachable:** Set `WAVEOS_METRICS_PORT` (e.g. 9109) and ensure the port is open and not blocked by firewall.
- **Logging format unexpected:** Set `WAVEOS_LOG_FORMAT=json` or `text`; default is `json`.
- **Dependency audit failures:** Run `pip-audit`; update dependencies and `.pip-audit.toml` if needed.
- **Version check:** Run `waveos -V` or `waveos --version` to confirm installed version (e.g. for support or compatibility).

---

## Incident response

1. **Capture** logs and pipeline outputs (e.g. `out/`, audit log, run_meta.json).
2. **Identify** affected components and data inputs (baseline vs run, config fingerprint).
3. **Escalate** to engineering with repro steps, version (`waveos -V`), and relevant config (no secrets).

---

## On-call escalation

| Severity | Definition | Action |
|----------|------------|--------|
| **SEV-1** | Data loss, pipeline failure, or security incident | Page primary + lead. |
| **SEV-2** | Partial failure or degraded output quality | Page primary. |
| **SEV-3** | Non-blocking issues | File ticket; include logs and version. |
