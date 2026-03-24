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

        distance_cm = None
        if reg.ultrasonic:
            try:
                distance_cm = reg.ultrasonic.read_cm()
            except AttributeError:
                try:
                    distance_cm = reg.ultrasonic.measure_distance_cm()
                except Exception:
                    distance_cm = None
            except Exception:
                distance_cm = None

        distance_rear_cm = None
        if reg.ultrasonic_rear:
            try:
                distance_rear_cm = reg.ultrasonic_rear.read_cm()
            except AttributeError:
                try:
                    distance_rear_cm = reg.ultrasonic_rear.measure_distance_cm()
                except Exception:
                    pass
            except Exception:
                pass

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
            'distance_rear_cm': distance_rear_cm,
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
            'patrol_enabled': state.patrol_enabled,
            'patrol': {
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
            },
            'gamepad_connected': False,
        }
        state.telemetry = snapshot
        return snapshot

    def get_snapshot(self) -> dict:
        if not self.runtime.state.telemetry:
            return self.poll_once()
        return dict(self.runtime.state.telemetry)
