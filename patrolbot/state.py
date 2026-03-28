from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


def _default_sensor_entry(name: str, enabled: bool = False, use_mode: str = 'off') -> dict[str, Any]:
    return {
        'name': name,
        'configured': bool(enabled),
        'initialized': False,
        'detected': False,
        'healthy': False,
        'enabled': bool(enabled),
        'use_mode': use_mode,
        'available': False,
        'last_distance_cm': None,
        'last_good_read_ts': None,
        'last_probe_ts': None,
        'last_error': None,
        'details': None,
    }


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
    system_status: str = 'booting'
    status_led_reason: str | None = None

    network_connected: bool = False
    network_ssid: str | None = None
    network_ip: str | None = None
    network_last_error: str | None = None

    sensor_status: dict[str, dict[str, Any]] = field(default_factory=lambda: {
        'front_ultrasonic': _default_sensor_entry('Front Ultrasonic', enabled=True, use_mode='safety_only'),
        'rear_ultrasonic': _default_sensor_entry('Rear Ultrasonic', enabled=False, use_mode='off'),
    })

    patrol_enabled: bool = False
    patrol_mode: str = 'patrol'
    patrol_drive_state: str = 'idle'
    patrol_speed: int = 0
    patrol_targets: list[str] = field(default_factory=list)
    patrol_detect_count: int = 0
    patrol_last_detected: str | None = None
    patrol_metrics: dict[str, Any] = field(default_factory=dict)
    patrol_disable_reason: str | None = None
    patrol_last_error: str | None = None

    tracking_enabled: bool = False
    tracking_mode: str = 'camera_track'
    tracking_detector: str = 'face'
    tracking_target_acquired: bool = False
    tracking_box: dict[str, Any] | None = None
    tracking_target_label: str | None = None
    tracking_target_confidence: float | None = None
    tracking_frame_size: dict[str, int] | None = None
    tracking_last_error: str | None = None
    tracking_last_detection_count: int = 0
    tracking_detector_available: bool = False
    tracking_detector_status: str = 'inactive'
    tracking_detector_details: dict[str, Any] = field(default_factory=dict)
    tracking_yolo_available: bool = False
    tracking_preferred_target: str = 'largest'
    tracking_scan_active: bool = False
    tracking_metrics: dict[str, Any] = field(default_factory=dict)
    tracking_fps_actual: float = 0.0
    tracking_mjpeg_clients: int = 0
    tracking_follow_distance_cm: float | None = None
    tracking_follow_state: str = 'stopped'
    tracking_disable_reason: str | None = None
    tracking_overlay_enabled: bool = True

    snapshot_last_saved: str | None = None
    snapshot_count: int = 0
