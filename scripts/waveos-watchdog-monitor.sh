#!/usr/bin/env bash
# WaveOS Watchdog Monitor — run as a systemd service or cron job.
# If the watchdog file is older than STALE_SECONDS, write reset reason and restart the WaveOS service.
# Requires: WAVEOS_WATCHDOG_PATH (or --watchdog-path), optional WAVEOS_SERVICE_NAME, WAVEOS_RESET_REASON_PATH.

set -euo pipefail

WATCHDOG_PATH="${WAVEOS_WATCHDOG_PATH:-out/watchdog.txt}"
STALE_SECONDS="${WAVEOS_WATCHDOG_STALE_SECONDS:-120}"
SERVICE_NAME="${WAVEOS_SERVICE_NAME:-waveos}"
RESET_REASON_PATH="${WAVEOS_RESET_REASON_PATH:-/var/run/waveos-reset-reason}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --watchdog-path) WATCHDOG_PATH="$2"; shift 2 ;;
    --stale-seconds) STALE_SECONDS="$2"; shift 2 ;;
    --service)       SERVICE_NAME="$2"; shift 2 ;;
    --reset-reason)  RESET_REASON_PATH="$2"; shift 2 ;;
    *) break ;;
  esac
done

if [[ ! -f "$WATCHDOG_PATH" ]]; then
  echo "Watchdog file missing: $WATCHDOG_PATH (WaveOS may not have run yet)"
  exit 0
fi

NOW=$(date +%s)
MTIME=$(stat -c %Y "$WATCHDOG_PATH" 2>/dev/null || stat -f %m "$WATCHDOG_PATH" 2>/dev/null)
AGE=$((NOW - MTIME))

if [[ $AGE -gt $STALE_SECONDS ]]; then
  echo "WaveOS watchdog stale (${AGE}s > ${STALE_SECONDS}s). Writing reset reason and restarting."
  echo "watchdog_timeout $(date -Iseconds)" | tee "$RESET_REASON_PATH" 2>/dev/null || true
  systemctl restart "$SERVICE_NAME" 2>/dev/null || true
  exit 1
fi

exit 0
