from __future__ import annotations

from flask import Flask, current_app, request

from patrolbot.config import DEFAULT_CONFIG_PATH, load_runtime_config, save_runtime_config
from patrolbot.services.camera_settings import (
    build_camera_settings_from_config,
    metadata_for_response,
    normalize_camera_settings,
    persist_camera_settings,
    update_runtime_camera_config,
)


def _clamp_trim(value) -> int:
    return max(-20, min(20, int(value)))


def _apply_camera_settings(runtime, normalized: dict):
    cam = runtime.registry.camera
    persist_camera_settings(normalized)
    update_runtime_camera_config(runtime, normalized)

    apply_result = {'ok': True, 'applied': False, 'warnings': []}
    if cam is not None:
        apply_result = cam.restart_with_settings(normalized)

    return {
        'ok': True,
        'camera_running': bool(cam and cam.running),
        'applied_live': bool(apply_result.get('applied', False)),
        'camera_restarted': bool(apply_result.get('restarted', False)),
        'settings': cam.get_settings() if cam else build_camera_settings_from_config(runtime.config),
        'saved_settings': build_camera_settings_from_config(runtime.config),
        'warnings': list(apply_result.get('warnings', [])),
        **metadata_for_response(),
    }


def register_settings_routes(app: Flask) -> None:
    @app.get('/api/settings/servo_trim')
    def get_servo_trim():
        runtime = current_app.config['PATROLBOT_RUNTIME']
        return {
            'ok': True,
            'steering_trim': runtime.registry.steering.trim,
            'camera_pan_trim': runtime.registry.camera_servo.pan_trim,
            'camera_tilt_trim': runtime.registry.camera_servo.tilt_trim,
        }

    @app.post('/api/settings/servo_trim')
    def set_servo_trim():
        runtime = current_app.config['PATROLBOT_RUNTIME']
        payload = request.get_json(force=True, silent=True) or {}

        steering_trim = _clamp_trim(payload.get('steering_trim', runtime.registry.steering.trim))
        camera_pan_trim = _clamp_trim(payload.get('camera_pan_trim', runtime.registry.camera_servo.pan_trim))
        camera_tilt_trim = _clamp_trim(payload.get('camera_tilt_trim', runtime.registry.camera_servo.tilt_trim))

        runtime.registry.steering.set_trim(steering_trim)
        runtime.registry.camera_servo.set_pan_trim(camera_pan_trim)
        runtime.registry.camera_servo.set_tilt_trim(camera_tilt_trim)

        runtime_cfg = load_runtime_config()
        runtime_cfg.setdefault('servo', {})
        runtime_cfg['servo'].setdefault('steering', {})
        runtime_cfg['servo'].setdefault('camera_pan', {})
        runtime_cfg['servo'].setdefault('camera_tilt', {})
        runtime_cfg['servo']['steering']['trim'] = steering_trim
        runtime_cfg['servo']['camera_pan']['trim'] = camera_pan_trim
        runtime_cfg['servo']['camera_tilt']['trim'] = camera_tilt_trim
        save_runtime_config(runtime_cfg)

        runtime.config.setdefault('servo', {}).setdefault('steering', {})['trim'] = steering_trim
        runtime.config.setdefault('servo', {}).setdefault('camera_pan', {})['trim'] = camera_pan_trim
        runtime.config.setdefault('servo', {}).setdefault('camera_tilt', {})['trim'] = camera_tilt_trim

        runtime.state.steering_angle = runtime.registry.steering.angle
        runtime.state.pan_angle = runtime.registry.camera_servo.pan_angle
        runtime.state.tilt_angle = runtime.registry.camera_servo.tilt_angle

        return {
            'ok': True,
            'steering_trim': steering_trim,
            'camera_pan_trim': camera_pan_trim,
            'camera_tilt_trim': camera_tilt_trim,
        }

    @app.get('/api/settings/camera')
    def get_camera_settings():
        runtime = current_app.config['PATROLBOT_RUNTIME']
        cam = runtime.registry.camera
        config_settings = build_camera_settings_from_config(runtime.config)
        live_settings = cam.get_settings() if cam else config_settings
        return {
            'ok': True,
            'camera_running': bool(cam and cam.running),
            'settings': live_settings,
            'saved_settings': config_settings,
            **metadata_for_response(),
        }

    @app.post('/api/settings/camera')
    def set_camera_settings():
        runtime = current_app.config['PATROLBOT_RUNTIME']
        payload = request.get_json(force=True, silent=True) or {}

        merged_input = build_camera_settings_from_config(runtime.config)
        merged_input.update(payload)
        normalized, warnings = normalize_camera_settings(merged_input)
        result = _apply_camera_settings(runtime, normalized)
        result['warnings'] = warnings + result.get('warnings', [])
        return result

    @app.post('/api/settings/camera/reset')
    def reset_camera_settings():
        runtime = current_app.config['PATROLBOT_RUNTIME']
        import yaml
        default_cfg = yaml.safe_load(DEFAULT_CONFIG_PATH.read_text()) or {}
        normalized, warnings = normalize_camera_settings((default_cfg or {}).get('camera', {}))
        result = _apply_camera_settings(runtime, normalized)
        result['warnings'] = warnings + result.get('warnings', [])
        return result
