from __future__ import annotations

import io
import threading
import time
from typing import Any

from patrolbot.services.camera_settings import build_camera_settings_from_config


class CameraWrapper:
    def __init__(self, config: dict, logger):
        self.config = config or {}
        self.logger = logger
        self.running = False
        self.picam2 = None
        self._lock = threading.RLock()
        self.current_settings = build_camera_settings_from_config(self.config)
        self.last_error: str | None = None

        cam_cfg = self.config.get('camera', {})
        self.width = int(cam_cfg.get('width', 640))
        self.height = int(cam_cfg.get('height', 480))
        self.fps = int(cam_cfg.get('fps', 20))
        self.rotation = int(cam_cfg.get('rotation', 0))

    def _refresh_runtime_geometry(self, settings: dict[str, Any] | None = None) -> None:
        merged = dict(self.current_settings)
        if settings:
            merged.update(settings)
        self.width = int(merged.get('width', self.width or 640))
        self.height = int(merged.get('height', self.height or 480))
        self.fps = int(merged.get('fps', self.fps or 20))
        self.rotation = int(merged.get('rotation', self.rotation or 0))

    def _build_camera_instance(self):
        from picamera2 import Picamera2

        picam2 = Picamera2()
        frame_duration = int(1_000_000 / max(1, self.fps))
        config = picam2.create_video_configuration(
            main={"size": (self.width, self.height), "format": "RGB888"},
            controls={"FrameDurationLimits": (frame_duration, frame_duration)},
        )
        picam2.configure(config)
        return picam2

    def start(self) -> bool:
        with self._lock:
            if self.running and self.picam2 is not None:
                return True
            self.last_error = None
            try:
                self._refresh_runtime_geometry(self.current_settings)
                self.logger.info("Camera start: creating fresh Picamera2 instance")
                self.picam2 = self._build_camera_instance()
                self.logger.info("Camera start: starting stream")
                self.picam2.start()
                time.sleep(0.35)
                self.running = True
                apply_result = self.apply_settings(self.current_settings)
                warnings = apply_result.get('warnings', []) if isinstance(apply_result, dict) else []
                if warnings:
                    self.logger.warning("Camera start applied settings with warnings: %s", "; ".join(warnings))
                self.logger.info("Camera started via picamera2 at %sx%s %sfps", self.width, self.height, self.fps)
                return True
            except Exception as exc:
                self.last_error = str(exc)
                self.logger.warning("Camera start failed, streaming disabled: %s", exc)
                try:
                    if self.picam2 is not None:
                        self.picam2.close()
                except Exception:
                    pass
                self.picam2 = None
                self.running = False
                return False

    def stop(self) -> None:
        with self._lock:
            picam2 = self.picam2
            self.picam2 = None
            self.running = False
            if picam2 is None:
                self.logger.info('Camera stopped')
                return
            self.logger.info('Camera stop: stopping stream')
            try:
                picam2.stop()
            except Exception as exc:
                self.logger.warning('Camera stop: stop() raised: %s', exc)
            self.logger.info('Camera stop: closing camera instance')
            try:
                picam2.close()
            except Exception as exc:
                self.logger.warning('Camera stop: close() raised: %s', exc)
        self.logger.info('Camera stopped')

    def get_frame(self) -> bytes:
        if not self.running or self.picam2 is None:
            return b''
        with self._lock:
            if not self.running or self.picam2 is None:
                return b''
            try:
                buf = io.BytesIO()
                self.picam2.capture_file(buf, format='jpeg')
                return buf.getvalue()
            except Exception as exc:
                self.last_error = str(exc)
                self.logger.warning('Camera frame capture failed: %s', exc)
                return b''


    def read_bgr(self):
        if not self.running or self.picam2 is None:
            return None
        with self._lock:
            if not self.running or self.picam2 is None:
                return None
            try:
                frame = self.picam2.capture_array()
                if frame is None:
                    return None
                try:
                    import cv2
                    return cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                except Exception:
                    return frame
            except Exception as exc:
                self.last_error = str(exc)
                self.logger.warning('Camera BGR capture failed: %s', exc)
                return None

    def encode_jpeg(self, frame_bgr) -> bytes:
        try:
            import cv2
            ok, buf = cv2.imencode('.jpg', frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, 85])
            return buf.tobytes() if ok else b''
        except Exception as exc:
            self.last_error = str(exc)
            self.logger.warning('Camera JPEG encode failed: %s', exc)
            return b''

    def get_settings(self) -> dict[str, Any]:
        return dict(self.current_settings)

    def apply_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        merged = dict(self.current_settings)
        merged.update(settings or {})
        if not self.running or self.picam2 is None:
            self.current_settings = merged
            self._refresh_runtime_geometry(merged)
            return {"ok": False, "applied": False, "warnings": ["Camera is not running; settings were saved for next start."]}

        controls, warnings = self._build_control_payload(merged)
        applied = False
        with self._lock:
            if controls and self.picam2 is not None:
                try:
                    self.picam2.set_controls(controls)
                    applied = True
                except Exception as exc:
                    warnings.append(f"Failed to apply camera controls live: {exc}")
            self.current_settings = merged
            self._refresh_runtime_geometry(merged)
        return {"ok": True, "applied": applied, "warnings": warnings}

    def restart_with_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        merged = dict(self.current_settings)
        merged.update(settings or {})
        self.current_settings = merged
        self._refresh_runtime_geometry(merged)

        warnings: list[str] = []
        previous_running = self.running
        previous_error = self.last_error

        self.logger.info('Camera restart requested: begin full teardown/recreate cycle')
        try:
            self.stop()
            self.logger.info('Camera restart: waiting for hardware release')
            time.sleep(0.85)

            if self.start():
                self.logger.info('Camera restart completed successfully')
                return {"ok": True, "applied": True, "restarted": True, "warnings": warnings}

            first_error = self.last_error
            if first_error:
                warnings.append(f"Camera restart attempt 1 failed: {first_error}")

            self.logger.warning('Camera restart attempt 1 failed; retrying once after cooldown')
            time.sleep(1.25)
            if self.start():
                self.logger.info('Camera restart completed successfully on retry')
                warnings.append('Camera restart succeeded on second attempt.')
                return {"ok": True, "applied": True, "restarted": True, "warnings": warnings}

            second_error = self.last_error
            if second_error:
                warnings.append(f"Camera restart attempt 2 failed: {second_error}")
        except Exception as exc:
            self.last_error = str(exc)
            warnings.append(f"Camera restart failed with unexpected error: {exc}")
            self.logger.exception('Camera restart failed with unexpected exception')

        if previous_running:
            warnings.append('Camera settings were saved, but the camera did not come back online.')
        else:
            warnings.append('Camera settings were saved, but the camera is not currently running.')
        if previous_error and previous_error != self.last_error:
            warnings.append(f"Previous camera error before restart: {previous_error}")
        return {"ok": False, "applied": False, "restarted": False, "warnings": warnings}

    def _build_control_payload(self, settings: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
        controls: dict[str, Any] = {}
        warnings: list[str] = []

        controls['Brightness'] = float(settings.get('brightness', 0.0))
        controls['Contrast'] = float(settings.get('contrast', 1.0))
        controls['Saturation'] = float(settings.get('saturation', 1.0))
        controls['Sharpness'] = float(settings.get('sharpness', 1.0))
        controls['ExposureValue'] = float(settings.get('exposure_compensation', 0.0))

        rotation = int(settings.get('rotation', self.rotation) or 0)
        if rotation:
            controls['Rotation'] = rotation

        awb_mode = str(settings.get('awb_mode', 'auto')).strip().lower()
        red_gain = settings.get('manual_red_gain')
        blue_gain = settings.get('manual_blue_gain')

        awb_enum = self._resolve_awb_mode(awb_mode)
        if awb_mode == 'custom':
            controls['AwbEnable'] = False
            if red_gain is not None and blue_gain is not None:
                controls['ColourGains'] = (float(red_gain), float(blue_gain))
            else:
                warnings.append('Manual gains mode selected, but both red and blue gains are required.')
        else:
            controls['AwbEnable'] = True
            if awb_enum is not None:
                controls['AwbMode'] = awb_enum
            else:
                warnings.append(f"Unsupported AWB mode mapping for {awb_mode!r}; leaving current AWB mode alone.")
            if red_gain is not None or blue_gain is not None:
                warnings.append('Manual gains are ignored unless AWB mode is set to Manual Gains.')

        return controls, warnings

    def _resolve_awb_mode(self, awb_mode: str):
        if awb_mode == 'auto':
            target = 'Auto'
        elif awb_mode == 'tungsten':
            target = 'Tungsten'
        elif awb_mode == 'fluorescent':
            target = 'Fluorescent'
        elif awb_mode == 'indoor':
            target = 'Indoor'
        elif awb_mode == 'daylight':
            target = 'Daylight'
        elif awb_mode == 'cloudy':
            target = 'Cloudy'
        else:
            return None

        try:
            from libcamera import controls as libcamera_controls

            enum_cls = getattr(libcamera_controls, 'AwbModeEnum', None)
            if enum_cls is None:
                return None
            return getattr(enum_cls, target, None)
        except Exception:
            return None

    def mjpeg_generator(self, runtime=None):
        try:
            import cv2 as _cv2
            import numpy as _np
            _cv_ok = True
        except ImportError:
            _cv_ok = False

        while True:
            if not self.running or self.picam2 is None:
                time.sleep(0.1)
                continue

            frame = self.get_frame()
            if frame:
                # Draw tracking overlay if enabled and a detected box exists
                if _cv_ok and runtime is not None:
                    state = runtime.state
                    box = getattr(state, 'tracking_box', None)
                    if getattr(state, 'tracking_enabled', False) and box is not None:
                        try:
                            np_arr = _np.frombuffer(frame, _np.uint8)
                            img = _cv2.imdecode(np_arr, _cv2.IMREAD_COLOR)
                            if img is not None:
                                x, y, w, h = box
                                detector = getattr(state, 'tracking_detector', '')
                                label_map = {
                                    'haar_face': 'Face',
                                    'haar_body': 'Body',
                                    'motion': 'Motion',
                                }
                                label = label_map.get(detector, 'Target')
                                # Cyan bounding box + label
                                _cv2.rectangle(img, (x, y), (x + w, y + h), (0, 255, 204), 2)
                                _cv2.putText(
                                    img, label,
                                    (x, max(y - 8, 12)),
                                    _cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                                    (0, 255, 204), 2, _cv2.LINE_AA,
                                )
                                ok, buf = _cv2.imencode('.jpg', img, [_cv2.IMWRITE_JPEG_QUALITY, 85])
                                if ok:
                                    frame = buf.tobytes()
                        except Exception:
                            pass  # never crash the stream on overlay failure

                yield (
                    b'--frame\r\n'
                    b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n'
                )

            time.sleep(max(0.03, 1.0 / max(1, self.fps)))
