from __future__ import annotations

import time
from statistics import median

from smbus2 import SMBus


class BatteryMonitor:
    def __init__(self, config: dict, logger):
        self.config = config or {}
        self.logger = logger

        batt_cfg = self.config.get('battery', {})
        self.low_voltage = float(batt_cfg.get('low_voltage', 6.8))
        self.critical_voltage = float(batt_cfg.get('critical_voltage', 6.4))

        self.address = int(batt_cfg.get('address', 0x48))
        self.bus_num = int(batt_cfg.get('bus', 1))
        self.channel = int(batt_cfg.get('channel', 0))
        self.command = int(batt_cfg.get('command', 0x84))
        self.adc_vref = float(batt_cfg.get('adc_vref', 4.93))
        self.r_high = float(batt_cfg.get('divider_r_high', 3000.0))
        self.r_low = float(batt_cfg.get('divider_r_low', 1000.0))
        self.samples = int(batt_cfg.get('samples', 7))
        self.sample_delay_s = float(batt_cfg.get('sample_delay_s', 0.01))
        self.offset = float(batt_cfg.get('offset', 0.0))
        self.full_voltage = float(batt_cfg.get('full_voltage', 8.4))

        self.division_ratio = self.r_low / (self.r_high + self.r_low)
        self.bus = SMBus(self.bus_num)
        self.logger.info(
            'Battery monitor initialized: bus=%s addr=0x%02X channel=%s vref=%.2f',
            self.bus_num,
            self.address,
            self.channel,
            self.adc_vref,
        )

    def _analog_read(self, channel: int) -> int:
        mux = ((channel << 2 | channel >> 1) & 0x07) << 4
        return int(self.bus.read_byte_data(self.address, self.command | mux))

    def _sample_voltage(self) -> float:
        adc_value = self._analog_read(self.channel)
        a0_voltage = (adc_value / 255.0) * self.adc_vref
        return (a0_voltage / self.division_ratio) + self.offset

    def read_voltage(self) -> float | None:
        values: list[float] = []
        for _ in range(max(1, self.samples)):
            try:
                values.append(self._sample_voltage())
            except Exception as exc:
                self.logger.warning('Battery read failed: %s', exc)
            time.sleep(self.sample_delay_s)

        if not values:
            return None

        med = median(values)
        filtered = [v for v in values if abs(v - med) < 1.0]
        final = filtered if filtered else values
        return round(sum(final) / len(final), 2)

    def get_status(self, voltage: float | None = None) -> str:
        if voltage is None:
            voltage = self.read_voltage()
        if voltage is None:
            return 'unknown'
        if voltage <= self.critical_voltage:
            return 'critical'
        if voltage <= self.low_voltage:
            return 'low'
        return 'ok'

    def estimate_percent(self, voltage: float | None = None) -> int | None:
        if voltage is None:
            voltage = self.read_voltage()
        if voltage is None:
            return None
        if self.full_voltage <= self.critical_voltage:
            return 0
        percent = ((float(voltage) - self.critical_voltage) / (self.full_voltage - self.critical_voltage)) * 100.0
        return int(round(max(0.0, min(100.0, percent))))