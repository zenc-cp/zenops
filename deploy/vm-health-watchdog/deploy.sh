#!/usr/bin/env bash
# Deploy vm-health-watchdog to the local machine (run on nanoclaw-az as root).
# Usage: sudo bash deploy.sh <WEBHOOK_URL>
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: sudo bash deploy.sh <WEBHOOK_URL>" >&2
  exit 1
fi
WEBHOOK_URL="$1"

install -d -o root -g root -m 0755 /opt/vm-health-watchdog
install -o root -g root -m 0755 vm_health_check.py /opt/vm-health-watchdog/vm_health_check.py

# env file: readable by azureuser (service user), not world
umask 027
cat > /etc/vm-health-watchdog.env <<EOF
WEBHOOK_URL=${WEBHOOK_URL}
EOF
chown root:azureuser /etc/vm-health-watchdog.env
chmod 0640 /etc/vm-health-watchdog.env

install -o root -g root -m 0644 vm-health-watchdog.service /etc/systemd/system/vm-health-watchdog.service
install -o root -g root -m 0644 vm-health-watchdog.timer   /etc/systemd/system/vm-health-watchdog.timer

systemctl daemon-reload
systemctl enable --now vm-health-watchdog.timer

# one-shot run to surface any immediate config error
systemctl start vm-health-watchdog.service || true
sleep 2
systemctl --no-pager status vm-health-watchdog.service | head -20
echo
echo "Next runs:"
systemctl list-timers vm-health-watchdog.timer --no-pager