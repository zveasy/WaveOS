# Field Drills

## Drill 1: Alert Path Validation
1. Trigger a WARN condition (e.g., overcurrent in telemetry).
2. Confirm alert delivery to webhook/Slack/email.
3. Capture evidence pack and audit log.

## Drill 2: Rollback Exercise
1. Install a new bundle.
2. Force a failure in telemetry processing.
3. Run `waveos bundle rollback`.
4. Verify report and audit logs.

## Drill 3: Watchdog/Recovery
1. Stop the WaveOS process.
2. Confirm supervisor detects watchdog staleness.
3. Restart WaveOS and verify recovery actions logged.
