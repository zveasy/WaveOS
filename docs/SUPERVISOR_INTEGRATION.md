# Supervisor Integration

## Watchdog
- Set `watchdog_enabled=true`
- Set `watchdog_path=/var/run/waveos.watchdog`
- Configure the device supervisor to monitor the watchdog file and trigger recovery on stale updates.

## Recovery Commands
Use recovery command hooks to integrate with the platform supervisor:
- `WAVEOS_RECOVERY_RESTART_COMMAND="/usr/local/bin/restart-service"`
- `WAVEOS_RECOVERY_DEGRADE_COMMAND="/usr/local/bin/degrade-mode"`
- `WAVEOS_RECOVERY_REBOOT_COMMAND="/sbin/reboot"`

## Example (systemd)
```
[Service]
ExecStart=/usr/local/bin/waveos schedule --in /data/run --baseline /data/base --out /var/lib/waveos/out --every 60 --count 0
Restart=always
```
