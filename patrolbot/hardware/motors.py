from __future__ import annotations

import threading
import time

import board
import busio
from adafruit_motor import motor
from adafruit_pca9685 import PCA9685


class MotorController:
    """
    patrolbot drive motor controller for the Adeept PiCar-B style PCA9685 HAT.

    This keeps the existing patrolbot architecture intact, but uses the same
    effective motor-channel layout as the known-good reference helper:

        1 -> (15, 14)
        2 -> (12, 13)
        3 -> (11, 10)
        4 -> (8, 9)

    The reference motor test drives all four motor outputs together for
    forward/reverse. patrolbot now does the same by default, while still exposing
    the existing forward/backward/stop/estop API the rest of the app expects.
    """

    _shared_pca = None
    _shared_lock = threading.Lock()

    DEFAULT_CHANNEL_PAIRS = {
        1: (15, 14),
        2: (12, 13),
        3: (11, 10),
        4: (8, 9),
    }

    def __init__(self, config: dict, logger, hat=None):
        self.config = config or {}
        self.logger = logger
        self.hat = hat

        motor_cfg = self.config.get("motors", {})
        self.address = int(motor_cfg.get("address", 0x5F))
        self.frequency = int(motor_cfg.get("frequency", 50))
        self.default_speed = int(motor_cfg.get("default_speed", 40))
        self.timeout_s = float(motor_cfg.get("command_timeout_s", 0.75))
        self.motion_locked = False
        self.estop_latched = False

        raw_enabled = motor_cfg.get("enabled_channels", [1, 2, 3, 4])
        self.enabled_channels = [int(ch) for ch in raw_enabled]

        raw_inverted = motor_cfg.get("invert_channels", [])
        self.invert_channels = {int(ch) for ch in raw_inverted}
        self.reverse_drive = bool(motor_cfg.get("reverse_drive", False))

        self.state = "stopped"
        self.speed = 0
        self.last_command_ts = 0.0

        self._ensure_driver()
        self._build_motors()

        self._stop_event = threading.Event()
        self._watchdog_thread = threading.Thread(
            target=self._watchdog_loop,
            name="patrolbot-motor-watchdog",
            daemon=True,
        )
        self._watchdog_thread.start()

        self.logger.info(
            "Motor controller initialized: addr=0x%02X timeout=%.2fs default_speed=%s enabled_channels=%s invert_channels=%s reverse_drive=%s",
            self.address,
            self.timeout_s,
            self.default_speed,
            self.enabled_channels,
            sorted(self.invert_channels),
            self.reverse_drive,
        )

    def _ensure_driver(self) -> None:
        with MotorController._shared_lock:
            if MotorController._shared_pca is None:
                i2c = busio.I2C(board.SCL, board.SDA)
                pca = PCA9685(i2c, address=self.address)
                pca.frequency = self.frequency
                MotorController._shared_pca = pca
                self.logger.info(
                    "Initialized shared PCA9685 motor driver at address 0x%02X, frequency=%sHz",
                    self.address,
                    self.frequency,
                )
        self.pca = MotorController._shared_pca

    def _channel_pair_for(self, idx: int) -> tuple[int, int]:
        cfg = self.config.get("motors", {}).get("channel_pairs", {})
        pair = cfg.get(str(idx), cfg.get(idx))
        if pair and len(pair) == 2:
            return int(pair[0]), int(pair[1])
        return self.DEFAULT_CHANNEL_PAIRS[idx]

    def _build_motors(self) -> None:
        self.motors = {}
        for idx in self.enabled_channels:
            in1, in2 = self._channel_pair_for(idx)
            dc = motor.DCMotor(self.pca.channels[in1], self.pca.channels[in2])
            dc.decay_mode = motor.SLOW_DECAY
            self.motors[idx] = dc
            self.logger.info("Configured motor channel %s on PCA outputs (%s, %s)", idx, in1, in2)

    @staticmethod
    def _clamp_speed(speed: int) -> int:
        return max(0, min(100, int(speed)))

    def _touch(self) -> None:
        self.last_command_ts = time.monotonic()

    def _speed_to_throttle(self, speed: int) -> float:
        return self._clamp_speed(speed) / 100.0

    def _directional_throttle(self, speed: int, forward: bool) -> float:
        throttle = self._speed_to_throttle(speed)

        if not forward:
            throttle = -throttle

        if self.reverse_drive:
            throttle = -throttle

        return throttle

    def _check_motion_allowed(self) -> None:
        if self.motion_locked:
            raise RuntimeError("motion locked: battery critical")
        if self.estop_latched:
            raise RuntimeError("motion locked: emergency stop latched")

    def _set_channel_throttle(self, channel: int, throttle: float) -> None:
        throttle = max(-1.0, min(1.0, float(throttle)))
        if channel in self.invert_channels:
            throttle = -throttle
        self.motors[channel].throttle = throttle

    def _apply_all(self, throttle: float) -> None:
        applied = {}
        for ch in self.enabled_channels:
            actual = -throttle if ch in self.invert_channels else throttle
            self.motors[ch].throttle = actual
            applied[ch] = round(actual, 3)

    def forward(self, speed: int | None = None) -> None:
        self._check_motion_allowed()
        speed = self.default_speed if speed is None else self._clamp_speed(speed)

        if self.state == "forward" and self.speed == speed:
            self._touch()
            return

        throttle = self._directional_throttle(speed, forward=True)

        self._apply_all(throttle)
        self.speed = speed
        self.state = "forward"
        self._touch()

        self.logger.info("Motors forward at %s%%", self.speed)

    def backward(self, speed: int | None = None) -> None:
        self._check_motion_allowed()
        speed = self.default_speed if speed is None else self._clamp_speed(speed)

        if self.state == "backward" and self.speed == speed:
            self._touch()
            return

        throttle = self._directional_throttle(speed, forward=False)

        self._apply_all(throttle)
        self.speed = speed
        self.state = "backward"
        self._touch()

        self.logger.info("Motors backward at %s%%", self.speed)

    def stop(self) -> None:
        if self.state == "stopped" and self.speed == 0:
            return
        for dc in self.motors.values():
            dc.throttle = 0.0
        self.speed = 0
        self.state = "stopped"
        self.logger.info("Motors stopped")

    def set_lockout(self, active: bool, reason: str = "lockout") -> None:
        active = bool(active)
        if self.motion_locked == active:
            return
        self.motion_locked = active
        if active:
            self.stop()
            self.logger.warning("Motion lockout enabled: %s", reason)
        else:
            self.logger.info("Motion lockout cleared")

    def emergency_stop(self, latch: bool = True) -> None:
        self.stop()
        self.estop_latched = bool(latch)
        self.logger.warning("Emergency stop triggered%s", " (latched)" if latch else "")

    def clear_estop(self) -> None:
        self.estop_latched = False
        self.logger.info("Emergency stop latch cleared")

    def _watchdog_loop(self) -> None:
        while not self._stop_event.wait(0.1):
            if self.state == "stopped":
                continue
            if self.timeout_s <= 0:
                continue
            age = time.monotonic() - self.last_command_ts
            if age > self.timeout_s:
                self.logger.warning("Motor command timeout reached (%.2fs); stopping motors", age)
                self.stop()

    def get_state(self) -> dict:
        age = None
        if self.last_command_ts:
            age = round(max(0.0, time.monotonic() - self.last_command_ts), 3)
        return {
            "state": self.state,
            "speed": self.speed,
            "motion_locked": self.motion_locked,
            "estop_latched": self.estop_latched,
            "last_command_age_s": age,
            "timeout_s": self.timeout_s,
            "enabled_channels": self.enabled_channels,
            "invert_channels": sorted(self.invert_channels),
            "reverse_drive": self.reverse_drive,
        }

    def close(self) -> None:
        self._stop_event.set()
        self.stop()