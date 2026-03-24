from __future__ import annotations

from patrolbot.hardware.servo_driver import ServoDriver


class SteeringController:
    def __init__(self, config: dict, logger=None, hat=None):
        self.config = config or {}
        self.logger = logger
        self.hat = hat

        steering_cfg = self.config.get("servo", {}).get("steering", {})

        self.channel = int(steering_cfg.get("channel", 0))
        self.center_angle = int(steering_cfg.get("center", 90))
        self.trim = int(steering_cfg.get("trim", 0))
        self.min_angle = int(steering_cfg.get("min_angle", 45))
        self.max_angle = int(steering_cfg.get("max_angle", 135))
        self.step = int(steering_cfg.get("step", 10))
        self.invert = bool(steering_cfg.get("invert", False))

        self.driver = ServoDriver(self.config, logger=self.logger, hat=self.hat)
        self.angle = self.center_angle

        if self.logger:
            self.logger.info(
                "Steering controller initialized: channel=%s center=%s trim=%s range=%s..%s step=%s invert=%s",
                self.channel,
                self.center_angle,
                self.trim,
                self.min_angle,
                self.max_angle,
                self.step,
                self.invert,
            )

    def _clamp(self, angle: int) -> int:
        return max(self.min_angle, min(self.max_angle, int(angle)))

    def _physical_angle(self, logical_angle: int) -> int:
        return self._clamp(int(logical_angle) + self.trim)

    def set_angle(self, angle: int) -> None:
        logical_angle = self._clamp(angle)
        physical_angle = self._physical_angle(logical_angle)
        if logical_angle == self.angle:
            return
        self.driver.set_servo_angle(self.channel, physical_angle)
        self.angle = logical_angle

        if self.logger:
            self.logger.info("Steering angle set to logical=%s physical=%s", self.angle, physical_angle)

    def center(self) -> None:
        self.set_angle(self.center_angle)

    def left(self) -> None:
        delta = self.step if self.invert else -self.step
        self.set_angle(self.angle + delta)

    def right(self) -> None:
        delta = -self.step if self.invert else self.step
        self.set_angle(self.angle + delta)

    def set_trim(self, trim: int) -> None:
        self.trim = max(-20, min(20, int(trim)))
        self.set_angle(self.angle)

    def get_state(self) -> dict:
        return {
            "channel": self.channel,
            "angle": self.angle,
            "center": self.center_angle,
            "trim": self.trim,
            "min_angle": self.min_angle,
            "max_angle": self.max_angle,
            "step": self.step,
            "invert": self.invert,
        }
