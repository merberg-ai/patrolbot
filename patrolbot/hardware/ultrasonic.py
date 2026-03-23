from __future__ import annotations

import time
from statistics import median

from gpiozero import DistanceSensor


class UltrasonicSensor:
    def __init__(self, config: dict, logger):
        self.config = config or {}
        self.logger = logger
        ultra_cfg = self.config.get('ultrasonic', {})

        self.trigger_pin = int(ultra_cfg.get('trigger_pin', 23))
        self.echo_pin = int(ultra_cfg.get('echo_pin', 24))
        self.max_distance_m = float(ultra_cfg.get('max_distance_m', 2.0))
        self.samples = int(ultra_cfg.get('samples', 3))
        self.sample_delay_s = float(ultra_cfg.get('sample_delay_s', 0.02))
        self.offset_cm = float(ultra_cfg.get('offset_cm', 0.0))

        self.sensor = DistanceSensor(
            echo=self.echo_pin,
            trigger=self.trigger_pin,
            max_distance=self.max_distance_m,
        )
        self.logger.info(
            'Ultrasonic sensor initialized: trigger=%s echo=%s max_distance=%.2fm samples=%s',
            self.trigger_pin,
            self.echo_pin,
            self.max_distance_m,
            self.samples,
        )

    def read_cm(self) -> float | None:
        values: list[float] = []
        for _ in range(max(1, self.samples)):
            try:
                distance_cm = (float(self.sensor.distance) * 100.0) + self.offset_cm
                if 0.0 <= distance_cm <= (self.max_distance_m * 100.0 + 5.0):
                    values.append(distance_cm)
            except Exception as exc:
                self.logger.warning('Ultrasonic read failed: %s', exc)
            time.sleep(self.sample_delay_s)

        if not values:
            return None

        return round(median(values), 1)
