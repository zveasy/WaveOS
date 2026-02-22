# Weak Implementations Audit

This document lists **weak or risky implementations** found across the WaveOS repo. Each item includes location, risk, and suggested hardening. Use it for prioritised remediation and security review.

**Implemented:** The fixes described below have been applied in the codebase (recovery, HTTP collector, alerts SSRF, secrets fallback, exception narrowing, path validation, normalize cap, config size, resource limits). Items marked **FIXED** in a section header have been fully addressed.

---

## 1. Security-sensitive

### 1.1 Recovery command execution with `shell=True` (command injection) — **FIXED**

| Where | `src/waveos/recovery.py` — `_run_command()` |
| Risk | If `restart_command` / `degrade_command` / `reboot_command` come from untrusted config or env, an attacker could inject shell metacharacters. |
| Fix | Commands are validated for unsafe shell metacharacters (`;|&$()<>\\\n\r\t`). Execution uses `shlex.split(command)` and `subprocess.run(..., shell=False, timeout=60)`. |

### 1.2 HTTP collector: no response size limit (DoS / OOM) — **FIXED**

| Where | `src/waveos/collectors/http.py` — `load_records_from_url()` |
| Risk | `resp.read()` reads the entire response into memory. A very large or slow response can cause OOM or long blocks. |
| Fix | Response is read in chunks (64 KB). Total size is capped at `max_response_bytes` (default 50 MB). Truncation is logged. |

### 1.3 Alert webhook URL: no SSRF protection — **FIXED**

| Where | `src/waveos/utils/alerts.py` — `send_webhook(url, ...)` |
| Risk | If the webhook URL is misconfigured or attacker-controlled, `urllib` could be used to hit internal services. |
| Fix | `_validate_webhook_url()` enforces scheme `https` only and rejects private/loopback/reserved IPs. |

### 1.4 Secrets fallback to env JSON in production — **FIXED**

| Where | `src/waveos/utils/secrets.py` — `get_secret_from_vault`, `get_secret_from_aws`, `get_secret_from_gcp` |
| Risk | When the provider library is missing or config is incomplete, code falls back to `_load_env_json("WAVEOS_VAULT_SECRETS_JSON")` (and AWS/GCP equivalents). Those env vars can contain raw secrets; if env is ever logged or dumped, secrets leak. Docs say “dev only” but code does not prevent use in production. |
| Recommendation | (1) In production (e.g. when `WAVEOS_LICENSE_SKIP` is not set), avoid falling back to `*_SECRETS_JSON`; instead fail or return None and log a clear error. (2) Or add a config flag to disable JSON fallback. |

---

## 2. Robustness and error handling

### 2.1 Broad `except Exception` that hide failures

| Where | Multiple files (see table below) |
| Risk | Catching `Exception` and returning None/continuing can hide bugs (e.g. `KeyboardInterrupt`, `SystemExit`) or make debugging hard when the real error is not logged. |
| Recommendation | Prefer catching specific exceptions (e.g. `OSError`, `ValueError`, `json.JSONDecodeError`). If catching `Exception`, at least log `logger.debug(... exc_info=True)` or re-raise after logging. |

| File | Line / context | Suggestion |
|------|----------------|-----------|
| `recovery.py` | 30 — `_recovery_approved` read approval file | Catch `OSError`; log and return False on error. |
| `bundle.py` | 132, 147, 166, 178 — various verify/encrypt/decrypt helpers | Catch specific errors (e.g. `ValueError`, crypto errors); log and return False. |
| `reporting/report.py` | 49 — encrypted write fallback | Catch specific exception (e.g. import or encryption error); log. |
| `utils/encryption.py` | 41, 54 — read/write encrypted | Same: narrow exception and log. |
| `node_health.py` | 35 — heartbeat timestamp parse | Catch `ValueError` (or similar) for parse errors; log. |
| `heartbeat.py` | 48 — read JSONL line | Catch `json.JSONDecodeError`; optionally log and continue. |
| `collectors/file.py` | 39 — after retry failure | Re-raise after `record_failure()` (already does); consider logging. |
| `cli.py` | 544 — list-devices driver iteration | Log the exception (e.g. `logger.debug`) so failures are visible; avoid bare `pass`. |
| `update_agent.py` | 137 — loop over cache dirs | Log which path failed and why before `continue`. |
| `plugins/registry.py` | 89 — discover_entry_points | Log and skip; already logs at 96 for load(). |

### 2.2 Normalize pipeline: full materialisation of records (memory) — **FIXED**

| Where | `src/waveos/normalize/pipeline.py` — `normalize_records()` |
| Risk | `records_list = list(records)` materialises the full input. A huge telemetry stream can cause high memory use or OOM. |
| Fix | Optional `max_records` (from config `WAVEOS_MAX_TELEMETRY_RECORDS`). When set, input count is checked after materialisation; if exceeded, `ValueError` with a clear message. CLI passes `config.max_telemetry_records`. |

### 2.3 Cleanup command: no path restriction — **FIXED**

| Where | `src/waveos/cli.py` — `cmd_cleanup` (e.g. `--path`) |
| Risk | `base = Path(args.path)` then `base.rglob("*")` deletes old files under that path. If an operator passes `/` or a critical directory, data loss is possible. |
| Fix | Path is resolved; it must be under `WAVEOS_CLEANUP_ALLOWED_BASE` (default: current working directory). Otherwise exit 2 with a clear message. |

### 2.4 Bundle install: target dir not validated — **FIXED**

| Where | `src/waveos/update_agent.py` — `_install_to_dir(..., target_dir)` |
| Risk | `shutil.rmtree(target_dir)` then `shutil.copytree(...)`: if `target_dir` is set to `/etc` or `/usr`, the system could be corrupted. |
| Fix | `allowed_install_root` (parent of active_dir) is passed in; target_dir must resolve under it. Otherwise `ValueError` is raised. |

---

## 3. Subprocess and external calls

### 3.1 Thermal actuator command (single executable)

| Where | `src/waveos/actuators/sdn_thermal.py` — `_run_thermal_cmd()` |
| Current | `subprocess.run([self._thermal_cmd], input=..., timeout=10)` — no shell. The entire `WAVEOS_ACTUATOR_THERMAL_CMD` is used as the executable name (single argument). |
| Risk | Low: not shell-invoked. If the env var is set to a path like `/usr/bin/my-thermal-helper`, it’s safe. Only risk is setting it to a path that points to a malicious binary. |
| Recommendation | Document that `WAVEOS_ACTUATOR_THERMAL_CMD` must be a trusted executable path. Optionally validate that it is an absolute path under a configured prefix. |

### 3.2 Supervisor utility

| Where | `src/waveos/utils/supervisor.py` |
| Current | `subprocess.run(command, check=False)` — `command` is a list (no shell). |
| Risk | Low if callers always pass a list. Verify all call sites pass a list, not a string. |

---

## 4. Input and config

### 4.1 Config file size — **FIXED**

| Where | `src/waveos/utils/config.py` — `_load_file()` |
| Risk | `path.read_text(encoding="utf-8")` loads the whole file. An enormous config could use a lot of memory. |
| Fix | `MAX_CONFIG_FILE_BYTES = 1 * 1024 * 1024`. Before reading, `path.stat().st_size` is checked; if exceeded, `ValueError` is raised. |

### 4.2 CSV/JSONL file size (collectors / validation)

| Where | `src/waveos/utils/io.py` — `read_jsonl`, `read_csv`; `validation.py` — `validate_file` |
| Risk | Entire file is read into memory. Very large files can cause OOM. |
| Recommendation | Document recommended max file sizes; consider streaming or chunked validation for very large files, or a hard limit with a clear error. |

---

## 5. Logic and edge cases

### 5.1 Metrics CSV with no rows

| Where | `src/waveos/reporting/report.py` — `write_outputs()` |
| Current | `if rows: write_csv(metrics_path, rows, fieldnames=list(rows[0].keys()))` — safe: only writes when `rows` is non-empty. |
| Status | No change needed; logic is correct. |

### 5.2 Resource limits applied unconditionally — **FIXED**

| Where | `src/waveos/utils/resource_limits.py` — `apply_resource_limits()` |
| Risk | On some platforms, `setrlimit(RLIMIT_AS, ...)` can fail or behave differently. Failure is not caught and could crash startup. |
| Fix | Each `setrlimit` call is wrapped in try/except (ValueError, OSError); on failure a warning is logged and that limit is skipped. |

### 5.3 License path: symlink or sensitive file

| Where | `src/waveos/licensing.py` — `_read_license_from_path()` |
| Risk | If `WAVEOS_LICENSE_PATH` is set to a symlink or sensitive file, content is read. Path is admin-controlled. |
| Recommendation | Document that the path must point to a dedicated license file. Optional: resolve realpath and check it’s under a permitted directory. |

---

## 6. Summary table

| Priority | Category | Item | File(s) |
|----------|----------|------|---------|
| High | Security | Recovery `shell=True` (injection) | `recovery.py` |
| High | Security | HTTP response size limit | `collectors/http.py` |
| Medium | Security | Webhook SSRF | `utils/alerts.py` |
| Medium | Security | Secrets JSON fallback in prod | `utils/secrets.py` |
| Medium | Robustness | Path validation for cleanup | `cli.py` |
| Medium | Robustness | Bundle install target validation | `update_agent.py` |
| Low | Robustness | Narrow exception handling | Multiple (see 2.1) |
| Low | Robustness | Normalize memory / record limit | `normalize/pipeline.py` |
| Low | Robustness | Resource limit failure handling | `cli.py`, `resource_limits.py` |
| Low | Docs/config | Config/file size limits | `config.py`, `io.py` |

---

## 7. What is already in good shape

- **Actuator thermal command:** Uses list form of `subprocess.run` (no shell).
- **Alert failure logging:** Only exception type is logged (no URLs/tokens).
- **Pydantic models:** Bounds and types for telemetry and health scores.
- **Atomic writes:** JSON/JSONL use temp file + rename.
- **RBAC and audit:** Auth decisions and actions logged.
- **Encryption at rest:** Optional; Fernet with key from secrets.
- **mTLS and ingestion token:** Config and docs present; “bring your own gateway” story.

Use this audit alongside [THREAT_MODEL.md](THREAT_MODEL.md) and [PRODUCTION_CHECKLIST.md](PRODUCTION_CHECKLIST.md) for deployment and security sign-off.
