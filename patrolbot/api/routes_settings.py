from __future__ import annotations

import time

from flask import Flask, current_app, request

from patrolbot.config import DEFAULT_CONFIG_PATH, load_runtime_config, save_runtime_config
from patrolbot.hardware.ultrasonic import UltrasonicSensor
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


def _sensor_slot(config_key: str) -> str:
    return 'front_ultrasonic' if config_key == 'ultrasonic' else 'rear_ultrasonic'


def _sensor_registry_attr(config_key: str) -> str:
    return 'ultrasonic' if config_key == 'ultrasonic' else 'ultrasonic_rear'


def _probe_sensor(runtime, config_key: str) -> dict:
    slot = _sensor_slot(config_key)
    reg_attr = _sensor_registry_attr(config_key)
    current = getattr(runtime.registry, reg_attr, None)
    if current and hasattr(current, 'close'):
        try:
            current.close()
        except Exception:
            pass
    probe_data = {
        'initialized': False,
        'detected': False,
        'healthy': False,
        'available': False,
        'last_error': None,
        'details': None,
        'last_probe_ts': time.time(),
    }
    sensor = None
    try:
        sensor = UltrasonicSensor(runtime.config, runtime.logger, config_key=config_key)
        probe_data.update(sensor.probe(reads=3, valid_reads_required=1))
        probe_data['available'] = bool(probe_data.get('detected'))
    except Exception as exc:
        probe_data['last_error'] = str(exc)
        probe_data['details'] = None
    entry = runtime.state.sensor_status.setdefault(slot, {})
    entry.update(probe_data)
    if probe_data.get('detected'):
        setattr(runtime.registry, reg_attr, sensor)
    else:
        setattr(runtime.registry, reg_attr, None)
        if sensor and hasattr(sensor, 'close'):
            sensor.close()
    return dict(entry)


def _sensor_payload(runtime, config_key: str) -> dict:
    slot = _sensor_slot(config_key)
    entry = dict(runtime.state.sensor_status.get(slot, {}))
    cfg = runtime.config.get(config_key, {}) or {}
    entry['config_key'] = config_key
    entry['trigger_pin'] = cfg.get('trigger_pin')
    entry['echo_pin'] = cfg.get('echo_pin')
    entry['configured'] = bool(cfg.get('enabled', config_key == 'ultrasonic'))
    entry['probe_on_startup'] = bool(cfg.get('probe_on_startup', entry['configured'] if config_key == 'ultrasonic' else False))
    entry['use_mode'] = str(cfg.get('use_mode', entry.get('use_mode', 'off')))
    entry['enabled'] = bool(entry.get('configured') and entry.get('use_mode') != 'off' and entry.get('detected'))
    return entry


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

    @app.get('/api/settings/system')
    def get_system_settings():
        runtime = current_app.config['PATROLBOT_RUNTIME']
        return {
            'ok': True,
            'start_patrol_on_boot': bool(runtime.config.get('patrol', {}).get('enabled', False)),
            'network': {
                'connected': runtime.state.network_connected,
                'ssid': runtime.state.network_ssid,
                'ip': runtime.state.network_ip,
                'last_error': runtime.state.network_last_error,
            },
        }

    @app.post('/api/settings/system')
    def save_system_settings():
        runtime = current_app.config['PATROLBOT_RUNTIME']
        payload = request.get_json(force=True, silent=True) or {}
        start_patrol_on_boot = bool(payload.get('start_patrol_on_boot', runtime.config.get('patrol', {}).get('enabled', False)))
        runtime.config.setdefault('patrol', {})['enabled'] = start_patrol_on_boot
        runtime_cfg = load_runtime_config()
        runtime_cfg.setdefault('patrol', {})['enabled'] = start_patrol_on_boot
        save_runtime_config(runtime_cfg)
        if runtime.patrol:
            runtime.patrol.update_config({'enabled': start_patrol_on_boot}, persist=False)
        return {'ok': True, 'start_patrol_on_boot': start_patrol_on_boot}

    @app.get('/api/settings/sensors')
    def get_sensor_settings():
        runtime = current_app.config['PATROLBOT_RUNTIME']
        return {
            'ok': True,
            'front_ultrasonic': _sensor_payload(runtime, 'ultrasonic'),
            'rear_ultrasonic': _sensor_payload(runtime, 'ultrasonic_rear'),
        }

    @app.post('/api/settings/sensors')
    def save_sensor_settings():
        runtime = current_app.config['PATROLBOT_RUNTIME']
        payload = request.get_json(force=True, silent=True) or {}
        runtime_cfg = load_runtime_config()
        updated = {}
        for config_key in ('ultrasonic', 'ultrasonic_rear'):
            patch = payload.get(config_key)
            if not isinstance(patch, dict):
                continue
            cfg = dict(runtime.config.get(config_key, {}) or {})
            cfg.update(patch)
            use_mode = str(cfg.get('use_mode', 'off')).strip().lower()
            if use_mode not in {'off', 'safety_only', 'fusion'}:
                use_mode = 'off'
            entry = runtime.state.sensor_status.setdefault(_sensor_slot(config_key), {})
            if use_mode != 'off' and not entry.get('detected'):
                return {'ok': False, 'error': f'{config_key} is not detected. Probe it before enabling.'}, 400
            cfg['use_mode'] = use_mode
            cfg['enabled'] = bool(use_mode != 'off')
            cfg['probe_on_startup'] = bool(cfg.get('probe_on_startup', cfg['enabled'] if config_key == 'ultrasonic' else False))
            runtime.config[config_key] = cfg
            runtime_cfg[config_key] = dict(cfg)
            entry['configured'] = bool(cfg.get('enabled', False))
            entry['probe_on_startup'] = bool(cfg.get('probe_on_startup', entry['configured'] if config_key == 'ultrasonic' else False))
            entry['use_mode'] = use_mode
            entry['enabled'] = bool(entry['configured'] and use_mode != 'off' and entry.get('detected'))
            updated[config_key] = _sensor_payload(runtime, config_key)
        save_runtime_config(runtime_cfg)
        return {'ok': True, **updated}

    @app.post('/api/settings/sensors/probe')
    def probe_sensors():
        runtime = current_app.config['PATROLBOT_RUNTIME']
        payload = request.get_json(force=True, silent=True) or {}
        target = str(payload.get('target', 'all')).strip().lower()
        results = {}
        if target in {'all', 'front', 'ultrasonic'}:
            results['front_ultrasonic'] = _probe_sensor(runtime, 'ultrasonic')
        if target in {'all', 'rear', 'ultrasonic_rear'}:
            results['rear_ultrasonic'] = _probe_sensor(runtime, 'ultrasonic_rear')
        return {'ok': True, **results}
