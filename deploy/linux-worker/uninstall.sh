#!/usr/bin/env bash
set -Eeuo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Run with sudo." >&2
  exit 1
fi

systemctl disable --now securewise-worker.service 2>/dev/null || true
systemctl stop securewise-worker-connectivity-check.service 2>/dev/null || true
rm -f /etc/systemd/system/securewise-worker.service
rm -f /etc/systemd/system/securewise-worker-connectivity-check.service
systemctl daemon-reload
systemctl reset-failed securewise-worker.service 2>/dev/null || true
echo "Worker service definitions removed. Code, virtualenvs, account, environment, state, logs and firewall were preserved."
