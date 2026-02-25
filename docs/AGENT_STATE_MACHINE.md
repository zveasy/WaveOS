# WaveOS Agent State Machine

## Overview

The WaveOS agent runs on target devices and manages the full deployment lifecycle. It uses a finite state machine to ensure safe, auditable transitions.

## States

| State | Description |
|-------|-------------|
| `IDLE` | No active operation. Awaiting commands or scheduled checks. |
| `CHECK_UPDATE` | Checking registry/mirror for available updates. |
| `DOWNLOAD` | Downloading/importing bundle from registry or transfer path. |
| `VERIFY` | Verifying bundle signature and checksums. |
| `PREFLIGHT` | Running compatibility checks (OS, arch, libs, disk). |
| `INSTALL` | Installing bundle side-by-side (`/opt/waveos/apps/<app>/<ver>/`). |
| `ACTIVATE` | Activating the new version (symlink swap, service restart). |
| `MONITOR` | Monitoring health post-activation. |
| `ROLLBACK` | Rolling back to previous version. |
| `QUARANTINE` | Bundle failed verification or caused issues; isolated. |

## Valid Transitions

```
IDLE → CHECK_UPDATE, MONITOR
CHECK_UPDATE → DOWNLOAD, IDLE
DOWNLOAD → VERIFY, IDLE, QUARANTINE
VERIFY → PREFLIGHT, QUARANTINE, IDLE
PREFLIGHT → INSTALL, IDLE, QUARANTINE
INSTALL → ACTIVATE, ROLLBACK, QUARANTINE
ACTIVATE → MONITOR, ROLLBACK, QUARANTINE
MONITOR → IDLE, ROLLBACK, CHECK_UPDATE, QUARANTINE
ROLLBACK → IDLE, QUARANTINE
QUARANTINE → IDLE
```

## Event Log Schema

Each state transition produces a structured event:

```json
{
  "timestamp": "2025-01-15T10:30:00Z",
  "from_state": "VERIFY",
  "to_state": "PREFLIGHT",
  "reason": "Verification passed, running preflight",
  "details": {}
}
```

## CLI Commands

```bash
waveos agent-v2 install --base-dir out/agent
waveos agent-v2 status
waveos agent-v2 activate <bundle_dir> --bundle-id <id>
waveos agent-v2 rollback
waveos agent-v2 logs
waveos agent-v2 update --channel prod
```
