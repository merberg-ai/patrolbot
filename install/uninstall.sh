#!/usr/bin/env bash
set -euo pipefail
sudo systemctl disable --now patrolbot.service || true
sudo rm -f /etc/systemd/system/patrolbot.service
sudo systemctl daemon-reload
echo "patrolbot service removed. Project files in ~/patrolbot were left intact on purpose."
