from __future__ import annotations

from flask import Flask, current_app, request

from patrolbot.config import load_runtime_config, save_runtime_config


def _servo_payload(runtime):
    servo = getattr(runtime.registry, 'camera_servo', None)
    if not servo:
        return None
    state = servo.get_state()
    for axis in ('pan', 'tilt'):
        if axis in state:
            item = state[axis]
            item['min'] = item.get('min_angle')
            item['max'] = item.get('max_angle')
            item['physical_angle'] = getattr(servo, f'_physical_{axis}')(item.get('angle', 90))
    return state


def _camera_payload(runtime):
    return dict(runtime.config.get('camera', {}) or {})


def _state_payload(runtime):
    state = runtime.state
    servo = _servo_payload(runtime) or {}
    servo_driver = 'pca9685' if getattr(getattr(runtime.registry, 'camera_servo', None), 'driver', None) else 'unknown'
    return {
        'tracking_enabled': state.tracking_enabled,
        'detector': state.tracking_detector,
        'target_acquired': state.tracking_target_acquired,
        'target_box': state.tracking_box,
        'target_label': state.tracking_target_label,
        'target_confidence': state.tracking_target_confidence,
        'frame_size': state.tracking_frame_size,
        'pan_angle': state.pan_angle,
        'tilt_angle': state.tilt_angle,
        'pan_physical': (((servo.get('pan') or {}).get('physical_angle')) if servo else None),
        'tilt_physical': (((servo.get('tilt') or {}).get('physical_angle')) if servo else None),
        'last_error': state.tracking_last_error,
        'last_detection_count': state.tracking_last_detection_count,
        'detector_available': state.tracking_detector_available,
        'detector_status': state.tracking_detector_status,
        'detector_details': state.tracking_detector_details,
        'servo_backend': servo_driver,
        'servo_driver_requested': servo_driver,
        'servo_ok': True if servo else False,
        'servo_status': 'ready' if servo else 'unavailable',
        'yolo_available': state.tracking_yolo_available,
        'selected_target_source': state.tracking_preferred_target,
        'scan_active': state.tracking_scan_active,
        'metrics': state.tracking_metrics,
        'mjpeg_clients': state.tracking_mjpeg_clients,
        'mode': state.tracking_mode,
        'follow_distance_cm': state.tracking_follow_distance_cm,
        'follow_state': state.tracking_follow_state,
    }


def register_tracking_routes(app: Flask) -> None:
    @app.get('/api/tracking/state')
    def tracking_state():
        runtime = current_app.config['PATROLBOT_RUNTIME']
        return {'ok': True, 'state': _state_payload(runtime)}

    @app.get('/api/tracking/config')
    def tracking_config():
        runtime = current_app.config['PATROLBOT_RUNTIME']
        cfg = runtime.tracking.get_config() if runtime.tracking else dict(runtime.config.get('tracking', {}))
        return {'ok': True, 'config': cfg, 'servo': _servo_payload(runtime), 'camera': _camera_payload(runtime)}

    @app.get('/api/tracking/detectors')
    def tracking_detectors():
        runtime = current_app.config['PATROLBOT_RUNTIME']
        details = runtime.tracking.get_detector_details() if runtime.tracking else {}
        return {'ok': True, 'details': details}

    @app.get('/api/tracking/debug')
    def tracking_debug():
        runtime = current_app.config['PATROLBOT_RUNTIME']
        state = runtime.state
        return {
            'ok': True,
            'enabled': state.tracking_enabled,
            'mode': state.tracking_mode,
            'detector': state.tracking_detector,
            'detector_status': state.tracking_detector_status,
            'detector_available': state.tracking_detector_available,
            'detector_details': state.tracking_detector_details,
            'target_acquired': state.tracking_target_acquired,
            'target_box': state.tracking_box,
            'target_label': state.tracking_target_label,
            'target_confidence': state.tracking_target_confidence,
            'disable_reason': state.tracking_disable_reason,
            'scan_active': state.tracking_scan_active,
            'pan_angle': state.pan_angle,
            'tilt_angle': state.tilt_angle,
            'frame_size': state.tracking_frame_size,
            'last_detection_count': state.tracking_last_detection_count,
            'metrics': state.tracking_metrics,
            'mjpeg_clients': state.tracking_mjpeg_clients,
            'yolo_available': state.tracking_yolo_available,
            'last_error': state.tracking_last_error,
        }

    @app.post('/api/tracking/config')
    def tracking_update_config():
        runtime = current_app.config['PATROLBOT_RUNTIME']
        payload = request.get_json(force=True, silent=True) or {}
        tracking_patch = payload.get('tracking', payload)
        if not runtime.tracking:
            return {'ok': False, 'error': 'tracking service unavailable'}, 503
        normalized, warnings = runtime.tracking.update_config(tracking_patch, persist=True)

        runtime_cfg = load_runtime_config()
        if 'servo' in payload and isinstance(payload['servo'], dict):
            runtime_cfg['servo'] = dict(payload['servo'])
            runtime.config['servo'] = dict(payload['servo'])
        if 'camera' in payload and isinstance(payload['camera'], dict):
            runtime_cfg['camera'] = dict(payload['camera'])
            runtime.config['camera'] = dict(payload['camera'])
        save_runtime_config(runtime_cfg)
        return {'ok': True, 'config': normalized, 'warnings': warnings, 'servo': _servo_payload(runtime), 'camera': _camera_payload(runtime)}

    @app.post('/api/tracking/toggle')
    def tracking_toggle():
        runtime = current_app.config['PATROLBOT_RUNTIME']
        if runtime.tracking:
            runtime.tracking.toggle()
        return {'ok': True, 'enabled': runtime.state.tracking_enabled}

    @app.post('/api/tracking/enable')
    def tracking_enable():
        runtime = current_app.config['PATROLBOT_RUNTIME']
        if runtime.tracking:
            runtime.tracking.enable()
        return {'ok': True, 'enabled': runtime.state.tracking_enabled}

    @app.post('/api/tracking/disable')
    def tracking_disable():
        runtime = current_app.config['PATROLBOT_RUNTIME']
        if runtime.tracking:
            runtime.tracking.disable()
        return {'ok': True, 'enabled': runtime.state.tracking_enabled}

    @app.post('/api/tracking/servo/home')
    def tracking_servo_home():
        runtime = current_app.config['PATROLBOT_RUNTIME']
        servo = getattr(runtime.registry, 'camera_servo', None)
        if not servo:
            return {'ok': False, 'error': 'camera servo unavailable'}, 503
        servo.home()
        runtime.state.pan_angle = servo.pan_angle
        runtime.state.tilt_angle = servo.tilt_angle
        return {'ok': True, 'servo': _servo_payload(runtime)}

    @app.post('/api/tracking/servo/set')
    def tracking_servo_set():
        runtime = current_app.config['PATROLBOT_RUNTIME']
        servo = getattr(runtime.registry, 'camera_servo', None)
        if not servo:
            return {'ok': False, 'error': 'camera servo unavailable'}, 503
        payload = request.get_json(force=True, silent=True) or {}
        pan = int(payload.get('pan', servo.pan_angle))
        tilt = int(payload.get('tilt', servo.tilt_angle))
        pan_trim = payload.get('pan_trim')
        tilt_trim = payload.get('tilt_trim')
        servo.set_pan(pan)
        servo.set_tilt(tilt)
        if pan_trim is not None:
            servo.set_pan_trim(int(pan_trim))
        if tilt_trim is not None:
            servo.set_tilt_trim(int(tilt_trim))
        runtime.state.pan_angle = servo.pan_angle
        runtime.state.tilt_angle = servo.tilt_angle
        runtime_cfg = load_runtime_config()
        runtime_cfg.setdefault('servo', {})
        runtime_cfg['servo'].setdefault('camera_pan', {})
        runtime_cfg['servo'].setdefault('camera_tilt', {})
        runtime_cfg['servo']['camera_pan']['trim'] = servo.pan_trim
        runtime_cfg['servo']['camera_tilt']['trim'] = servo.tilt_trim
        save_runtime_config(runtime_cfg)
        return {'ok': True, 'servo': _servo_payload(runtime)}

    @app.post('/api/tracking/servo/nudge')
    def tracking_servo_nudge():
        runtime = current_app.config['PATROLBOT_RUNTIME']
        servo = getattr(runtime.registry, 'camera_servo', None)
        if not servo:
            return {'ok': False, 'error': 'camera servo unavailable'}, 503
        payload = request.get_json(force=True, silent=True) or {}
        direction = str(payload.get('direction', '')).lower()
        if direction == 'left':
            servo.pan_left()
        elif direction == 'right':
            servo.pan_right()
        elif direction == 'up':
            servo.tilt_up()
        elif direction == 'down':
            servo.tilt_down()
        else:
            servo.set_pan(int(payload.get('pan', servo.pan_angle)))
            servo.set_tilt(int(payload.get('tilt', servo.tilt_angle)))
        runtime.state.pan_angle = servo.pan_angle
        runtime.state.tilt_angle = servo.tilt_angle
        return {'ok': True, 'servo': _servo_payload(runtime)}
