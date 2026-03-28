from __future__ import annotations

from flask import Flask, current_app, request

from patrolbot.config import load_runtime_config, save_runtime_config


TRACKING_DEFAULTS = {
    'enabled': False,
    'mode': 'camera_track',
    'detector': 'face',
    'target_label': '',
    'yolo_model': 'yolov8n.pt',
    'enable_yolo': False,
    'yolo_imgsz': 320,
    'yolo_classes': [],
    'confidence_min': 0.45,
    'max_results': 20,
    'min_area': 1500,
    'min_target_area': 900,
    'pan_gain': 0.06,
    'tilt_gain': 0.06,
    'x_deadzone_px': 48,
    'y_deadzone_px': 36,
    'smoothing_alpha': 0.4,
    'scan_when_lost': True,
    'scan_step': 2,
    'scan_tilt_step': 0,
    'lost_timeout_s': 1.5,
    'process_every_n_frames': 3,
    'box_padding_px': 8,
    'show_labels': True,
    'show_crosshair': True,
    'show_metrics_overlay': True,
    'preferred_target': 'largest',
    'overlay_enabled': True,
    'show_confidence_bar': True,
    'invert_error_x': False,
    'invert_error_y': False,
    'invert_pan_error': False,
    'follow_target_distance_cm': 60,
    'follow_distance_tolerance_cm': 15,
    'follow_drive_speed': 30,
    'follow_steer_gain': 0.4,
    'follow_use_ultrasonic': False,
    'follow_stop_distance_cm': 25,
    'follow_image_size_ratio_target': 0.25,
    'follow_image_size_tolerance': 0.06,
}


def _normalize_tracking_config(source: dict | None) -> dict:
    cfg = dict(TRACKING_DEFAULTS)
    cfg.update(source or {})
    cfg['enable_yolo'] = bool(cfg.get('enable_yolo', False))
    cfg['yolo_classes'] = list(cfg.get('yolo_classes') or [])
    return cfg


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
        cfg = runtime.tracking.get_config() if runtime.tracking else _normalize_tracking_config(runtime.config.get('tracking', {}))
        return {'ok': True, 'config': cfg, 'servo': _servo_payload(runtime), 'camera': _camera_payload(runtime)}

    @app.get('/api/tracking/detectors')
    def tracking_detectors():
        runtime = current_app.config['PATROLBOT_RUNTIME']
        details = runtime.tracking.get_detector_details() if runtime.tracking else runtime.state.tracking_detector_details
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
        if runtime.tracking:
            normalized, warnings = runtime.tracking.update_config(tracking_patch, persist=True)
        else:
            normalized = _normalize_tracking_config({**runtime.config.get('tracking', {}), **tracking_patch})
            runtime.config['tracking'] = dict(normalized)
            runtime_cfg = load_runtime_config()
            runtime_cfg['tracking'] = dict(normalized)
            warnings = ['tracking service not initialized; config saved only']
            save_runtime_config(runtime_cfg)
            runtime.state.tracking_mode = normalized.get('mode', runtime.state.tracking_mode)
            runtime.state.tracking_detector = normalized.get('detector', runtime.state.tracking_detector)
            runtime.state.tracking_preferred_target = normalized.get('preferred_target', runtime.state.tracking_preferred_target)
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
        if not runtime.tracking:
            return {'ok': False, 'error': 'tracking service unavailable in phase 1'}, 503
        runtime.tracking.toggle()
        return {'ok': True, 'enabled': runtime.state.tracking_enabled}

    @app.post('/api/tracking/enable')
    def tracking_enable():
        runtime = current_app.config['PATROLBOT_RUNTIME']
        if not runtime.tracking:
            return {'ok': False, 'error': 'tracking service unavailable in phase 1'}, 503
        runtime.tracking.enable()
        return {'ok': True, 'enabled': runtime.state.tracking_enabled}

    @app.post('/api/tracking/disable')
    def tracking_disable():
        runtime = current_app.config['PATROLBOT_RUNTIME']
        if not runtime.tracking:
            return {'ok': False, 'error': 'tracking service unavailable in phase 1'}, 503
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
