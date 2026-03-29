from __future__ import annotations

from flask import Flask, current_app, request

from patrolbot.config import load_runtime_config, save_runtime_config


VISION_DEFAULTS = {
    'enabled': False,
    'detector': 'face',
    'yolo_model': 'yolov8n.pt',
    'enable_yolo': False,
    'yolo_imgsz': 320,
    'yolo_classes': [],
    'confidence_min': 0.45,
    'max_results': 20,
    'process_every_n_frames': 3,
    'box_padding_px': 8,
    'show_labels': True,
    'show_crosshair': True,
    'show_metrics_overlay': True,
    'preferred_target': 'largest',
    'overlay_enabled': True,
    'show_confidence_bar': True,
}


def _normalize_vision_config(source: dict | None) -> dict:
    cfg = dict(VISION_DEFAULTS)
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
        'vision_enabled': state.vision_enabled,
        'detector': state.vision_detector,
        'target_acquired': state.vision_target_acquired,
        'target_box': state.vision_box,
        'target_label': state.vision_target_label,
        'target_confidence': state.vision_target_confidence,
        'frame_size': state.vision_frame_size,
        'pan_angle': state.pan_angle,
        'tilt_angle': state.tilt_angle,
        'pan_physical': (((servo.get('pan') or {}).get('physical_angle')) if servo else None),
        'tilt_physical': (((servo.get('tilt') or {}).get('physical_angle')) if servo else None),
        'last_error': state.vision_last_error,
        'last_detection_count': state.vision_last_detection_count,
        'detector_available': state.vision_detector_available,
        'detector_status': state.vision_detector_status,
        'detector_details': state.vision_detector_details,
        'servo_backend': servo_driver,
        'servo_driver_requested': servo_driver,
        'servo_ok': True if servo else False,
        'servo_status': 'ready' if servo else 'unavailable',
        'yolo_available': state.vision_yolo_available,
        'selected_target_source': state.vision_preferred_target,
        'metrics': state.vision_metrics,
        'mjpeg_clients': state.vision_mjpeg_clients,
        'disable_reason': state.vision_disable_reason,
        'overlay_enabled': state.vision_overlay_enabled,
        'stream_url': '/video_feed?view=vision',
    }


def register_vision_routes(app: Flask) -> None:
    @app.get('/api/vision/state')
    def vision_state():
        runtime = current_app.config['PATROLBOT_RUNTIME']
        return {'ok': True, 'state': _state_payload(runtime)}

    @app.get('/api/vision/config')
    def vision_config():
        runtime = current_app.config['PATROLBOT_RUNTIME']
        cfg = runtime.vision.get_config() if runtime.vision else _normalize_vision_config(runtime.config.get('vision') or runtime.config.get('tracking', {}))
        return {'ok': True, 'config': cfg, 'servo': _servo_payload(runtime), 'camera': _camera_payload(runtime)}

    @app.get('/api/vision/detectors')
    def vision_detectors():
        runtime = current_app.config['PATROLBOT_RUNTIME']
        details = runtime.vision.get_detector_details() if runtime.vision else runtime.state.vision_detector_details
        return {'ok': True, 'details': details}

    @app.get('/api/vision/debug')
    def vision_debug():
        runtime = current_app.config['PATROLBOT_RUNTIME']
        state = runtime.state
        return {
            'ok': True,
            'enabled': state.vision_enabled,
            'detector': state.vision_detector,
            'detector_status': state.vision_detector_status,
            'detector_available': state.vision_detector_available,
            'detector_details': state.vision_detector_details,
            'target_acquired': state.vision_target_acquired,
            'target_box': state.vision_box,
            'target_label': state.vision_target_label,
            'target_confidence': state.vision_target_confidence,
            'disable_reason': state.vision_disable_reason,
            'pan_angle': state.pan_angle,
            'tilt_angle': state.tilt_angle,
            'frame_size': state.vision_frame_size,
            'last_detection_count': state.vision_last_detection_count,
            'metrics': state.vision_metrics,
            'mjpeg_clients': state.vision_mjpeg_clients,
            'yolo_available': state.vision_yolo_available,
            'last_error': state.vision_last_error,
        }

    @app.post('/api/vision/config')
    def vision_update_config():
        runtime = current_app.config['PATROLBOT_RUNTIME']
        payload = request.get_json(force=True, silent=True) or {}
        vision_patch = payload.get('vision', payload)
        if runtime.vision:
            normalized, warnings = runtime.vision.update_config(vision_patch, persist=True)
        else:
            normalized = _normalize_vision_config({**(runtime.config.get('vision') or runtime.config.get('tracking', {})), **vision_patch})
            runtime.config['vision'] = dict(normalized)
            runtime.config['tracking'] = dict(normalized)
            runtime_cfg = load_runtime_config()
            runtime_cfg['vision'] = dict(normalized)
            runtime_cfg['tracking'] = dict(normalized)
            warnings = ['vision service not initialized; config saved only']
            save_runtime_config(runtime_cfg)
            runtime.state.vision_detector = normalized.get('detector', runtime.state.vision_detector)
            runtime.state.vision_preferred_target = normalized.get('preferred_target', runtime.state.vision_preferred_target)
        runtime_cfg = load_runtime_config()
        if 'servo' in payload and isinstance(payload['servo'], dict):
            runtime_cfg['servo'] = dict(payload['servo'])
            runtime.config['servo'] = dict(payload['servo'])
        if 'camera' in payload and isinstance(payload['camera'], dict):
            runtime_cfg['camera'] = dict(payload['camera'])
            runtime.config['camera'] = dict(payload['camera'])
        save_runtime_config(runtime_cfg)
        return {'ok': True, 'config': normalized, 'warnings': warnings, 'servo': _servo_payload(runtime), 'camera': _camera_payload(runtime)}

    @app.post('/api/vision/toggle')
    def vision_toggle():
        runtime = current_app.config['PATROLBOT_RUNTIME']
        if not runtime.vision:
            return {'ok': False, 'error': 'vision service unavailable'}, 503
        runtime.vision.toggle()
        return {'ok': True, 'enabled': runtime.state.vision_enabled}

    @app.post('/api/vision/enable')
    def vision_enable():
        runtime = current_app.config['PATROLBOT_RUNTIME']
        if not runtime.vision:
            return {'ok': False, 'error': 'vision service unavailable'}, 503
        runtime.vision.enable()
        return {'ok': True, 'enabled': runtime.state.vision_enabled}

    @app.post('/api/vision/disable')
    def vision_disable():
        runtime = current_app.config['PATROLBOT_RUNTIME']
        if not runtime.vision:
            return {'ok': False, 'error': 'vision service unavailable'}, 503
        runtime.vision.disable()
        return {'ok': True, 'enabled': runtime.state.vision_enabled}

    @app.post('/api/vision/servo/home')
    def vision_servo_home():
        runtime = current_app.config['PATROLBOT_RUNTIME']
        servo = getattr(runtime.registry, 'camera_servo', None)
        if not servo:
            return {'ok': False, 'error': 'camera servo unavailable'}, 503
        servo.home()
        runtime.state.pan_angle = servo.pan_angle
        runtime.state.tilt_angle = servo.tilt_angle
        return {'ok': True, 'servo': _servo_payload(runtime)}

    @app.post('/api/vision/servo/set')
    def vision_servo_set():
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

    @app.post('/api/vision/servo/nudge')
    def vision_servo_nudge():
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
