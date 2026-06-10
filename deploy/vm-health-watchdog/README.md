# vm-health-watchdog

Replaces Scout automation `s7zwne60mq6pedls` (zenops-watchdog). Runs entirely on
nanoclaw-az: probes every 10 min, silent on success, posts to a Teams
incoming-webhook on failure. Zero laptop dependency.

## Architecture

```
systemd timer (10 min) ──► vm_health_check.py
                              │
                              ├── probe systemd: hermes, azure-auth-shim, design-e
                              ├── probe HTTP:    shim /v1/models, design-e /rpc/v1/health
                              │
                              ├─ all ok ──► exit 0  (silent, journal only)
                              └─ any fail ─► POST Teams webhook ──► Zen's self-chat
```

Probes are pure functions; webhook delivery is one urllib call. No Python deps
beyond stdlib.

## Tests

`pytest test_vm_health_check.py` — 11 vertical-slice unit tests (decide,
format_alert, probe_http x3, probe_systemd_active x2, main x3). All green.

## Deploy

1. Create a Teams **Workflows webhook** (Teams → Apps → Workflows → "Post to a
   channel when a webhook request is received" template → choose your self-chat
   or a Scout channel → copy the URL).
2. SSH to nanoclaw-az and run `bash deploy.sh <webhook-url>`.
3. Verify: `systemctl list-timers vm-health-watchdog.timer` shows next run;
   `journalctl -u vm-health-watchdog.service --since '15 min ago'` shows the
   silent-path log lines.
4. **Cutover**: delete or disable Scout automation `s7zwne60mq6pedls` (the
   factory-shim that currently no-ops every 10 min on the laptop).

## Failure-mode simulation

```
sudo systemctl stop azure-auth-shim
sudo systemctl start vm-health-watchdog.service
journalctl -u vm-health-watchdog.service --since '1 min ago'
# expect: alert posted; check Teams chat for "⚠️ VM health alert"
sudo systemctl start azure-auth-shim
```
