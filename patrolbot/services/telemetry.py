from __future__ import annotations

import threading
import time


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

    def _sensor_entry(self, slot: str) -> dict:
        return self.runtime.state.sensor_status.setdefault(slot, {
            'configured': False,
            'initialized': False,
            'detected': False,
            'healthy': False,
            'enabled': False,
            'use_mode': 'off',
            'available': False,
            'last_distance_cm': None,
            'last_good_read_ts': None,
            'last_probe_ts': None,
            'last_error': None,
            'details': None,
        })

    def _read_sensor(self, registry_attr: str, slot: str):
        sensor = getattr(self.runtime.registry, registry_attr, None)
        entry = self._sensor_entry(slot)
        if not sensor:
            entry['initialized'] = False
            entry['healthy'] = False
            entry['available'] = bool(entry.get('detected'))
            return None
        try:
            distance = sensor.read_cm() if hasattr(sensor, 'read_cm') else sensor.measure_distance_cm()
            entry['initialized'] = True
            if distance is None:
                entry['healthy'] = False
                return None
            entry['detected'] = True
            entry['healthy'] = True
            entry['available'] = True
            entry['last_distance_cm'] = distance
            entry['last_good_read_ts'] = time.time()
            entry['last_error'] = None
            return round(float(distance), 1)
        except Exception as exc:
            entry['initialized'] = True
            entry['healthy'] = False
            entry['last_error'] = str(exc)
            return None

    def poll_once(self) -> dict:
        reg = self.runtime.registry
        state = self.runtime.state

        battery_voltage = reg.battery.read_voltage() if reg.battery else None
        battery_status = reg.battery.get_status(battery_voltage) if reg.battery else 'unknown'
        battery_percent = reg.battery.estimate_percent(battery_voltage) if reg.battery else None

        distance_cm = None
        front_status = self._sensor_entry('front_ultrasonic')
        if front_status.get('enabled') and front_status.get('use_mode') != 'off':
            distance_cm = self._read_sensor('ultrasonic', 'front_ultrasonic')

        distance_rear_cm = None
        rear_status = self._sensor_entry('rear_ultrasonic')
        if rear_status.get('enabled') and rear_status.get('use_mode') != 'off':
            distance_rear_cm = self._read_sensor('ultrasonic_rear', 'rear_ultrasonic')

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

        if self.runtime.network_status is not None:
            if not getattr(self, '_network_next_due', None) or time.time() >= self._network_next_due:
                net = self.runtime.network_status.get_status()
                state.network_connected = bool(net.get('connected'))
                state.network_ssid = net.get('ssid')
                state.network_ip = net.get('ip')
                state.network_last_error = net.get('error')
                self._network_next_due = time.time() + 10.0

        if self.runtime.status_leds is not None:
            self.runtime.status_leds.set_battery_critical(battery_status == 'critical')
            self.runtime.status_leds.apply_runtime_status(self.runtime)

        if self.runtime.snapshots is not None:
            state.snapshot_count = len(self.runtime.snapshots.list_snapshots(limit=9999))

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
            'system_status': state.system_status,
            'network': {
                'connected': state.network_connected,
                'ssid': state.network_ssid,
                'ip': state.network_ip,
                'last_error': state.network_last_error,
            },
            'sensors': {
                'front_ultrasonic': dict(front_status),
                'rear_ultrasonic': dict(rear_status),
            },
            'vision': {
                'enabled': state.vision_enabled,
                'detector': state.vision_detector,
                'detector_status': state.vision_detector_status,
                'detector_available': state.vision_detector_available,
                'last_error': state.vision_last_error,
                'disable_reason': state.vision_disable_reason,
            },
            'patrol_enabled': state.patrol_enabled,
            'patrol': {
                'enabled': state.patrol_enabled,
                'mode': state.patrol_mode,
                'drive_state': state.patrol_drive_state,
                'speed': state.patrol_speed,
                'targets': state.patrol_targets,
                'detect_count': state.patrol_detect_count,
                'last_detected': state.patrol_last_detected,
                'last_event': state.patrol_last_event,
                'event_count': state.patrol_event_count,
                'metrics': state.patrol_metrics,
                'disable_reason': state.patrol_disable_reason,
                'last_error': state.patrol_last_error,
            },
            'snapshots': {
                'count': state.snapshot_count,
                'last_saved': state.snapshot_last_saved,
            },
            'gamepad_connected': False,
        }
        state.telemetry = snapshot
        return snapshot

    def get_snapshot(self) -> dict:
        if not self.runtime.state.telemetry:
            return self.poll_once()
        return dict(self.runtime.state.telemetry)
