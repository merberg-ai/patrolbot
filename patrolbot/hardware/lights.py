from __future__ import annotations
from dataclasses import dataclass
from typing import Dict

try:
    from gpiozero import PWMOutputDevice
except Exception:
    PWMOutputDevice = None


class _DummyPwm:
    def __init__(self, pin: int):
        self.pin = pin
        self.value = 0.0

    def close(self) -> None:
        return None


@dataclass
class _EyePins:
    r: int
    g: int
    b: int


class RgbEyes:
    def __init__(self, config: dict, logger):
        self.config = config
        self.logger = logger
        self.enabled = config['lights'].get('enabled', True)
        self.left_pins = _EyePins(**config['lights']['left_pins'])
        self.right_pins = _EyePins(**config['lights']['right_pins'])
        self._channels: Dict[str, object] = {}
        self.initialized = False

    def _make_pwm(self, pin: int):
        if not self.enabled or PWMOutputDevice is None:
            if PWMOutputDevice is None:
                self.logger.warning('gpiozero unavailable; using dummy PWM for pin %s', pin)
            return _DummyPwm(pin)
        # Adeept uses active-low PWM for the eye LEDs.
        return PWMOutputDevice(pin, active_high=False, initial_value=0.0, frequency=2000)

    def initialize(self) -> None:
        pin_map = {
            'left_r': self.left_pins.r,
            'left_g': self.left_pins.g,
            'left_b': self.left_pins.b,
            'right_r': self.right_pins.r,
            'right_g': self.right_pins.g,
            'right_b': self.right_pins.b,
        }
        for name, pin in pin_map.items():
            self._channels[name] = self._make_pwm(pin)
        self.initialized = True
        self.logger.info('RGB eyes initialized with logical pin map: %s', pin_map)
        self.off()

    @staticmethod
    def _norm(value: int) -> float:
        return max(0, min(255, int(value))) / 255.0

    def _set_eye(self, prefix: str, r: int, g: int, b: int) -> None:
        if not self.initialized:
            return
        self._channels[f'{prefix}_r'].value = self._norm(r)
        self._channels[f'{prefix}_g'].value = self._norm(g)
        self._channels[f'{prefix}_b'].value = self._norm(b)

    def set_left(self, r: int, g: int, b: int) -> None:
        self._set_eye('left', r, g, b)

    def set_right(self, r: int, g: int, b: int) -> None:
        self._set_eye('right', r, g, b)

    def set_both(self, r: int, g: int, b: int) -> None:
        self.set_left(r, g, b)
        self.set_right(r, g, b)

    def off(self) -> None:
        self.set_both(0, 0, 0)

    def close(self) -> None:
        self.off()
        for channel in self._channels.values():
            close = getattr(channel, 'close', None)
            if callable(close):
                close()
        self._channels.clear()
        self.initialized = False
