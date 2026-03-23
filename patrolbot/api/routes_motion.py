from __future__ import annotations
from flask import Flask, current_app, request
from patrolbot.services.safety import emergency_stop

def _speed_from_payload(payload, runtime):
    default_speed = runtime.config.get('motors', {}).get('default_speed', 40)
    return int(payload.get('speed', default_speed))

def _motion_locked_response(runtime, message: str):
    return {
        'ok': False,
        'error': message,
        'motor_state': runtime.registry.motors.state,
        'speed': runtime.registry.motors.speed,
        'motion_locked': runtime.registry.motors.motion_locked,
        'estop_latched': runtime.registry.motors.estop_latched,
    }, 409

def register_motion_routes(app: Flask) -> None:
    @app.post('/api/motor/stop')
    def motor_stop():
        runtime = current_app.config['PATROLBOT_RUNTIME']
        runtime.registry.motors.stop()
        runtime.state.motor_state = runtime.registry.motors.state
        runtime.state.speed = runtime.registry.motors.speed
        runtime.state.estop_latched = runtime.registry.motors.estop_latched
        return {
            'ok': True,
            'motor_state': runtime.registry.motors.state,
            'speed': runtime.registry.motors.speed,
            'estop_latched': runtime.registry.motors.estop_latched,
        }

    @app.post('/api/motor/estop')
    def motor_estop():
        runtime = current_app.config['PATROLBOT_RUNTIME']
        emergency_stop(runtime, runtime.logger, latch=True)
        return {
            'ok': True,
            'motor_state': runtime.registry.motors.state,
            'speed': runtime.registry.motors.speed,
            'estop_latched': runtime.registry.motors.estop_latched,
        }

    @app.post('/api/motor/clear_estop')
    def motor_clear_estop():
        runtime = current_app.config['PATROLBOT_RUNTIME']
        runtime.registry.motors.clear_estop()
        runtime.state.estop_latched = runtime.registry.motors.estop_latched
        return {'ok': True, 'estop_latched': runtime.registry.motors.estop_latched}

    @app.post('/api/motor/forward')
    def motor_forward():
        runtime = current_app.config['PATROLBOT_RUNTIME']
        payload = request.get_json(force=True, silent=True) or {}
        try:
            runtime.registry.motors.forward(_speed_from_payload(payload, runtime))
        except RuntimeError as exc:
            return _motion_locked_response(runtime, str(exc))
        runtime.state.motor_state = runtime.registry.motors.state
        runtime.state.speed = runtime.registry.motors.speed
        return {'ok': True, 'motor_state': runtime.registry.motors.state, 'speed': runtime.registry.motors.speed}

    @app.post('/api/motor/backward')
    def motor_backward():
        runtime = current_app.config['PATROLBOT_RUNTIME']
        payload = request.get_json(force=True, silent=True) or {}
        try:
            runtime.registry.motors.backward(_speed_from_payload(payload, runtime))
        except RuntimeError as exc:
            return _motion_locked_response(runtime, str(exc))
        runtime.state.motor_state = runtime.registry.motors.state
        runtime.state.speed = runtime.registry.motors.speed
        return {'ok': True, 'motor_state': runtime.registry.motors.state, 'speed': runtime.registry.motors.speed}

    @app.post('/api/steering/center')
    def steering_center():
        runtime = current_app.config['PATROLBOT_RUNTIME']
        runtime.registry.steering.center()
        runtime.state.steering_angle = runtime.registry.steering.angle
        return {'ok': True, 'steering_angle': runtime.registry.steering.angle}

    @app.post('/api/steering/left')
    def steering_left():
        runtime = current_app.config['PATROLBOT_RUNTIME']
        runtime.registry.steering.left()
        runtime.state.steering_angle = runtime.registry.steering.angle
        return {'ok': True, 'steering_angle': runtime.registry.steering.angle}

    @app.post('/api/steering/right')
    def steering_right():
        runtime = current_app.config['PATROLBOT_RUNTIME']
        runtime.registry.steering.right()
        runtime.state.steering_angle = runtime.registry.steering.angle
        return {'ok': True, 'steering_angle': runtime.registry.steering.angle}

    @app.post('/api/steering/set')
    def steering_set():
        runtime = current_app.config['PATROLBOT_RUNTIME']
        payload = request.get_json(force=True, silent=True) or {}
        angle = int(payload.get('angle', 90))
        runtime.registry.steering.set_angle(angle)
        runtime.state.steering_angle = runtime.registry.steering.angle
        return {'ok': True, 'steering_angle': runtime.registry.steering.angle}

    @app.post('/api/camera/home')
    def camera_home():
        runtime = current_app.config['PATROLBOT_RUNTIME']
        runtime.registry.camera_servo.home()
        runtime.state.pan_angle = runtime.registry.camera_servo.pan_angle
        runtime.state.tilt_angle = runtime.registry.camera_servo.tilt_angle
        return {'ok': True, 'pan_angle': runtime.registry.camera_servo.pan_angle, 'tilt_angle': runtime.registry.camera_servo.tilt_angle}

    @app.post('/api/camera/pan_left')
    def camera_pan_left():
        runtime = current_app.config['PATROLBOT_RUNTIME']
        runtime.registry.camera_servo.pan_left()
        runtime.state.pan_angle = runtime.registry.camera_servo.pan_angle
        return {'ok': True, 'pan_angle': runtime.registry.camera_servo.pan_angle}

    @app.post('/api/camera/pan_right')
    def camera_pan_right():
        runtime = current_app.config['PATROLBOT_RUNTIME']
        runtime.registry.camera_servo.pan_right()
        runtime.state.pan_angle = runtime.registry.camera_servo.pan_angle
        return {'ok': True, 'pan_angle': runtime.registry.camera_servo.pan_angle}

    @app.post('/api/camera/tilt_up')
    def camera_tilt_up():
        runtime = current_app.config['PATROLBOT_RUNTIME']
        runtime.registry.camera_servo.tilt_up()
        runtime.state.tilt_angle = runtime.registry.camera_servo.tilt_angle
        return {'ok': True, 'tilt_angle': runtime.registry.camera_servo.tilt_angle}

    @app.post('/api/camera/tilt_down')
    def camera_tilt_down():
        runtime = current_app.config['PATROLBOT_RUNTIME']
        runtime.registry.camera_servo.tilt_down()
        runtime.state.tilt_angle = runtime.registry.camera_servo.tilt_angle
        return {'ok': True, 'tilt_angle': runtime.registry.camera_servo.tilt_angle}
