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
        'scan_on_boot': True,
        'scan_pan_min': 45,
        'scan_pan_max': 135,
        'scan_step': 2,
        'scan_tilt_angle': 90,
        'memory_max_repeats': 3,
        'trapped_timeout_s': 10.0,
        
        # New Targeting Features
        'action_on_detect': 'follow',  # 'follow', 'log', 'ignore'
        'target_classes': ['person', 'dog', 'cat'],
        'save_screenshots': True,
        'obstacle_classes': ['chair', 'couch', 'table', 'dining table', 'potted plant', 'tv', 'bench'],
        'log_only_classes': [],
        'target_min_area_ratio': 0.01,
        'obstacle_min_area_ratio': 0.05,
        'follow_obstacle_steer_bias': 0.18,
        'follow_reacquire_hold_s': 0.75,
        
        # Follow Mode PID Configuration
        'follow_target_distance_cm': 60,
        'follow_stop_distance_cm': 25,
        'follow_drive_speed': 30,
        'follow_steer_gain': 0.6,
        'follow_steer_smoothing_alpha': 0.45,
        'follow_pan_gain': 0.08,
        'follow_use_ultrasonic': True,
        'follow_image_size_ratio_target': 0.25,
        'acquire_confirm_frames': 3,
        'lost_timeout_s': 1.5,
        'log_cooldown_sec': 5.0,
        'obstacle_hold_time_s': 0.5,
    }

    def __init__(self, runtime, logger):
        self.runtime = runtime
        self.logger = logger
        self._stop = threading.Event()
        self._thread = None
        self._config = self._normalize(dict(runtime.config.get('patrol', {})))
        self._scan_dir = 1
        self._last_turn = 'right'
        self._scan_interval_idle = 0.6
        self._scan_interval_active = 0.25
        self._last_scan_ts = 0.0
        self._consecutive_blocks = 0
        self._last_escape_ts = time.monotonic()
        self._last_log_ts = 0.0
        self._last_steer_angle = None
        self._follow_distance_ema = None
        self._last_target_signature = None
        self._last_target_ts = 0.0
        self._last_obstacle_label = None
        self._behavior_state = 'patrol'
        self._target_seen_streak = 0
        self._obstacle_clear_since = None
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
        cfg['scan_on_boot'] = bool(cfg.get('scan_on_boot', True))
        cfg['scan_pan_min'] = int(cfg.get('scan_pan_min', 45))
        cfg['scan_pan_max'] = int(cfg.get('scan_pan_max', 135))
        if cfg['scan_pan_min'] > cfg['scan_pan_max']:
            cfg['scan_pan_min'], cfg['scan_pan_max'] = cfg['scan_pan_max'], cfg['scan_pan_min']
        cfg['scan_step'] = max(1, int(cfg.get('scan_step', 2)))
        cfg['scan_tilt_angle'] = int(cfg.get('scan_tilt_angle', 90))
        cfg['memory_max_repeats'] = max(1, int(cfg.get('memory_max_repeats', 3)))
        cfg['trapped_timeout_s'] = max(1.0, float(cfg.get('trapped_timeout_s', 10.0)))
        
        cfg['action_on_detect'] = str(cfg.get('action_on_detect', 'follow')).lower()
        if cfg['action_on_detect'] not in {'follow', 'log', 'ignore'}:
            cfg['action_on_detect'] = 'follow'
            
        raw_classes = cfg.get('target_classes', [])
        if isinstance(raw_classes, str):
            cfg['target_classes'] = [x.strip().lower() for x in raw_classes.split(',') if x.strip()]
        else:
            cfg['target_classes'] = [str(x).lower() for x in raw_classes]

        raw_obstacle_classes = cfg.get('obstacle_classes', [])
        if isinstance(raw_obstacle_classes, str):
            cfg['obstacle_classes'] = [x.strip().lower() for x in raw_obstacle_classes.split(',') if x.strip()]
        else:
            cfg['obstacle_classes'] = [str(x).lower() for x in raw_obstacle_classes if str(x).strip()]

        raw_log_only_classes = cfg.get('log_only_classes', [])
        if isinstance(raw_log_only_classes, str):
            cfg['log_only_classes'] = [x.strip().lower() for x in raw_log_only_classes.split(',') if x.strip()]
        else:
            cfg['log_only_classes'] = [str(x).lower() for x in raw_log_only_classes if str(x).strip()]

        cfg['save_screenshots'] = bool(cfg.get('save_screenshots', True))
        cfg['target_min_area_ratio'] = max(0.0, min(1.0, float(cfg.get('target_min_area_ratio', 0.01))))
        cfg['obstacle_min_area_ratio'] = max(0.0, min(1.0, float(cfg.get('obstacle_min_area_ratio', 0.05))))
        cfg['follow_obstacle_steer_bias'] = max(0.0, min(1.0, float(cfg.get('follow_obstacle_steer_bias', 0.18))))
        cfg['follow_reacquire_hold_s'] = max(0.0, min(5.0, float(cfg.get('follow_reacquire_hold_s', 0.75))))
        cfg['follow_target_distance_cm'] = max(10, int(cfg.get('follow_target_distance_cm', 60)))
        cfg['follow_stop_distance_cm'] = max(5, int(cfg.get('follow_stop_distance_cm', 25)))
        cfg['follow_drive_speed'] = max(0, min(100, int(cfg.get('follow_drive_speed', 30))))
        cfg['follow_steer_gain'] = max(0.0, min(5.0, float(cfg.get('follow_steer_gain', 0.6))))
        cfg['follow_steer_smoothing_alpha'] = max(0.0, min(1.0, float(cfg.get('follow_steer_smoothing_alpha', 0.45))))
        cfg['follow_pan_gain'] = max(0.0, min(2.0, float(cfg.get('follow_pan_gain', 0.08))))
        cfg['follow_use_ultrasonic'] = bool(cfg.get('follow_use_ultrasonic', True))
        cfg['follow_image_size_ratio_target'] = max(0.01, min(1.0, float(cfg.get('follow_image_size_ratio_target', 0.25))))
        cfg['acquire_confirm_frames'] = max(1, min(20, int(cfg.get('acquire_confirm_frames', 3))))
        cfg['lost_timeout_s'] = max(0.1, min(10.0, float(cfg.get('lost_timeout_s', 1.5))))
        cfg['log_cooldown_sec'] = max(0.5, min(60.0, float(cfg.get('log_cooldown_sec', 5.0))))
        cfg['obstacle_hold_time_s'] = max(0.0, min(5.0, float(cfg.get('obstacle_hold_time_s', 0.5))))
        return cfg

    def _sync_state_basics(self):
        state = self.runtime.state
        state.patrol_enabled = bool(self._config.get('enabled', False))
        state.patrol_speed = self._config.get('speed', 35)
        state.patrol_mode = getattr(self, '_behavior_state', 'patrol')
        state.patrol_targets = self._config.get('target_classes', [])
        state.patrol_obstacles = self._config.get('obstacle_classes', [])
        state.patrol_log_only = self._config.get('log_only_classes', [])
        metrics = state.patrol_metrics if isinstance(state.patrol_metrics, dict) else {}
        metrics.setdefault('last_distance_cm', None)
        metrics.setdefault('last_rear_distance_cm', None)
        metrics.setdefault('obstacle_count', 0)
        metrics.setdefault('last_turn', None)
        metrics.setdefault('loop_hz', 0.0)
        metrics.setdefault('last_target_score', None)
        state.patrol_metrics = metrics
        state.patrol_last_event = state.patrol_last_event if isinstance(state.patrol_last_event, dict) else None
        state.patrol_recent_events = list(state.patrol_recent_events or [])[-25:]
        metrics['target_seen_streak'] = int(metrics.get('target_seen_streak', 0) or 0)
        metrics['target_lost_age_s'] = metrics.get('target_lost_age_s')
        metrics['obstacle_clear_age_s'] = metrics.get('obstacle_clear_age_s')

    def get_config(self):
        return dict(self._config)

    def _record_event(self, event: str, **fields):
        state = self.runtime.state
        payload = {'ts': round(time.time(), 3), 'event': event}
        payload.update({k: v for k, v in fields.items() if v is not None})
        state.patrol_last_event = payload
        state.patrol_event_count = int(getattr(state, 'patrol_event_count', 0) or 0) + 1
        events = list(getattr(state, 'patrol_recent_events', []) or [])
        events.append(payload)
        state.patrol_recent_events = events[-25:]
        return payload

    def _vision_patch_for_patrol(self) -> dict:
        wanted = []
        for bucket in ('target_classes', 'obstacle_classes', 'log_only_classes'):
            for item in (self._config.get(bucket) or []):
                label = str(item).strip().lower()
                if label and label not in wanted:
                    wanted.append(label)
        return {
            'enabled': True,
            'enable_yolo': True,
            'detector': 'yolo',
            'yolo_classes': wanted,
        }

    def _ensure_patrol_vision(self):
        vision = getattr(self.runtime, 'vision', None)
        if not vision:
            return
        desired = self._vision_patch_for_patrol()
        current = vision.get_config() if hasattr(vision, 'get_config') else {}
        needs_update = any(current.get(k) != v for k, v in desired.items())
        if needs_update:
            vision.update_config(desired, persist=True)
            self.logger.info('Patrol aligned vision for YOLO target mode: detector=%s classes=%s', desired['detector'], ','.join(desired['yolo_classes']) or 'all')
        if not getattr(self.runtime.state, 'vision_enabled', False):
            vision.enable()

    def update_config(self, patch: dict, persist: bool = True):
        merged = dict(self._config)
        merged.update(patch or {})
        self._config = self._normalize(merged)
        self.runtime.config['patrol'] = dict(self._config)
        self._sync_state_basics()

        if self._config.get('enabled'):
            self._ensure_patrol_vision()

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
        self._ensure_patrol_vision()
        self._set_behavior_state('patrol')
        self._record_event('patrol_enabled', targets=list(self._config.get('target_classes', [])))
        self.logger.info('Patrol enabled')

    def disable(self, reason: str = 'user'):
        self._config['enabled'] = False
        self.update_config({'enabled': False}, persist=True)
        self._stop_motion()
        self.runtime.state.mode = 'idle'
        self.runtime.state.patrol_drive_state = 'idle'
        self.runtime.state.patrol_disable_reason = reason
        self._set_behavior_state('idle')
        self._record_event('patrol_disabled', reason=reason)
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

    def _sensor_enabled(self, slot: str) -> bool:
        entry = self.runtime.state.sensor_status.get(slot, {})
        return bool(entry.get('enabled')) and entry.get('use_mode') != 'off' and entry.get('detected')

    def _measure_distance(self):
        if not self._sensor_enabled('front_ultrasonic'):
            return None
        sensor = self.runtime.registry.ultrasonic
        if not sensor:
            return None
        try:
            distance = sensor.read_cm() if hasattr(sensor, 'read_cm') else sensor.measure_distance_cm()
            if distance is None:
                return None
            self.runtime.state.patrol_last_error = None
            self.runtime.state.sensor_status['front_ultrasonic']['last_distance_cm'] = distance
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
                val = steering.max_angle if getattr(steering, 'invert', False) else steering.min_angle
                steering.set_angle(val)
            else:
                val = steering.min_angle if getattr(steering, 'invert', False) else steering.max_angle
                steering.set_angle(val)
            self.runtime.state.steering_angle = steering.angle
            motors.forward(self._config.get('speed', 35))
            self.runtime.state.motor_state = motors.state
            self.runtime.state.speed = motors.speed
            self.runtime.state.patrol_drive_state = f'turning_{direction}'
            time.sleep(self._config.get('turn_time_sec', 0.9))
        finally:
             # Do not center immediately to keep turning inertia
            motors.stop()
            self.runtime.state.motor_state = motors.state
            self.runtime.state.speed = motors.speed

    def _measure_rear_distance(self):
        if not self._sensor_enabled('rear_ultrasonic'):
            return None
        sensor = self.runtime.registry.ultrasonic_rear
        if not sensor:
            return None
        try:
            val = sensor.read_cm()
            self.runtime.state.sensor_status['rear_ultrasonic']['last_distance_cm'] = val
            return val
        except Exception:
            return None

    def _frame_size(self):
        frame_size = self.runtime.state.vision_frame_size or (640, 480)
        if isinstance(frame_size, dict):
            return int(frame_size.get('width', 640)), int(frame_size.get('height', 480))
        return int(frame_size[0]), int(frame_size[1])

    def _detection_area_ratio(self, det, frame_w: int, frame_h: int) -> float:
        area = float(getattr(det, 'area', getattr(det, 'w', 0) * getattr(det, 'h', 0)) or 0.0)
        return area / max(1.0, float(frame_w * frame_h))

    def _label_in(self, det, labels) -> bool:
        label = str(getattr(det, 'label', '') or '').strip().lower()
        return bool(label and label in set(labels or []))

    def _get_detection_buckets(self):
        target_classes = [str(x).lower() for x in (self._config.get('target_classes') or []) if str(x).strip()]
        obstacle_classes = [str(x).lower() for x in (self._config.get('obstacle_classes') or []) if str(x).strip()]
        log_only_classes = [str(x).lower() for x in (self._config.get('log_only_classes') or []) if str(x).strip()]
        return target_classes, obstacle_classes, log_only_classes

    def _select_loggable_target(self):
        target_classes, _, log_only_classes = self._get_detection_buckets()
        interesting = list(dict.fromkeys([*target_classes, *log_only_classes]))
        if not interesting:
            return None
        frame_w, frame_h = self._frame_size()
        min_area = float(self._config.get('target_min_area_ratio', 0.01))
        detections = getattr(self.runtime.state, 'vision_detections', []) or []
        candidates = []
        for det in detections:
            label = str(getattr(det, 'label', '') or '').lower()
            if label not in interesting:
                continue
            area_ratio = self._detection_area_ratio(det, frame_w, frame_h)
            if area_ratio < min_area:
                continue
            candidates.append((self._score_target(det, frame_w, frame_h), det))
        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0][1]

    def _get_yolo_obstacle(self) -> dict | None:
        if not self.runtime.state.vision_enabled:
            return None
        detections = getattr(self.runtime.state, 'vision_detections', [])
        if not detections:
            return None

        frame_w, frame_h = self._frame_size()
        min_area_ratio = float(self._config.get('obstacle_min_area_ratio', 0.05))
        target_classes, obstacle_classes, _ = self._get_detection_buckets()

        obstacles = []
        for det in detections:
            label = str(getattr(det, 'label', '') or '').lower()
            if label in target_classes:
                continue
            if obstacle_classes and label not in obstacle_classes:
                continue

            area_ratio = self._detection_area_ratio(det, frame_w, frame_h)
            if area_ratio < min_area_ratio:
                continue

            center_x = float(getattr(det, 'center_x', frame_w / 2.0))
            center_ratio = center_x / max(1.0, frame_w)
            pan = self.runtime.state.pan_angle
            if pan > 105:
                is_right, is_left = True, False
            elif pan < 75:
                is_right, is_left = False, True
            else:
                is_right = center_ratio > 0.6
                is_left = center_ratio < 0.4

            obstacles.append({
                'area_ratio': area_ratio,
                'is_right': is_right,
                'is_left': is_left,
                'label': label or 'unknown',
            })

        if not obstacles:
            return None

        return max(obstacles, key=lambda o: o['area_ratio'])



    def _set_behavior_state(self, state_name: str, **fields):
        state_name = str(state_name or 'patrol').strip().lower()
        previous = getattr(self, '_behavior_state', 'patrol')
        self._behavior_state = state_name
        self.runtime.state.patrol_mode = state_name
        self.runtime.state.patrol_metrics['target_seen_streak'] = int(self._target_seen_streak or 0)
        if previous != state_name:
            self._record_event('state_changed', previous=previous, state=state_name, **fields)
        return state_name

    def _front_obstacle_info(self, distance, target=None):
        avoid_dist = float(self._config.get('avoidance_distance_cm', 30))
        yolo_obs = self._get_yolo_obstacle()
        hard = False
        soft_dir = None
        label = None
        area_ratio = None

        if distance is not None:
            if distance < avoid_dist:
                hard = True
                label = 'ultrasonic'
            elif distance < avoid_dist * 1.8:
                soft_dir = self._last_turn
                label = label or 'ultrasonic_soft'

        if yolo_obs:
            area_ratio = round(float(yolo_obs.get('area_ratio', 0.0)), 3)
            label = yolo_obs.get('label') or label
            if area_ratio > 0.25:
                hard = True
                if not soft_dir:
                    soft_dir = 'left' if yolo_obs['is_right'] else 'right'
            else:
                if yolo_obs['is_right']:
                    soft_dir = 'left'
                elif yolo_obs['is_left']:
                    soft_dir = 'right'
                elif not soft_dir:
                    soft_dir = self._last_turn

        return {
            'hard': bool(hard),
            'soft_dir': soft_dir,
            'label': label,
            'area_ratio': area_ratio,
            'distance_cm': distance,
        }

    def _handle_hard_obstacle(self, obstacle):
        state = self.runtime.state
        motors = self.runtime.registry.motors
        state.patrol_metrics['obstacle_count'] = int(state.patrol_metrics.get('obstacle_count', 0)) + 1
        label = obstacle.get('label') or 'unknown'
        if label != self._last_obstacle_label:
            self._record_event('obstacle_detected', label=label, area_ratio=obstacle.get('area_ratio'), distance_cm=obstacle.get('distance_cm'))
            self._last_obstacle_label = label
        self._set_behavior_state('avoid_front', label=label)
        state.patrol_drive_state = 'obstacle_detected'
        if motors:
            motors.stop()
            state.motor_state = motors.state
            state.speed = motors.speed
        time.sleep(0.1)

        now = time.monotonic()
        if now - self._last_escape_ts < 3.0:
            self._consecutive_blocks += 1
        else:
            self._consecutive_blocks = 1
        self._last_escape_ts = now
        self._obstacle_clear_since = None

        if self._consecutive_blocks > self._config.get('memory_max_repeats', 3):
            self.logger.warning('Consecutive blocks max reached (%d), entered trapped state', self._consecutive_blocks)
            self._set_behavior_state('trapped', repeats=self._consecutive_blocks)
            self._record_event('trapped_entered', repeats=self._consecutive_blocks)
            state.patrol_drive_state = 'trapped'
            self._stop_motion()
            return

        self._reverse_once()
        direction = obstacle.get('soft_dir') or self._choose_turn_direction()
        self._turn_once(direction)
        self._set_behavior_state('recovering', direction=direction)
        state.patrol_drive_state = 'recovering'
        time.sleep(0.15)

    def _target_signature(self, target):
        return (
            getattr(target, 'label', 'unknown'),
            int(getattr(target, 'center_x', 0) / 20),
            int(getattr(target, 'center_y', 0) / 20),
            int(getattr(target, 'w', 0) / 20),
            int(getattr(target, 'h', 0) / 20),
        )

    def _score_target(self, det, frame_w: int, frame_h: int) -> float:
        conf = float(getattr(det, 'confidence', 0.0) or 0.0)
        area = float(getattr(det, 'area', getattr(det, 'w', 0) * getattr(det, 'h', 0)) or 0.0)
        frame_area = max(1.0, float(frame_w * frame_h))
        area_ratio = area / frame_area
        center_x = float(getattr(det, 'center_x', frame_w / 2.0))
        center_y = float(getattr(det, 'center_y', frame_h / 2.0))
        norm_dx = abs(center_x - (frame_w / 2.0)) / max(1.0, frame_w / 2.0)
        norm_dy = abs(center_y - (frame_h / 2.0)) / max(1.0, frame_h / 2.0)
        center_bonus = max(0.0, 1.0 - ((norm_dx * 0.7) + (norm_dy * 0.3)))
        score = (conf * 2.5) + (area_ratio * 6.0) + center_bonus
        signature = self._target_signature(det)
        if self._last_target_signature and signature[0] == self._last_target_signature[0]:
            if signature == self._last_target_signature:
                score += 2.5
            else:
                dx = abs(signature[1] - self._last_target_signature[1])
                dy = abs(signature[2] - self._last_target_signature[2])
                if dx <= 2 and dy <= 2:
                    score += 1.2
        return score

    def _select_target(self):
        target_classes, _, _ = self._get_detection_buckets()
        if not target_classes:
            return None
        frame_w, frame_h = self._frame_size()
        min_area = float(self._config.get('target_min_area_ratio', 0.01))
        vision = getattr(self.runtime, 'vision', None)
        tracker_target = vision.get_latest_target() if vision and hasattr(vision, 'get_latest_target') else None
        candidates = []
        if tracker_target and str(getattr(tracker_target, 'label', '')).lower() in target_classes:
            if self._detection_area_ratio(tracker_target, frame_w, frame_h) >= min_area:
                candidates.append(tracker_target)
        detections = vision.get_latest_detections() if vision and hasattr(vision, 'get_latest_detections') else getattr(self.runtime.state, 'vision_detections', [])
        for det in detections or []:
            if str(getattr(det, 'label', '')).lower() in target_classes:
                if self._detection_area_ratio(det, frame_w, frame_h) >= min_area:
                    candidates.append(det)
        if not candidates:
            self.runtime.state.patrol_metrics['last_target_score'] = None
            return None
        scored = [(self._score_target(det, frame_w, frame_h), det) for det in candidates]
        scored.sort(key=lambda item: item[0], reverse=True)
        best_score, best = scored[0]
        self.runtime.state.patrol_metrics['last_target_score'] = round(float(best_score), 3)
        return best

    def _reverse_once(self):
        motors = self.runtime.registry.motors
        if not motors:
            return
        self.runtime.state.patrol_drive_state = 'reversing'

        rear_dist = self._measure_rear_distance()
        self.runtime.state.patrol_metrics['last_rear_distance_cm'] = rear_dist
        if rear_dist is not None and rear_dist < 15.0:
            self._record_event('reverse_blocked', distance_cm=round(float(rear_dist),1))
            self.logger.info('Rear blocked (%.1fcm), skipping reverse', rear_dist)
            return

        self._record_event('reverse_started', distance_cm=rear_dist)
        motors.backward(self._config.get('reverse_speed', 28))
        self.runtime.state.motor_state = motors.state
        self.runtime.state.speed = motors.speed

        total_time = self._config.get('reverse_time_sec', 0.8)
        steps = int(total_time / 0.1) + 1
        for _ in range(steps):
            time.sleep(0.1)
            d = self._measure_rear_distance()
            if d is not None and d < 10.0:
                self.logger.info('Rear blocked dynamically, stopping reverse')
                break

        motors.stop()
        self.runtime.state.motor_state = motors.state
        self.runtime.state.speed = motors.speed

    def _update_scan(self, force: bool = False):
        servo = self.runtime.registry.camera_servo
        if not servo:
            return

        now = time.monotonic()
        interval = self._scan_interval_active if self.runtime.state.patrol_enabled else self._scan_interval_idle
        if not force and (now - self._last_scan_ts) < interval:
            return
        self._last_scan_ts = now

        pan = int(getattr(servo, 'pan_angle', self.runtime.state.pan_angle))
        p_min = self._config.get('scan_pan_min', 45)
        p_max = self._config.get('scan_pan_max', 135)
        step = self._config.get('scan_step', 2)
        target_tilt = int(self._config.get('scan_tilt_angle', 90))

        if getattr(servo, 'tilt_angle', None) != target_tilt:
            servo.set_tilt(target_tilt)

        pan += step * self._scan_dir
        if pan <= p_min or pan >= p_max:
            self._scan_dir *= -1
            pan = max(p_min, min(p_max, pan))

        if getattr(servo, 'pan_angle', None) != pan:
            servo.set_pan(pan)

        self.runtime.state.pan_angle = servo.pan_angle
        self.runtime.state.tilt_angle = servo.tilt_angle
        
    def _ema(self, previous, current, alpha: float):
        if current is None:
            return previous
        if previous is None:
            return float(current)
        alpha = max(0.0, min(1.0, float(alpha)))
        return (alpha * float(current)) + ((1.0 - alpha) * float(previous))
        
    def _log_target(self, target):
        self.runtime.state.patrol_drive_state = 'investigating'
        self.runtime.state.patrol_last_detected = target.label
        self.runtime.state.patrol_detect_count += 1

        now = time.time()
        if (now - self._last_log_ts) < float(self._config.get('log_cooldown_sec', 5.0)):
            return
        self._last_log_ts = now

        conf = round(float(getattr(target, 'confidence', 1.0) or 1.0), 3)
        self.logger.info('Target Detected: %s (Conf: %.2f)', target.label, conf)
        self._record_event('target_logged', label=target.label, confidence=conf)
        self._stop_motion()

        if self._config.get('save_screenshots'):
            snapshots = getattr(self.runtime, 'snapshots', None)
            if snapshots:
                try:
                    snap = snapshots.take_snapshot(reason=f'Target {target.label} detected', label=target.label)
                    self._record_event('snapshot_saved', label=target.label, snapshot=snap.get('name'))
                except Exception as e:
                    self.logger.error('Failed to save snapshot: %s', e)
                    self._record_event('snapshot_failed', label=target.label, error=str(e))

        time.sleep(2.0)

    def _follow_target(self, target, distance):
        cfg = self._config
        servo = self.runtime.registry.camera_servo
        motors = self.runtime.registry.motors
        steering = self.runtime.registry.steering
        
        if not target:
            return

        self._set_behavior_state('follow', label=getattr(target, 'label', None))
        self.runtime.state.patrol_drive_state = 'following'
        self.runtime.state.patrol_last_detected = target.label
        
        frame_size = self.runtime.state.vision_frame_size or (640, 480)
        frame_w, frame_h = frame_size

        # 1. Steer the Camera to keep the object centered (Pan only to preserve tilt)
        if servo:
            pan_error = target.center_x - (frame_w / 2.0)
            pan = servo.pan_angle
            pan_gain = float(cfg.get('follow_pan_gain', 0.08))
            pan -= int(round(pan_error * pan_gain))
            pan = max(getattr(servo, 'pan_min', 40), min(getattr(servo, 'pan_max', 140), pan))
            servo.set_pan(pan)
            self.runtime.state.pan_angle = pan

        # 2. Steer Wheels
        if steering:
             center = getattr(steering, 'center_angle', 90)
             min_a = getattr(steering, 'min_angle', 45)
             max_a = getattr(steering, 'max_angle', 135)
             steer_gain = float(cfg.get('follow_steer_gain', 0.6))
             steer_alpha = float(cfg.get('follow_steer_smoothing_alpha', 0.45))
             
             err_x = float(target.center_x - (frame_w / 2.0))
             norm_err = err_x / max(1.0, frame_w / 2.0)
             steer_range = float((max_a - center) if norm_err >= 0 else (center - min_a))
             target_angle = float(center + (norm_err * steer_range * steer_gain))
             obstacle = self._front_obstacle_info(distance, target=target)
             soft_dir = obstacle.get('soft_dir')
             bias = float(cfg.get('follow_obstacle_steer_bias', 0.18)) * float(max_a - min_a)
             if soft_dir == 'left':
                 target_angle -= bias
             elif soft_dir == 'right':
                 target_angle += bias
             target_angle = max(float(min_a), min(float(max_a), target_angle))
             
             if self._last_steer_angle is None:
                 self._last_steer_angle = float(center)
             current_angle = float(self._last_steer_angle)
             smoothed = (steer_alpha * target_angle) + ((1.0 - steer_alpha) * current_angle)
             self._last_steer_angle = smoothed
             
             steering.set_angle(int(round(smoothed)))
             self.runtime.state.steering_angle = steering.angle

        # 3. Drive Forward/Reverse depending on distance / area volume
        if motors:
            speed = int(cfg.get('follow_drive_speed', 30))
            stop_dist = float(cfg.get('follow_stop_distance_cm', 25))
            target_dist = float(cfg.get('follow_target_distance_cm', 60))
            use_sonic = bool(cfg.get('follow_use_ultrasonic', True))
            
            # Decide to move forward, backward, or stop
            drive_state = 'stopped'
            
            if use_sonic and distance is not None:
                if distance > (target_dist + 15):
                    drive_state = 'forward'
                elif distance < stop_dist:
                    drive_state = 'backward'
                # Else stop
            else:
                 area_ratio = getattr(target, 'area', getattr(target, 'w', 0) * getattr(target, 'h', 0)) / max(1, frame_w * frame_h)
                 area_target = float(cfg.get('follow_image_size_ratio_target', 0.25))
                 if area_ratio < (area_target - 0.05):
                     drive_state = 'forward'
                 elif area_ratio > (area_target + 0.15): # Overly close
                     drive_state = 'backward'

            if drive_state == 'forward':
                motors.forward(speed)
            elif drive_state == 'backward':
                rear_dist = self._measure_rear_distance()
                self.runtime.state.patrol_metrics['last_rear_distance_cm'] = rear_dist
                if rear_dist is not None and rear_dist < 15.0:
                    drive_state = 'stopped'
                    motors.stop()
                else:
                    motors.backward(max(0, speed - 5))
            else:
                motors.stop()

            self.runtime.state.patrol_drive_state = 'following_' + drive_state
                
            self.runtime.state.motor_state = motors.state
            self.runtime.state.speed = motors.speed
            time.sleep(0.05)


    def _patrol_drive(self, distance):
         state = self.runtime.state
         motors = self.runtime.registry.motors
         steering = self.runtime.registry.steering

         obstacle = self._front_obstacle_info(distance)
         hard_obstacle = bool(obstacle.get('hard'))
         soft_obstacle_dir = obstacle.get('soft_dir')

         if hard_obstacle:
             self._handle_hard_obstacle(obstacle)
         else:
             self._consecutive_blocks = 0
             self._last_obstacle_label = None
             self._obstacle_clear_since = self._obstacle_clear_since or time.monotonic()
             self._set_behavior_state('patrol')
             if state.patrol_drive_state != 'forward':
                 state.patrol_drive_state = 'forward'

             if steering:
                 if soft_obstacle_dir == 'left':
                     steering.left()
                 elif soft_obstacle_dir == 'right':
                     steering.right()
                 else:
                     ang = steering.angle
                     cen = steering.center_angle
                     if ang > cen + 2:
                         steering.set_angle(ang - 2)
                     elif ang < cen - 2:
                         steering.set_angle(ang + 2)
                     else:
                         steering.center()
                 state.steering_angle = steering.angle

             if motors:
                 motors.forward(self._config.get('speed', 35))
                 state.motor_state = motors.state
                 state.speed = motors.speed
             time.sleep(0.05)

         self._update_scan()

    def _loop(self):
        tick_history = []
        while not self._stop.is_set():
            t0 = time.monotonic()
            state = self.runtime.state
            motors = self.runtime.registry.motors
            steering = self.runtime.registry.steering
            if not state.patrol_enabled:
                if state.patrol_drive_state != 'idle' or (motors is not None and motors.state != 'stopped'):
                    state.patrol_drive_state = 'idle'
                    self._stop_motion()
                if self._config.get('scan_on_boot', True):
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

            if state.patrol_drive_state == 'trapped':
                if time.monotonic() - self._last_escape_ts > self._config.get('trapped_timeout_s', 10.0):
                    self.logger.info('Trapped timeout expired, attempting recovery')
                    self._consecutive_blocks = 0
                    state.patrol_drive_state = 'idle'
                else:
                    self._stop_motion()
                    time.sleep(1.0)
                    continue

            try:
                self._ensure_patrol_vision()
                action = self._config.get('action_on_detect', 'follow')
                target = self._select_target()
                now = time.monotonic()

                if target:
                    self._target_seen_streak += 1
                    sig = self._target_signature(target)
                    if sig != self._last_target_signature:
                        self._record_event('target_acquired', label=target.label, confidence=round(float(getattr(target, 'confidence', 1.0) or 1.0), 3))
                    self._last_target_signature = sig
                    self._last_target_ts = now
                else:
                    self._target_seen_streak = 0

                state.patrol_metrics['target_seen_streak'] = int(self._target_seen_streak)
                if self._last_target_signature:
                    state.patrol_metrics['target_lost_age_s'] = round(max(0.0, now - self._last_target_ts), 2)
                else:
                    state.patrol_metrics['target_lost_age_s'] = None
                if self._obstacle_clear_since is not None:
                    state.patrol_metrics['obstacle_clear_age_s'] = round(max(0.0, now - self._obstacle_clear_since), 2)
                else:
                    state.patrol_metrics['obstacle_clear_age_s'] = None
                state.patrol_metrics['current_target_label'] = getattr(target, 'label', None) if target else None

                obstacle = self._front_obstacle_info(distance, target=target)
                state.patrol_metrics['current_obstacle_label'] = obstacle.get('label') if obstacle else None
                acquire_frames = int(self._config.get('acquire_confirm_frames', 3))
                lost_timeout = float(self._config.get('lost_timeout_s', 1.5))
                obstacle_hold = float(self._config.get('obstacle_hold_time_s', 0.5))
                reacquire_hold = float(self._config.get('follow_reacquire_hold_s', 0.75))
                target_confirmed = bool(target and self._target_seen_streak >= acquire_frames)
                target_recent = bool(self._last_target_signature and (now - self._last_target_ts) <= lost_timeout)
                log_target = self._select_loggable_target()
                log_confirmed = bool(log_target and ((str(getattr(log_target, 'label', '')).lower() in (self._config.get('log_only_classes') or [])) or action == 'log'))

                if obstacle.get('hard'):
                    self._obstacle_clear_since = None
                    self._handle_hard_obstacle(obstacle)
                elif action == 'follow' and (target_confirmed or (target and target_recent)):
                    if self._obstacle_clear_since is None:
                        self._obstacle_clear_since = now
                    if self._behavior_state in {'avoid_front', 'recovering'} and (now - self._obstacle_clear_since) < max(obstacle_hold, reacquire_hold):
                        self._set_behavior_state('recovering')
                        self.runtime.state.patrol_drive_state = 'recovering'
                        self._stop_motion()
                        time.sleep(0.05)
                    else:
                        self._obstacle_clear_since = now
                        self._follow_target(target, distance)
                elif log_target and (log_confirmed or (action == 'log' and self._target_seen_streak >= acquire_frames)):
                    self._set_behavior_state('investigate', label=getattr(log_target, 'label', None))
                    self._log_target(log_target)
                else:
                    if self._last_target_signature and not target_recent:
                        self._record_event('target_lost')
                        self._last_target_signature = None
                    self._patrol_drive(distance)
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
                dt = max(0.0001, time.monotonic() - t0)
                tick_history.append(dt)
                if len(tick_history) > 20:
                    tick_history.pop(0)
                avg = sum(tick_history) / len(tick_history)
                state.patrol_metrics['loop_hz'] = round(1.0 / avg, 2)
