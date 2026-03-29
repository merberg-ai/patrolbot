from __future__ import annotations

def emergency_stop(runtime, logger, latch: bool = True) -> None:
    if runtime and runtime.registry and runtime.registry.motors:
        runtime.registry.motors.emergency_stop(latch=latch)
        runtime.state.motor_state = runtime.registry.motors.state
        runtime.state.speed = runtime.registry.motors.speed
        runtime.state.estop_latched = runtime.registry.motors.estop_latched
        logger.warning('Emergency stop triggered')

def safe_shutdown(runtime, logger) -> None:
    if runtime is None:
        return
    logger.info('Beginning patrolbot safe shutdown')
    reg = runtime.registry
    try:
        if getattr(runtime, 'telemetry', None):
            runtime.telemetry.stop()
        if getattr(runtime, 'vision', None):
            runtime.vision.stop()
        if getattr(runtime, 'patrol', None):
            runtime.patrol.stop()
        if getattr(runtime, 'status_leds', None):
            runtime.status_leds.close()
        if reg.motors:
            reg.motors.stop()
            close = getattr(reg.motors, 'close', None)
            if callable(close):
                close()
        if reg.switches:
            reg.switches.all_off()
        if reg.camera:
            reg.camera.stop()
        if reg.lights:
            reg.lights.off()
        if getattr(runtime, 'gamepad', None):
            runtime.gamepad.stop()
    finally:
        for obj_name in ['ultrasonic', 'ultrasonic_rear', 'lights', 'hat']:
            obj = getattr(reg, obj_name, None)
            close = getattr(obj, 'close', None)
            if callable(close):
                close()
