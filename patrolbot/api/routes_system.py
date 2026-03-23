from __future__ import annotations
from flask import Flask, current_app
from patrolbot.services.version import get_version_info
import socket


def _get_ip() -> str | None:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return None


def register_system_routes(app: Flask) -> None:
    @app.get('/api/system')
    def api_system():
        runtime = current_app.config['PATROLBOT_RUNTIME']
        version = get_version_info()
        return {
            'ok': True,
            'ip': _get_ip(),
            'mode': runtime.state.mode,
            'led_state': runtime.state.led_state,
            'version': version,
        }

    @app.post('/api/system/reboot')
    def api_system_reboot():
        import os
        os.system('sudo reboot')
        return {'ok': True}

    @app.post('/api/system/shutdown')
    def api_system_shutdown():
        import os
        os.system('sudo shutdown -h now')
        return {'ok': True}
