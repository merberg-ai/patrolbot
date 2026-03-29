from __future__ import annotations

import threading
import time

from patrolbot.config import load_runtime_config, save_runtime_config
from patrolbot.vision.detectors import build_detector
from patrolbot.vision.tracker import VisionTracker

try:
    import psutil  # type: ignore
except Exception:  # pragma: no cover
    psutil = None


class VisionService:
    DEFAULTS = {
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
        'jpeg_every_n_frames': 2,
        'idle_sleep_s': 0.02,
        'stats_log_interval_s': 10.0,
        'overlay_enabled': True,
        'show_confidence_bar': True,
    }

    def __init__(self, runtime, logger):
        self.runtime = runtime
        self.logger = logger
        self._stop = threading.Event()
        self._thread = None
        self._config = self._normalize(dict(runtime.config.get('vision', {})))

        self._detector = build_detector(self._config.get('detector', 'face'), self._config)
        self._tracker = VisionTracker(self._config)
        self._latest_jpeg = b''
        self._latest_detections = []
        self._latest_target = None
        self._fps_window_ts = time.time()
        self._fps_counter = 0
        self._fps_actual = 0.0
        self._process = psutil.Process() if psutil else None
        self._last_stats_log_ts = 0.0
        self._mjpeg_clients = 0
        self._mjpeg_clients_lock = threading.Lock()
        self._cv_ok = self._check_cv()
        self._sync_state_basics()
        self._apply_startup_safety()

    def _check_cv(self) -> bool:
        try:
            import cv2  # noqa: F401
            import numpy as np  # noqa: F401
            return True
        except Exception:
            return False

    def _normalize(self, source: dict) -> dict:
        cfg = dict(self.DEFAULTS)
        cfg.update(source or {})
        cfg['enabled'] = bool(cfg.get('enabled', False))
        detector = str(cfg.get('detector', 'face')).strip().lower()
        aliases = {'haar_face': 'face', 'haar_body': 'body'}
        cfg['detector'] = aliases.get(detector, detector)
        raw_classes = cfg.get('yolo_classes', [])
        if isinstance(raw_classes, str):
            raw_classes = [x.strip().lower() for x in raw_classes.split(',') if x.strip()]
        cfg['yolo_classes'] = raw_classes
        cfg['preferred_target'] = str(cfg.get('preferred_target', 'largest')).strip().lower()
        for name in ('confidence_min', 'idle_sleep_s', 'stats_log_interval_s'):
            cfg[name] = float(cfg.get(name, self.DEFAULTS[name]))
        for name in ('max_results', 'process_every_n_frames', 'box_padding_px', 'yolo_imgsz', 'jpeg_every_n_frames'):
            cfg[name] = int(cfg.get(name, self.DEFAULTS[name]))
        for name in ('show_labels', 'show_crosshair', 'show_metrics_overlay', 'enable_yolo', 'overlay_enabled', 'show_confidence_bar'):
            cfg[name] = bool(cfg.get(name, self.DEFAULTS[name]))
        
        cfg['confidence_min'] = max(0.0, min(1.0, cfg['confidence_min']))
        cfg['process_every_n_frames'] = max(1, cfg['process_every_n_frames'])
        cfg['box_padding_px'] = max(0, cfg['box_padding_px'])
        cfg['jpeg_every_n_frames'] = max(1, cfg['jpeg_every_n_frames'])
        cfg['yolo_imgsz'] = max(160, int(cfg['yolo_imgsz']))
        cfg['idle_sleep_s'] = max(0.005, float(cfg['idle_sleep_s']))
        cfg['stats_log_interval_s'] = max(3.0, float(cfg['stats_log_interval_s']))
        return cfg

    def _sync_state_basics(self):
        state = self.runtime.state
        state.vision_enabled = bool(self._config.get('enabled', False))
        state.vision_detector = self._config.get('detector', 'face')
        state.vision_preferred_target = self._config.get('preferred_target', 'largest')
        state.vision_overlay_enabled = bool(self._config.get('overlay_enabled', True))
        state.vision_detector_available = bool(self._detector.is_available()) if self._detector else False
        state.vision_detector_status = self.get_detector_status()
        state.vision_yolo_available = self.yolo_available()
        state.vision_detector_details = self.get_detector_details()

    def _apply_startup_safety(self):
        requested = bool(self._config.get('enabled', False))
        if not requested:
            return
        if not self._cv_ok:
            self._config['enabled'] = False
            self.runtime.state.vision_enabled = False
            self.runtime.state.vision_disable_reason = 'opencv_unavailable'
            self.logger.warning('Vision requested at boot but OpenCV is unavailable; starting disabled')
            return
        if self._detector is None or not self._detector.is_available():
            self._config['enabled'] = False
            self.runtime.state.vision_enabled = False
            self.runtime.state.vision_disable_reason = 'detector_unavailable'
            self.logger.warning('Vision requested at boot but detector %s is unavailable; starting disabled', self._config.get('detector', 'unknown'))

    def get_config(self):
        return dict(self._config)

    def get_detector_status(self):
        det = self._detector
        if det is None:
            return 'missing'
        if hasattr(det, 'status'):
            try:
                return det.status()
            except Exception:
                return 'unknown'
        return 'ready' if det.is_available() else 'unavailable'

    def get_detector_details(self):
        det = self._detector
        name = self._config.get('detector', 'face')
        status = self.get_detector_status()
        available = bool(det.is_available()) if det else False
        details = {
            'selected': name,
            'available': available,
            'status': status,
            'opencv_available': self._cv_ok,
            'vision_enabled_requested': bool(self._config.get('enabled', False)),
            'vision_enabled_live': bool(self.runtime.state.vision_enabled),
            'yolo_available': self.yolo_available(),
            'enable_yolo': bool(self._config.get('enable_yolo', False)),
            'yolo_model': self._config.get('yolo_model', 'yolov8n.pt'),
            'yolo_classes': list(self._config.get('yolo_classes', []) or []),
            'detectors': {
                'face': {'available': self._cv_ok, 'status': 'ready' if self._cv_ok else 'unavailable: opencv missing'},
                'body': {'available': self._cv_ok, 'status': 'ready' if self._cv_ok else 'unavailable: opencv missing'},
                'motion': {'available': self._cv_ok, 'status': 'ready' if self._cv_ok else 'unavailable: opencv missing'},
                'yolo': {
                    'available': self.yolo_available() and bool(self._config.get('enable_yolo', False)),
                    'status': status if name == 'yolo' else ('available' if self.yolo_available() else 'unavailable: ultralytics import failed'),
                },
            },
        }
        if det is not None and hasattr(det, '_error') and getattr(det, '_error', None):
            details['reason'] = getattr(det, '_error')
        return details

    def yolo_available(self):
        try:
            from ultralytics import YOLO  # noqa: F401
            return True
        except Exception:
            return False

    def update_config(self, patch: dict, persist: bool = True):
        merged = dict(self._config)
        merged.update(patch or {})
        self._config = self._normalize(merged)
        self._tracker.apply_config(self._config)
        self.runtime.config['vision'] = dict(self._config)
        self._detector = build_detector(self._config.get('detector', 'face'), self._config)
        warnings = []
        if self._config.get('detector') == 'yolo' and not bool(self._config.get('enable_yolo', False)):
            warnings.append('YOLO detector selected but Enable YOLO is off; vision cannot use YOLO until enabled.')
        if self._config.get('detector') == 'yolo' and not self.yolo_available():
            warnings.append('Ultralytics/YOLO is unavailable in this environment.')
        if not self._cv_ok:
            warnings.append('OpenCV is unavailable; vision cannot be enabled until it is installed.')
        self._sync_state_basics()
        if self.runtime.state.vision_enabled and (self._detector is None or not self._detector.is_available()):
            self.disable(reason='detector_unavailable')
            warnings.append('Vision was disabled because the selected detector is unavailable.')
        if persist:
            runtime_cfg = load_runtime_config()
            runtime_cfg['vision'] = dict(self._config)
            save_runtime_config(runtime_cfg)
        return dict(self._config), warnings

    def set_enabled(self, enabled: bool, persist: bool = False):
        self._config['enabled'] = bool(enabled)
        self.runtime.config['vision'] = dict(self._config)
        self.runtime.state.vision_enabled = bool(enabled)
        self.runtime.state.vision_disable_reason = None if enabled else self.runtime.state.vision_disable_reason
        self.runtime.state.vision_detector_status = self.get_detector_status()
        self.runtime.state.vision_detector_details = self.get_detector_details()
        if persist:
            runtime_cfg = load_runtime_config()
            runtime_cfg['vision'] = dict(self._config)
            save_runtime_config(runtime_cfg)

    def enable(self):
        if not self._cv_ok:
            self.runtime.state.vision_disable_reason = 'opencv_unavailable'
            return
        if self._detector is None or not self._detector.is_available():
            self.runtime.state.vision_disable_reason = 'detector_unavailable'
            return
        self.set_enabled(True, persist=True)

    def disable(self, reason: str | None = None):
        self.set_enabled(False, persist=True)
        self.runtime.state.vision_target_acquired = False
        self.runtime.state.vision_box = None
        self.runtime.state.vision_target_label = None
        self.runtime.state.vision_target_confidence = None
        self.runtime.state.vision_disable_reason = reason
        if hasattr(self._tracker, 'reset'):
            self._tracker.reset()

    def toggle(self):
        if self.runtime.state.vision_enabled:
            self.disable()
        else:
            self.enable()

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._loop, daemon=True, name='patrolbot-vision')
        self._thread.start()
        self.logger.info('Vision background service started. detector=%s', self._config.get('detector', 'face'))

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)

    def _choose_target(self, detections, frame_w, frame_h):
        return self._tracker.choose_target(detections, frame_w, frame_h)

    def _draw_overlay(self, frame, detections, target):
        import cv2
        h, w = frame.shape[:2]
        pad = int(self._config.get('box_padding_px', 0))
        show_labels = self._config.get('show_labels', True)
        show_conf_bar = self._config.get('show_confidence_bar', True)

        for det in detections:
            is_target = (
                target and
                det.x == target.x and det.y == target.y and
                det.w == target.w and det.h == target.h
            )
            x1 = max(0, det.x - pad)
            y1 = max(0, det.y - pad)
            x2 = min(w - 1, det.x + det.w + pad)
            y2 = min(h - 1, det.y + det.h + pad)

            if is_target:
                color = (0, 255, 204)
                thickness = 2
                cs = min(16, (x2 - x1) // 4, (y2 - y1) // 4)
                cv2.line(frame, (x1, y1), (x1 + cs, y1), color, thickness)
                cv2.line(frame, (x1, y1), (x1, y1 + cs), color, thickness)
                cv2.line(frame, (x2, y1), (x2 - cs, y1), color, thickness)
                cv2.line(frame, (x2, y1), (x2, y1 + cs), color, thickness)
                cv2.line(frame, (x1, y2), (x1 + cs, y2), color, thickness)
                cv2.line(frame, (x1, y2), (x1, y2 - cs), color, thickness)
                cv2.line(frame, (x2, y2), (x2 - cs, y2), color, thickness)
                cv2.line(frame, (x2, y2), (x2, y2 - cs), color, thickness)
                cv2.rectangle(frame, (x1, y1), (x2, y2), (*color[:2], 80), 1)
            else:
                color = (120, 120, 120)
                thickness = 1
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, thickness)

            if show_labels:
                label = f"{det.label} {det.confidence:.2f}" if getattr(det, 'confidence', 1) < 0.999 else det.label
                label_y = max(14, y1 - 6)
                cv2.putText(frame, label, (x1 + 2, label_y), cv2.FONT_HERSHEY_SIMPLEX, 0.46, color, 1, cv2.LINE_AA)

            if show_conf_bar and is_target and hasattr(det, 'confidence'):
                bar_w = x2 - x1
                filled = int(bar_w * max(0.0, min(1.0, float(det.confidence))))
                bar_y = y2 + 3
                if bar_y + 4 < h:
                    cv2.rectangle(frame, (x1, bar_y), (x2, bar_y + 4), (60, 60, 60), -1)
                    cv2.rectangle(frame, (x1, bar_y), (x1 + filled, bar_y + 4), (0, 255, 204), -1)

        if self._config.get('show_crosshair', True):
            cx, cy = w // 2, h // 2
            cv2.line(frame, (cx - 14, cy), (cx + 14, cy), (255, 255, 255), 1)
            cv2.line(frame, (cx, cy - 14), (cx, cy + 14), (255, 255, 255), 1)

        if self._config.get('show_metrics_overlay', True):
            state = self.runtime.state
            line1 = (
                f"det={state.vision_detector} "
                f"vision={'on' if state.vision_enabled else 'off'} "
                f"target={'yes' if state.vision_target_acquired else 'no'}"
            )
            line2 = (
                f"fps={self._fps_actual:.1f} pan={state.pan_angle} tilt={state.tilt_angle} "
                f"det={len(detections)} clients={self._mjpeg_clients}"
            )
            cv2.putText(frame, line1, (8, h - 24), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255, 255, 255), 1, cv2.LINE_AA)
            cv2.putText(frame, line2, (8, h - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255, 255, 255), 1, cv2.LINE_AA)
        return frame

    def _update_fps(self):
        self._fps_counter += 1
        now = time.time()
        elapsed = now - self._fps_window_ts
        if elapsed >= 1.0:
            self._fps_actual = self._fps_counter / elapsed
            self.runtime.state.vision_fps_actual = round(self._fps_actual, 2)
            self._fps_counter = 0
            self._fps_window_ts = now

    def _current_rss_mb(self):
        if self._process is None:
            return None
        try:
            return round(self._process.memory_info().rss / (1024 * 1024), 1)
        except Exception:
            return None

    def _maybe_log_stats(self):
        now = time.time()
        interval = float(self._config.get('stats_log_interval_s', 10.0))
        if (now - self._last_stats_log_ts) < interval:
            return
        self._last_stats_log_ts = now
        self.logger.info(
            'Vision stats: fps=%.2f rss_mb=%s detector=%s status=%s detections=%s clients=%s vision=%s',
            self._fps_actual,
            self._current_rss_mb(),
            self.runtime.state.vision_detector,
            self.runtime.state.vision_detector_status,
            self.runtime.state.vision_last_detection_count,
            self._mjpeg_clients,
            self.runtime.state.vision_enabled,
        )

    def _should_encode_jpeg(self, frame_counter: int) -> bool:
        with self._mjpeg_clients_lock:
            client_count = self._mjpeg_clients
        self.runtime.state.vision_mjpeg_clients = client_count
        if client_count <= 0 and not self._latest_jpeg:
            return True
        if client_count <= 0:
            return False
        every_n = max(1, int(self._config.get('jpeg_every_n_frames', 2)))
        return (frame_counter % every_n) == 0

    def _loop(self):
        frame_counter = 0
        camera = getattr(self.runtime.registry, 'camera', None)
        while not self._stop.is_set():
            cfg = self._config
            if camera is None:
                self.runtime.state.vision_disable_reason = 'hardware_missing'
                time.sleep(0.2)
                camera = getattr(self.runtime.registry, 'camera', None)
                continue
                
            frame = camera.read_bgr() if hasattr(camera, 'read_bgr') else None
            if frame is None:
                time.sleep(0.05)
                continue
                
            frame_counter += 1
            every_n = max(1, int(cfg.get('process_every_n_frames', 3)))
            process_this = (frame_counter % every_n == 0)
            vision_enabled = bool(self.runtime.state.vision_enabled)

            detections = self._latest_detections if vision_enabled else []
            target = self._latest_target if vision_enabled else None

            if process_this and vision_enabled:
                try:
                    detections = self._detector.detect(frame)
                    self.runtime.state.vision_detector_available = bool(self._detector.is_available())
                    self.runtime.state.vision_detector_status = self.get_detector_status()
                    
                    target = self._choose_target(detections, frame.shape[1], frame.shape[0])
                    self._latest_detections = detections
                    self._latest_target = target
                    self.runtime.state.vision_detections = detections # Raw list for other services
                    self.runtime.state.vision_last_detection_count = len(detections)
                    self.runtime.state.vision_detector_details = self.get_detector_details()
                    
                    if target:
                        self.runtime.state.vision_target_acquired = True
                        self.runtime.state.vision_box = (target.x, target.y, target.w, target.h)
                        self.runtime.state.vision_target_label = target.label
                        self.runtime.state.vision_target_confidence = float(getattr(target, 'confidence', 1.0))
                        self.runtime.state.vision_disable_reason = None
                    else:
                        self.runtime.state.vision_target_acquired = False
                        self.runtime.state.vision_box = None
                        self.runtime.state.vision_target_label = None
                        self.runtime.state.vision_target_confidence = None

                except Exception as exc:
                    self.runtime.state.vision_last_error = str(exc)
                    self.runtime.state.vision_detector_status = f'error: {exc}'
                    self.runtime.state.vision_target_acquired = False
                    self.runtime.state.vision_detections = []
                    self._latest_detections = []
                    self._latest_target = None
                    detections = []
                    target = None
                    self.logger.exception('Detector failure: %s', exc)
            elif not vision_enabled:
                self._latest_detections = []
                self._latest_target = None
                self.runtime.state.vision_detections = []
                self.runtime.state.vision_last_detection_count = 0
                self.runtime.state.vision_target_acquired = False
                self.runtime.state.vision_detector_available = bool(self._detector.is_available()) if self._detector else False
                self.runtime.state.vision_detector_status = self.get_detector_status()

            self.runtime.state.vision_frame_size = (int(frame.shape[1]), int(frame.shape[0]))
            self._update_fps()
            
            self.runtime.state.vision_metrics = {
                'fps_target': getattr(camera, 'fps', None),
                'fps_actual': round(self._fps_actual, 2),
                'detections': self.runtime.state.vision_last_detection_count,
                'camera_backend': getattr(camera, '_backend', 'picamera2'),
                'detector_status': self.runtime.state.vision_detector_status,
                'rss_mb': self._current_rss_mb(),
                'mjpeg_clients': self.runtime.state.vision_mjpeg_clients,
            }

            if bool(cfg.get('overlay_enabled', True)) and self._should_encode_jpeg(frame_counter):
                draw_frame = self._draw_overlay(frame.copy(), detections or [], target)
                self._latest_jpeg = camera.encode_jpeg(draw_frame) if hasattr(camera, 'encode_jpeg') else b''
            
            self._maybe_log_stats()
            time.sleep(max(float(cfg.get('idle_sleep_s', 0.02)), 1.0 / max(1, getattr(camera, 'fps', 20))))

    def mjpeg(self):
        with self._mjpeg_clients_lock:
            self._mjpeg_clients += 1
        self.runtime.state.vision_mjpeg_clients = self._mjpeg_clients
        camera = getattr(self.runtime.registry, 'camera', None)
        fps = max(1, getattr(camera, 'fps', 20)) if camera else 20
        try:
            while not self._stop.is_set():
                frame = self._latest_jpeg
                if frame:
                    yield b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + frame + b'\r\n'
                else:
                    raw = camera.get_frame() if camera else b''
                    if raw:
                        yield b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + raw + b'\r\n'
                time.sleep(max(0.02, 1.0 / fps))
        finally:
            with self._mjpeg_clients_lock:
                self._mjpeg_clients = max(0, self._mjpeg_clients - 1)
            self.runtime.state.vision_mjpeg_clients = self._mjpeg_clients
