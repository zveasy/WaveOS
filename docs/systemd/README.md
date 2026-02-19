# WaveOS systemd examples

Use these as templates for running WaveOS and the watchdog monitor on an edge node.

- **waveos.service.example** — Single-shot run (invoked by a timer or wrapper).
- **waveos-watchdog.service.example** — Checks that the watchdog file is updated; if stale, writes reset reason and restarts the WaveOS service.
- **waveos-watchdog.timer.example** — Timer that runs the pipeline periodically (e.g. every 60s).

You also need a **timer** that starts `waveos.service` on an interval (e.g. every 60 seconds), so that `waveos run` runs repeatedly and updates the watchdog file. The watchdog monitor then runs (e.g. every 120s) and restarts the WaveOS service if the file is stale.

See [RECOVERY_INTEGRATION_KIT.md](../RECOVERY_INTEGRATION_KIT.md) for the full supervisor contract.
