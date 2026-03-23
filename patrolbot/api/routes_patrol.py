from __future__ import annotations

from flask import Flask, current_app, request

def _state_payload(runtime):
    state = runtime.state
    return {
        'enabled': state.patrol_enabled,
        'mode': state.patrol_mode,
        'drive_state': state.patrol_drive_state,
        'speed': state.patrol_speed,
        'targets': state.patrol_targets,
        'detect_count': state.patrol_detect_count,
        'last_detected': state.patrol_last_detected,
        'metrics': state.patrol_metrics,
        'disable_reason': state.patrol_disable_reason,
        'last_error': state.patrol_last_error,
    }

def register_patrol_routes(app: Flask) -> None:
    @app.route('/api/patrol/state', methods=['GET'], strict_slashes=False)
    def patrol_state():
        runtime = current_app.config['PATROLBOT_RUNTIME']
        return {'ok': True, 'state': _state_payload(runtime)}

    @app.route('/api/patrol/config', methods=['GET'], strict_slashes=False)
    def patrol_config():
        runtime = current_app.config['PATROLBOT_RUNTIME']
        cfg = runtime.patrol.get_config() if runtime.patrol else dict(runtime.config.get('patrol', {}))
        return {'ok': True, 'config': cfg}

    @app.route('/api/patrol/config', methods=['POST'], strict_slashes=False)
    def patrol_update_config():
        runtime = current_app.config['PATROLBOT_RUNTIME']
        payload = request.get_json(force=True, silent=True) or {}
        if not runtime.patrol:
            return {'ok': False, 'error': 'patrol service unavailable'}, 503
        normalized, warnings = runtime.patrol.update_config(payload, persist=True)
        return {'ok': True, 'config': normalized, 'warnings': warnings}

    @app.route('/api/patrol/toggle', methods=['POST'], strict_slashes=False)
    def patrol_toggle():
        runtime = current_app.config['PATROLBOT_RUNTIME']
        if runtime.patrol:
            runtime.patrol.toggle()
        return {'ok': True, 'enabled': runtime.state.patrol_enabled}

    @app.route('/api/patrol/enable', methods=['POST'], strict_slashes=False)
    def patrol_enable():
        runtime = current_app.config['PATROLBOT_RUNTIME']
        if runtime.patrol:
            runtime.patrol.enable()
        return {'ok': True, 'enabled': runtime.state.patrol_enabled}

    @app.route('/api/patrol/disable', methods=['POST'], strict_slashes=False)
    def patrol_disable():
        runtime = current_app.config['PATROLBOT_RUNTIME']
        if runtime.patrol:
            runtime.patrol.disable()
        return {'ok': True, 'enabled': runtime.state.patrol_enabled}
