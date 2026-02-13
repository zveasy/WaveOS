# Recovery Integration Kit (DoD / Hardware Supervisor)

WaveOS recovery and watchdog hooks are implemented in `src/waveos/recovery.py`. To be **DoD deployment-ready**, these must be wired to the **actual device supervisor** on target hardware. This document describes the API contract and integration steps.

## Overview

- **RecoveryOrchestrator** turns ERROR/WARN events into recovery actions (restart_service, degrade_features) and optionally runs configurable commands.
- **watchdog_ping(path)** writes a timestamp to a file so an external watchdog can confirm the control plane is alive.
- **Operator approval** can be required before any recovery command runs (see [Change Management](CHANGE_MANAGEMENT.md)).

## Hardware Supervisor Contract

Integrate with your device supervisor as follows.

### 1. Watchdog

- WaveOS writes a timestamp to `watchdog_path` (default `out/watchdog.txt`) at each run when `watchdog_enabled=true`.
- The **device supervisor** must:
  - Monitor this file (or a shared path you configure).
  - If the timestamp is not updated within the required interval (e.g. 2× pipeline interval), treat the control plane as unhealthy and trigger your **reset/recovery procedure** (e.g. restart WaveOS, reboot node, or failover).
- **Reset-reason capture:** After any supervisor-triggered reset, record the reason (watchdog timeout, panic, etc.) in a well-known location (e.g. `/var/run/waveos-reset-reason`) so WaveOS or operators can log it for compliance.

### 2. Recovery commands

When `recovery_enabled=true`, WaveOS can run:

- **restart_command** — e.g. `systemctl restart waveos` or a script that notifies the supervisor to restart the service.
- **degrade_command** — e.g. reduce features or put the node in a safe mode.
- **reboot_command** — e.g. `sudo reboot` or a script that asks the supervisor to reboot the device.

**Recommended:** Do not pass raw `reboot` to WaveOS config. Instead, point to a **supervisor-owned script** that:

1. Logs the request (reason, timestamp).
2. Calls the supervisor API (or systemd, or hardware watchdog) to perform the actual reboot.
3. Ensures reset-reason is set before rebooting.

Example (conceptual):

```bash
# /opt/waveos/bin/supervisor-reboot.sh
echo "waveos_recovery_$(date -Iseconds)" > /var/run/waveos-reset-reason
curl -X POST http://localhost:9999/supervisor/reboot   # your supervisor
```

Configure:

```toml
recovery_reboot_command = "/opt/waveos/bin/supervisor-reboot.sh"
```

### 3. Operator approval (DoD)

When `recovery_require_approval=true` (default when recovery is enabled in DoD mode):

- WaveOS writes proposed recovery actions to `recovery_actions.jsonl` but **does not run** restart/degrade/reboot commands until approval is granted.
- Approval is granted by placing a file at `recovery_approval_path` (e.g. `out/recovery_approved`) with content `approved` (or via env `WAVEOS_RECOVERY_APPROVED=true` for that run).
- See [Change Management](CHANGE_MANAGEMENT.md) for the formal operator sign-off process.

## Configuration

| Config / Env | Description |
|--------------|-------------|
| `recovery_enabled` / `WAVEOS_RECOVERY_ENABLED` | Enable recovery actions (default: false). |
| `recovery_require_approval` / `WAVEOS_RECOVERY_REQUIRE_APPROVAL` | If true, do not run recovery commands unless approval file/env is present. |
| `recovery_approval_path` / `WAVEOS_RECOVERY_APPROVAL_PATH` | Path to file that must contain `approved` to allow commands (e.g. `out/recovery_approved`). |
| `recovery_restart_command` | Command to run for ERROR → restart_service. |
| `recovery_degrade_command` | Command to run for WARN → degrade_features. |
| `recovery_reboot_command` | Command to run for full reboot (prefer supervisor script). |
| `watchdog_enabled` / `WAVEOS_WATCHDOG_ENABLED` | Write watchdog timestamp each run. |
| `watchdog_path` / `WAVEOS_WATCHDOG_PATH` | File path for watchdog ping (supervisor monitors this). |

## Validation Checklist

Before production/DoD:

1. [ ] Supervisor monitors `watchdog_path` and triggers if no update within threshold.
2. [ ] Reset-reason is captured after any supervisor-triggered reset and retained for audit.
3. [ ] Recovery commands point to supervisor-owned scripts (or equivalent) that perform the real action and log it.
4. [ ] Operator approval process is documented and used when `recovery_require_approval=true`.
5. [ ] One documented drill: trigger watchdog timeout (or simulated recovery), verify reset-reason and logs; retain for [FIELD_DRILL_REPORT](templates/FIELD_DRILL_REPORT.md).
