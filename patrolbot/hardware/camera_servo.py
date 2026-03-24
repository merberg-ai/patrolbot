from __future__ import annotations

from patrolbot.hardware.servo_driver import ServoDriver


class CameraServoController:
    def __init__(self, config: dict, logger=None, hat=None):
        self.config = config or {}
        self.logger = logger
        self.hat = hat

        servo_cfg = self.config.get("servo", {})

        pan_cfg = servo_cfg.get("camera_pan", {})
        tilt_cfg = servo_cfg.get("camera_tilt", {})

        self.pan_channel = int(pan_cfg.get("channel", 1))
        self.pan_center = int(pan_cfg.get("center", 90))
        self.pan_trim = int(pan_cfg.get("trim", 0))
        self.pan_min = int(pan_cfg.get("min_angle", 40))
        self.pan_max = int(pan_cfg.get("max_angle", 140))
        self.pan_step = int(pan_cfg.get("step", 10))
        self.pan_invert = bool(pan_cfg.get("invert", False))

        self.tilt_channel = int(tilt_cfg.get("channel", 2))
        self.tilt_center = int(tilt_cfg.get("center", 90))
        self.tilt_trim = int(tilt_cfg.get("trim", 0))
        self.tilt_min = int(tilt_cfg.get("min_angle", 40))
        self.tilt_max = int(tilt_cfg.get("max_angle", 140))
        self.tilt_step = int(tilt_cfg.get("step", 10))
        self.tilt_invert = bool(tilt_cfg.get("invert", False))

        self.driver = ServoDriver(self.config, logger=self.logger, hat=self.hat)

        self.pan_angle = self.pan_center
        self.tilt_angle = self.tilt_center

        if self.logger:
            self.logger.info(
                "Camera servo controller initialized: pan(ch=%s center=%s trim=%s), tilt(ch=%s center=%s trim=%s)",
                self.pan_channel,
                self.pan_center,
                self.pan_trim,
                self.tilt_channel,
                self.tilt_center,
                self.tilt_trim,
            )

    def _clamp_pan(self, angle: int) -> int:
        return max(self.pan_min, min(self.pan_max, int(angle)))

    def _clamp_tilt(self, angle: int) -> int:
        return max(self.tilt_min, min(self.tilt_max, int(angle)))

    def _physical_pan(self, logical_angle: int) -> int:
        return self._clamp_pan(int(logical_angle) + self.pan_trim)

    def _physical_tilt(self, logical_angle: int) -> int:
        return self._clamp_tilt(int(logical_angle) + self.tilt_trim)

    def set_pan(self, angle: int, log: bool = True):
        logical_angle = self._clamp_pan(angle)
        physical_angle = self._physical_pan(logical_angle)
        if logical_angle == self.pan_angle:
            return
        self.driver.set_servo_angle(self.pan_channel, physical_angle)
        self.pan_angle = logical_angle
        if self.logger and log:
            self.logger.info("Camera pan angle set to logical=%s physical=%s", self.pan_angle, physical_angle)

    def set_tilt(self, angle: int, log: bool = True):
        logical_angle = self._clamp_tilt(angle)
        physical_angle = self._physical_tilt(logical_angle)
        if logical_angle == self.tilt_angle:
            return
        self.driver.set_servo_angle(self.tilt_channel, physical_angle)
        self.tilt_angle = logical_angle
        if self.logger and log:
            self.logger.info("Camera tilt angle set to logical=%s physical=%s", self.tilt_angle, physical_angle)

    def home(self):
        self.set_pan(self.pan_center)
        self.set_tilt(self.tilt_center)

    def pan_left(self):
        delta = self.pan_step if self.pan_invert else -self.pan_step
        self.set_pan(self.pan_angle + delta)

    def pan_right(self):
        delta = -self.pan_step if self.pan_invert else self.pan_step
        self.set_pan(self.pan_angle + delta)

    def tilt_up(self):
        delta = self.tilt_step if self.tilt_invert else -self.tilt_step
        self.set_tilt(self.tilt_angle + delta)

    def tilt_down(self):
        delta = -self.tilt_step if self.tilt_invert else self.tilt_step
        self.set_tilt(self.tilt_angle + delta)

    def set_pan_trim(self, trim: int) -> None:
        self.pan_trim = max(-20, min(20, int(trim)))
        self.set_pan(self.pan_angle)

    def set_tilt_trim(self, trim: int) -> None:
        self.tilt_trim = max(-20, min(20, int(trim)))
        self.set_tilt(self.tilt_angle)

    def get_state(self) -> dict:
        return {
            "pan": {
                "channel": self.pan_channel,
                "angle": self.pan_angle,
                "center": self.pan_center,
                "trim": self.pan_trim,
                "min_angle": self.pan_min,
                "max_angle": self.pan_max,
                "step": self.pan_step,
                "invert": self.pan_invert,
            },
            "tilt": {
                "channel": self.tilt_channel,
                "angle": self.tilt_angle,
                "center": self.tilt_center,
                "trim": self.tilt_trim,
                "min_angle": self.tilt_min,
                "max_angle": self.tilt_max,
                "step": self.tilt_step,
                "invert": self.tilt_invert,
            },
        }
