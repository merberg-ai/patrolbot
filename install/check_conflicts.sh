#!/usr/bin/env bash
set -euo pipefail
echo "Checking for obvious patrolbot conflicts..."
systemctl list-unit-files | grep -Ei 'adeept|picar|marsrover' || true
ps aux | grep -Ei 'adeept|webServer_HAT|webServer.py' | grep -v grep || true
echo "If you see old Adeept services or robot Python processes above, disable them before using patrolbot."
