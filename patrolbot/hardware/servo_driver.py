from __future__ import annotations

from typing import Optional

import board
import busio
from adafruit_pca9685 import PCA9685


class ServoDriver:
    """
    Shared PCA9685 servo driver for patrolbot.

    Uses proper servo pulse width timing:
      - frequency default: 50 Hz
      - pulse range default: 500us .. 2500us

    Expected config shape:

    servo:
      driver:
        address: 0x5f
        frequency: 50
        min_pulse_us: 500
        max_pulse_us: 2500
    """

    _shared_pca: Optional[PCA9685] = None

    def __init__(self, config: dict, logger=None, hat=None):
        self.config = config or {}
        self.logger = logger
        self.hat = hat

        driver_cfg = self.config.get("servo", {}).get("driver", {})

        self.address = int(driver_cfg.get("address", 0x5F))
        self.frequency = int(driver_cfg.get("frequency", 50))
        self.min_pulse_us = int(driver_cfg.get("min_pulse_us", 500))
        self.max_pulse_us = int(driver_cfg.get("max_pulse_us", 2500))

        if ServoDriver._shared_pca is None:
            # If later your HatContext exposes a shared I2C bus, use it here.
            # For now we safely create our own busio I2C instance.
            i2c = busio.I2C(board.SCL, board.SDA)
            pca = PCA9685(i2c, address=self.address)
            pca.frequency = self.frequency
            ServoDriver._shared_pca = pca

            if self.logger:
                self.logger.info(
                    "Initialized PCA9685 servo driver at address 0x%02X, frequency=%sHz, pulse=%sus..%sus",
                    self.address,
                    self.frequency,
                    self.min_pulse_us,
                    self.max_pulse_us,
                )

        self.pca = ServoDriver._shared_pca

    def angle_to_duty_cycle(self, angle: float) -> int:
        """
        Convert servo angle (0..180) into PCA9685 16-bit duty cycle using
        configured microsecond pulse widths.
        """
        angle = max(0.0, min(180.0, float(angle)))

        pulse_us = self.min_pulse_us + (
            (angle / 180.0) * (self.max_pulse_us - self.min_pulse_us)
        )

        period_us = 1_000_000.0 / float(self.frequency)
        duty_fraction = pulse_us / period_us
        duty_cycle = int(max(0, min(65535, round(duty_fraction * 65535))))

        return duty_cycle

    def set_servo_angle(self, channel: int, angle: float) -> None:
        duty_cycle = self.angle_to_duty_cycle(angle)
        self.pca.channels[int(channel)].duty_cycle = duty_cycle

        if self.logger:
            self.logger.debug(
                "Set servo channel=%s angle=%.1f duty_cycle=%s",
                channel,
                angle,
                duty_cycle,
            )

    def release_channel(self, channel: int) -> None:
        """
        De-energize a servo channel. Useful later if you want to let a servo relax.
        """
        self.pca.channels[int(channel)].duty_cycle = 0

        if self.logger:
            self.logger.debug("Released servo channel=%s", channel)

    @classmethod
    def close_shared(cls, logger=None) -> None:
        if cls._shared_pca is not None:
            try:
                cls._shared_pca.deinit()
                if logger:
                    logger.info("Closed shared PCA9685 servo driver")
            finally:
                cls._shared_pca = None