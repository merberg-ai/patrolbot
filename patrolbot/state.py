from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

@dataclass
class RuntimeState:
    mode: str = 'idle'
    led_state: str = 'OFF'
    led_custom: dict[str, int] | None = None
    motor_state: str = 'stopped'
    speed: int = 0
    estop_latched: bool = False
    motion_locked: bool = False
    steering_angle: int = 90
    pan_angle: int = 90
    tilt_angle: int = 90
    telemetry: dict[str, Any] = field(default_factory=dict)

    patrol_enabled: bool = False
    patrol_mode: str = 'patrol'
    patrol_drive_state: str = 'stopped'
    patrol_speed: int = 0
    patrol_targets: list[str] = field(default_factory=list)
    patrol_detect_count: int = 0
    patrol_last_detected: str | None = None
    patrol_metrics: dict[str, Any] = field(default_factory=dict)
    patrol_disable_reason: str | None = None
    patrol_last_error: str | None = None
