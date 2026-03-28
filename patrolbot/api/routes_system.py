from __future__ import annotations
import socket
from pathlib import Path

from flask import Flask, current_app, request, send_file
from patrolbot.config import BASE_DIR
from patrolbot.services.version import get_version_info


def _get_ip() -> str | None:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return None


def _resolve_log_path(runtime) -> Path:
    logging_cfg = runtime.config.get('logging', {}) or {}
    raw = logging_cfg.get('file', 'logs/patrolbot.log')
    return (BASE_DIR / raw).resolve()


def register_system_routes(app: Flask) -> None:
    @app.get('/api/system')
    def api_system():
        runtime = current_app.config['PATROLBOT_RUNTIME']
        version = get_version_info()
        return {
            'ok': True,
            'ip': runtime.state.network_ip or _get_ip(),
            'mode': runtime.state.mode,
            'led_state': runtime.state.led_state,
            'system_status': runtime.state.system_status,
            'network': {
                'connected': runtime.state.network_connected,
                'ssid': runtime.state.network_ssid,
                'ip': runtime.state.network_ip,
                'last_error': runtime.state.network_last_error,
            },
            'services': {
                'camera_running': bool(runtime.registry.camera and runtime.registry.camera.running),
                'telemetry_running': bool(runtime.telemetry and getattr(runtime.telemetry, '_thread', None)),
                'patrol_service': bool(runtime.patrol),
                'tracking_service': bool(runtime.tracking),
            },
            'sensors': runtime.state.sensor_status,
            'snapshots': {
                'count': runtime.state.snapshot_count,
                'last_saved': runtime.state.snapshot_last_saved,
            },
            'version': version,
        }

    @app.get('/api/system/logs')
    def api_system_logs():
        runtime = current_app.config['PATROLBOT_RUNTIME']
        limit = max(20, min(1000, int(request.args.get('limit', 200))))
        contains = (request.args.get('contains') or '').strip().lower()
        log_path = _resolve_log_path(runtime)
        lines = []
        if log_path.exists():
            raw_lines = log_path.read_text(errors='replace').splitlines()
            if contains:
                raw_lines = [line for line in raw_lines if contains in line.lower()]
            lines = raw_lines[-limit:]
        return {'ok': True, 'path': str(log_path), 'lines': lines, 'line_count': len(lines)}

    @app.get('/api/system/snapshots')
    def api_system_snapshots():
        runtime = current_app.config['PATROLBOT_RUNTIME']
        service = runtime.snapshots
        items = service.list_snapshots(limit=request.args.get('limit', 200)) if service else []
        for item in items:
            item['url'] = f"/api/system/snapshots/file/{item['name']}"
        return {'ok': True, 'items': items}

    @app.get('/api/system/snapshots/file/<path:name>')
    def api_system_snapshot_file(name: str):
        runtime = current_app.config['PATROLBOT_RUNTIME']
        path = runtime.snapshots.resolve_snapshot(name)
        return send_file(path)

    @app.delete('/api/system/snapshots/<path:name>')
    def api_system_snapshot_delete(name: str):
        runtime = current_app.config['PATROLBOT_RUNTIME']
        runtime.snapshots.delete_snapshot(name)
        runtime.state.snapshot_count = len(runtime.snapshots.list_snapshots(limit=9999))
        return {'ok': True, 'deleted': name, 'snapshot_count': runtime.state.snapshot_count}

    @app.post('/api/system/snapshots/delete_all')
    def api_system_snapshot_delete_all():
        runtime = current_app.config['PATROLBOT_RUNTIME']
        deleted = runtime.snapshots.delete_all() if runtime.snapshots else 0
        runtime.state.snapshot_count = 0
        return {'ok': True, 'deleted': deleted, 'snapshot_count': 0}

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
