from __future__ import annotations

import threading
import time
import random

from patrolbot.config import load_runtime_config, save_runtime_config


class PatrolService:
    DEFAULTS = {
        'enabled': False,
        'speed': 35,
        'reverse_speed': 28,
        'avoidance_distance_cm': 30,
        'reverse_time_sec': 0.8,
        'turn_time_sec': 0.9,
        'turn_mode': 'alternate',
        'scan_pan_min': 45,
        'scan_pan_max': 135,
        'scan_step': 2,
        'scan_tilt_angle': 90,
    }

    def __init__(self, runtime, logger):
        self.runtime = runtime
        self.logger = logger
        self._stop = threading.Event()
        self._thread = None
        self._config = self._normalize(dict(runtime.config.get('patrol', {})))
        self._scan_dir = 1
        self._last_turn = 'right'
        self._sync_state_basics()

    def _normalize(self, source: dict) -> dict:
        cfg = dict(self.DEFAULTS)
        cfg.update(source or {})
        cfg['enabled'] = bool(cfg.get('enabled', False))
        cfg['speed'] = max(0, min(100, int(cfg.get('speed', 35))))
        cfg['reverse_speed'] = max(0, min(100, int(cfg.get('reverse_speed', 28))))
        cfg['avoidance_distance_cm'] = max(5, int(cfg.get('avoidance_distance_cm', 30)))
        cfg['reverse_time_sec'] = max(0.0, min(5.0, float(cfg.get('reverse_time_sec', 0.8))))
        cfg['turn_time_sec'] = max(0.1, min(5.0, float(cfg.get('turn_time_sec', 0.9))))
        cfg['turn_mode'] = str(cfg.get('turn_mode', 'alternate')).strip().lower()
        cfg['scan_pan_min'] = int(cfg.get('scan_pan_min', 45))
        cfg['scan_pan_max'] = int(cfg.get('scan_pan_max', 135))
        if cfg['scan_pan_min'] > cfg['scan_pan_max']:
            cfg['scan_pan_min'], cfg['scan_pan_max'] = cfg['scan_pan_max'], cfg['scan_pan_min']
        cfg['scan_step'] = max(1, int(cfg.get('scan_step', 2)))
        cfg['scan_tilt_angle'] = int(cfg.get('scan_tilt_angle', 90))
        return cfg

    def _sync_state_basics(self):
        state = self.runtime.state
        state.patrol_enabled = bool(self._config.get('enabled', False))
        state.patrol_speed = self._config.get('speed', 35)
        state.patrol_mode = 'patrol'
        state.patrol_targets = []
        metrics = state.patrol_metrics if isinstance(state.patrol_metrics, dict) else {}
        metrics.setdefault('last_distance_cm', None)
        metrics.setdefault('obstacle_count', 0)
        metrics.setdefault('last_turn', None)
        metrics.setdefault('loop_hz', 0.0)
        state.patrol_metrics = metrics

    def get_config(self):
        return dict(self._config)

    def update_config(self, patch: dict, persist: bool = True):
        merged = dict(self._config)
        merged.update(patch or {})
        self._config = self._normalize(merged)
        self.runtime.config['patrol'] = dict(self._config)
        self._sync_state_basics()
        if persist:
            runtime_cfg = load_runtime_config()
            runtime_cfg['patrol'] = dict(self._config)
            save_runtime_config(runtime_cfg)
        return dict(self._config), []

    def enable(self):
        self.runtime.state.patrol_last_error = None
        self._config['enabled'] = True
        self.update_config({'enabled': True}, persist=True)
        self.runtime.state.mode = 'patrol'
        self.runtime.state.patrol_disable_reason = None
        self.logger.info('Patrol enabled')

    def disable(self, reason: str = 'user'):
        self._config['enabled'] = False
        self.update_config({'enabled': False}, persist=True)
        self._stop_motion()
        self.runtime.state.mode = 'idle'
        self.runtime.state.patrol_drive_state = 'stopped'
        self.runtime.state.patrol_disable_reason = reason
        self.logger.info('Patrol disabled: %s', reason)

    def toggle(self):
        if self.runtime.state.patrol_enabled:
            self.disable(reason='toggle')
        else:
            self.enable()

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name='patrol-service', daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._stop_motion()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def _stop_motion(self):
        motors = self.runtime.registry.motors
        steering = self.runtime.registry.steering
        if steering:
            steering.center()
            self.runtime.state.steering_angle = steering.angle
        if motors:
            motors.stop()
            self.runtime.state.motor_state = motors.state
            self.runtime.state.speed = motors.speed

    def _measure_distance(self):
        sensor = self.runtime.registry.ultrasonic
        if not sensor:
            return None
        try:
            if hasattr(sensor, 'read_cm'):
                distance = sensor.read_cm()
            else:
                distance = sensor.measure_distance_cm()
            if distance is None:
                return None
            self.runtime.state.patrol_last_error = None
            return round(float(distance), 1)
        except Exception as exc:
            self.runtime.state.patrol_last_error = f'ultrasonic read failed: {exc}'
            return None

    def _choose_turn_direction(self):
        mode = self._config.get('turn_mode', 'alternate')
        if mode == 'left':
            direction = 'left'
        elif mode == 'right':
            direction = 'right'
        elif mode == 'random':
            direction = random.choice(['left', 'right'])
        else:
            direction = 'left' if self._last_turn == 'right' else 'right'
        self._last_turn = direction
        self.runtime.state.patrol_metrics['last_turn'] = direction
        return direction

    def _turn_once(self, direction: str):
        steering = self.runtime.registry.steering
        motors = self.runtime.registry.motors
        if not steering or not motors:
            return
        try:
            if direction == 'left':
                steering.left()
            else:
                steering.right()
            self.runtime.state.steering_angle = steering.angle
            motors.forward(self._config.get('speed', 35))
            self.runtime.state.motor_state = motors.state
            self.runtime.state.speed = motors.speed
            self.runtime.state.patrol_drive_state = f'turning_{direction}'
            time.sleep(self._config.get('turn_time_sec', 0.9))
        finally:
            steering.center()
            self.runtime.state.steering_angle = steering.angle
            motors.stop()
            self.runtime.state.motor_state = motors.state
            self.runtime.state.speed = motors.speed

    def _reverse_once(self):
        motors = self.runtime.registry.motors
        if not motors:
            return
        self.runtime.state.patrol_drive_state = 'reversing'
        motors.backward(self._config.get('reverse_speed', 28))
        self.runtime.state.motor_state = motors.state
        self.runtime.state.speed = motors.speed
        time.sleep(self._config.get('reverse_time_sec', 0.8))
        motors.stop()
        self.runtime.state.motor_state = motors.state
        self.runtime.state.speed = motors.speed

    def _update_scan(self):
        servo = self.runtime.registry.camera_servo
        if not servo:
            return
        pan = int(getattr(servo, 'pan_angle', self.runtime.state.pan_angle))
        p_min = self._config.get('scan_pan_min', 45)
        p_max = self._config.get('scan_pan_max', 135)
        step = self._config.get('scan_step', 2)
        servo.set_tilt(self._config.get('scan_tilt_angle', 90))
        pan += step * self._scan_dir
        if pan <= p_min or pan >= p_max:
            self._scan_dir *= -1
            pan = max(p_min, min(p_max, pan))
        servo.set_pan(pan)
        self.runtime.state.pan_angle = servo.pan_angle
        self.runtime.state.tilt_angle = servo.tilt_angle

    def _loop(self):
        tick_history = []
        while not self._stop.is_set():
            t0 = time.monotonic()
            state = self.runtime.state
            motors = self.runtime.registry.motors
            steering = self.runtime.registry.steering
            if not state.patrol_enabled:
                if state.patrol_drive_state != 'stopped':
                    state.patrol_drive_state = 'stopped'
                self._stop_motion()
                self._update_scan()
                time.sleep(0.1)
                continue

            if motors is None or steering is None:
                state.patrol_last_error = 'missing motion hardware'
                state.patrol_drive_state = 'fault'
                time.sleep(0.25)
                continue

            distance = self._measure_distance()
            state.patrol_metrics['last_distance_cm'] = distance

            try:
                if distance is not None and 0 < distance < self._config.get('avoidance_distance_cm', 30):
                    state.patrol_metrics['obstacle_count'] = int(state.patrol_metrics.get('obstacle_count', 0)) + 1
                    state.patrol_drive_state = 'obstacle_detected'
                    motors.stop()
                    state.motor_state = motors.state
                    state.speed = motors.speed
                    time.sleep(0.1)
                    self._reverse_once()
                    direction = self._choose_turn_direction()
                    self._turn_once(direction)
                    state.patrol_drive_state = 'recovering'
                    time.sleep(0.15)
                else:
                    steering.center()
                    state.steering_angle = steering.angle
                    state.patrol_drive_state = 'forward'
                    motors.forward(self._config.get('speed', 35))
                    state.motor_state = motors.state
                    state.speed = motors.speed
                    time.sleep(0.05)
            except RuntimeError as exc:
                state.patrol_last_error = str(exc)
                state.patrol_drive_state = 'locked'
                self._stop_motion()
                time.sleep(0.2)
            except Exception as exc:
                state.patrol_last_error = f'patrol loop error: {exc}'
                self.logger.exception('Patrol loop error')
                state.patrol_drive_state = 'fault'
                self._stop_motion()
                time.sleep(0.25)
            finally:
                self._update_scan()
                dt = max(0.0001, time.monotonic() - t0)
                tick_history.append(dt)
                if len(tick_history) > 20:
                    tick_history.pop(0)
                avg = sum(tick_history) / len(tick_history)
                state.patrol_metrics['loop_hz'] = round(1.0 / avg, 2)
