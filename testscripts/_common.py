from __future__ import annotations
import subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
def refuse_if_service_running() -> None:
    result = subprocess.run(['systemctl','is-active','--quiet','patrolbot.service'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if result.returncode == 0: raise SystemExit('patrolbot.service is running. Stop it before running direct hardware tests.')
