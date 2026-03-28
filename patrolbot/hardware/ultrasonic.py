from __future__ import annotations

import time
from statistics import median

from gpiozero import DistanceSensor


class UltrasonicSensor:
    def __init__(self, config: dict, logger, config_key: str = 'ultrasonic'):
        self.config = config or {}
        self.logger = logger
        self.config_key = config_key
        ultra_cfg = self.config.get(self.config_key, {})

        self.trigger_pin = int(ultra_cfg.get('trigger_pin', 23))
        self.echo_pin = int(ultra_cfg.get('echo_pin', 24))
        self.max_distance_m = float(ultra_cfg.get('max_distance_m', 2.0))
        self.samples = int(ultra_cfg.get('samples', 3))
        self.sample_delay_s = float(ultra_cfg.get('sample_delay_s', 0.02))
        self.offset_cm = float(ultra_cfg.get('offset_cm', 0.0))
        self.last_distance_cm = None
        self.last_error = None
        self.last_good_read_ts = None

        self.sensor = DistanceSensor(
            echo=self.echo_pin,
            trigger=self.trigger_pin,
            max_distance=self.max_distance_m,
        )
        self.logger.info(
            '%s sensor initialized: trigger=%s echo=%s max_distance=%.2fm samples=%s',
            self.config_key.capitalize(),
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
                self.last_error = str(exc)
                self.logger.warning('Ultrasonic read failed: %s', exc)
            time.sleep(self.sample_delay_s)

        if not values:
            return None

        value = round(median(values), 1)
        self.last_distance_cm = value
        self.last_error = None
        self.last_good_read_ts = time.time()
        return value

    def probe(self, reads: int = 3, valid_reads_required: int = 1) -> dict:
        valid = 0
        values = []
        last_error = None
        for _ in range(max(1, reads)):
            try:
                distance = self.read_cm()
                if distance is not None:
                    valid += 1
                    values.append(distance)
            except Exception as exc:
                last_error = str(exc)
            time.sleep(self.sample_delay_s)
        detected = valid >= max(1, valid_reads_required)
        return {
            'initialized': True,
            'detected': detected,
            'healthy': detected,
            'last_distance_cm': round(median(values), 1) if values else None,
            'last_good_read_ts': self.last_good_read_ts,
            'last_error': None if detected else (last_error or self.last_error or 'no valid echo'),
            'details': {
                'reads': reads,
                'valid_reads': valid,
                'trigger_pin': self.trigger_pin,
                'echo_pin': self.echo_pin,
            },
        }

    def close(self) -> None:
        try:
            self.sensor.close()
        except Exception:
            pass
