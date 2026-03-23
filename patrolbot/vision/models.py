from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Detection:
    label: str
    confidence: float
    x: int
    y: int
    w: int
    h: int
    center_x: float
    center_y: float
    area: int
    detector: str


@dataclass
class TrackedTarget:
    detection: Detection | None
    error_x: float = 0.0
    error_y: float = 0.0
    acquired: bool = False
    lost_age_s: float = 0.0
