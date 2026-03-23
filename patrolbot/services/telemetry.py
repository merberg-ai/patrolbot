from __future__ import annotations

import threading


class TelemetryService:
    def __init__(self, runtime, logger):
        self.runtime = runtime
        self.logger = logger
        self._thread = None
        self._stop_event = threading.Event()
        self.poll_interval_s = float(runtime.config.get('telemetry', {}).get('poll_interval_s', 2.0))

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, name='patrolbot-telemetry', daemon=True)
        self._thread.start()
        self.logger.info('Telemetry background polling started at %.2fs interval', self.poll_interval_s)

    def stop(self) -> None:
        self._stop_event.set()
        self._thread = None

    def _loop(self) -> None:
        while not self._stop_event.wait(self.poll_interval_s):
            try:
                self.poll_once()
            except Exception as exc:
                self.logger.warning('Telemetry background poll failed: %s', exc)

    def poll_once(self) -> dict:
        reg = self.runtime.registry
        state = self.runtime.state

        battery_voltage = reg.battery.read_voltage() if reg.battery else None
        battery_status = reg.battery.get_status(battery_voltage) if reg.battery else 'unknown'
        battery_percent = reg.battery.estimate_percent(battery_voltage) if reg.battery else None
        distance_cm = reg.ultrasonic.read_cm() if reg.ultrasonic else None

        steering_angle = getattr(reg.steering, 'angle', state.steering_angle) if reg.steering else state.steering_angle
        pan_angle = getattr(reg.camera_servo, 'pan_angle', state.pan_angle) if reg.camera_servo else state.pan_angle
        tilt_angle = getattr(reg.camera_servo, 'tilt_angle', state.tilt_angle) if reg.camera_servo else state.tilt_angle

        state.steering_angle = steering_angle
        state.pan_angle = pan_angle
        state.tilt_angle = tilt_angle

        if reg.motors:
            reg.motors.set_lockout(battery_status == 'critical', reason='battery critical')
            state.motor_state = reg.motors.state
            state.speed = reg.motors.speed
            state.motion_locked = reg.motors.motion_locked
            state.estop_latched = reg.motors.estop_latched

        if self.runtime.status_leds is not None:
            self.runtime.status_leds.set_battery_critical(battery_status == 'critical')

        motor_state = reg.motors.get_state() if reg.motors else {
            'state': state.motor_state,
            'speed': state.speed,
            'motion_locked': state.motion_locked,
            'estop_latched': state.estop_latched,
            'last_command_age_s': None,
            'timeout_s': None,
        }

        snapshot = {
            'battery_voltage': battery_voltage,
            'battery_status': battery_status,
            'battery_percent': battery_percent,
            'distance_cm': distance_cm,
            'distance_status': 'ok' if distance_cm is not None else 'unknown',
            'motor_state': motor_state['state'],
            'speed': motor_state['speed'],
            'motion_locked': motor_state['motion_locked'],
            'estop_latched': motor_state['estop_latched'],
            'last_command_age_s': motor_state['last_command_age_s'],
            'motor_timeout_s': motor_state['timeout_s'] if motor_state['timeout_s'] is not None else self.runtime.config.get('motors', {}).get('command_timeout_s'),
            'steering_angle': steering_angle,
            'pan_angle': pan_angle,
            'tilt_angle': tilt_angle,
            'led_state': state.led_state,
            'led_custom': state.led_custom,
            'mode': state.mode,
            'tracking_enabled': state.tracking_enabled,
            'tracking': {
                'enabled': state.tracking_enabled,
                'mode': state.tracking_mode,
                'detector': state.tracking_detector,
                'detector_status': state.tracking_detector_status,
                'detector_available': state.tracking_detector_available,
                'target_acquired': state.tracking_target_acquired,
                'target_box': state.tracking_box,
                'target_label': state.tracking_target_label,
                'target_confidence': state.tracking_target_confidence,
                'scan_active': state.tracking_scan_active,
                'frame_size': state.tracking_frame_size,
                'fps_actual': state.tracking_fps_actual,
                'metrics': state.tracking_metrics,
                'disable_reason': state.tracking_disable_reason,
            },
            'gamepad_connected': bool(getattr(self.runtime, 'gamepad', None) and getattr(self.runtime.gamepad, 'device', None) is not None),

        }
        state.telemetry = snapshot
        return snapshot

    def get_snapshot(self) -> dict:
        return self.poll_once()
