from __future__ import annotations

from copy import deepcopy
from typing import Any

from patrolbot.config import load_runtime_config, save_runtime_config


AWB_MODE_OPTIONS = [
    {"value": "auto", "label": "Auto"},
    {"value": "tungsten", "label": "Tungsten"},
    {"value": "fluorescent", "label": "Fluorescent"},
    {"value": "indoor", "label": "Indoor"},
    {"value": "daylight", "label": "Daylight"},
    {"value": "cloudy", "label": "Cloudy"},
    {"value": "custom", "label": "Manual Gains"},
]

CAMERA_FIELDS: dict[str, dict[str, Any]] = {
    "brightness": {"type": "float", "min": -1.0, "max": 1.0, "default": -0.05},
    "contrast": {"type": "float", "min": 0.0, "max": 32.0, "default": 1.15},
    "saturation": {"type": "float", "min": 0.0, "max": 32.0, "default": 1.1},
    "sharpness": {"type": "float", "min": 0.0, "max": 16.0, "default": 1.0},
    "exposure_compensation": {"type": "float", "min": -8.0, "max": 8.0, "default": -1.0},
    "awb_mode": {"type": "enum", "choices": [item["value"] for item in AWB_MODE_OPTIONS], "default": "auto"},
    "manual_red_gain": {"type": "float_or_none", "min": 0.0, "max": 32.0, "default": None},
    "manual_blue_gain": {"type": "float_or_none", "min": 0.0, "max": 32.0, "default": None},
    "width": {"type": "int", "min": 160, "max": 1920, "default": 640, "persist": False},
    "height": {"type": "int", "min": 120, "max": 1080, "default": 480, "persist": False},
    "fps": {"type": "int", "min": 5, "max": 30, "default": 20, "persist": True},
    "rotation": {"type": "int", "min": 0, "max": 360, "default": 0, "persist": False},
}


def _clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(max_value, value))


def get_camera_schema() -> dict[str, Any]:
    fields = {}
    for name, spec in CAMERA_FIELDS.items():
        cloned = deepcopy(spec)
        if name == "awb_mode":
            cloned["options"] = deepcopy(AWB_MODE_OPTIONS)
        fields[name] = cloned
    return {"fields": fields}


def normalize_camera_settings(source: dict[str, Any] | None) -> tuple[dict[str, Any], list[str]]:
    source = source or {}
    normalized: dict[str, Any] = {}
    warnings: list[str] = []

    for name, spec in CAMERA_FIELDS.items():
        value = source.get(name, spec.get("default"))
        field_type = spec["type"]

        if field_type == "enum":
            if value is None:
                value = spec["default"]
            value = str(value).strip().lower()
            if value not in spec["choices"]:
                warnings.append(f"{name} value {value!r} is unsupported, using {spec['default']!r}.")
                value = spec["default"]
        elif field_type == "int":
            try:
                value = int(value)
            except (TypeError, ValueError):
                warnings.append(f"{name} value {value!r} is invalid, using {spec['default']!r}.")
                value = int(spec["default"])
            value = int(_clamp(value, int(spec["min"]), int(spec["max"])))
        elif field_type == "float":
            try:
                value = float(value)
            except (TypeError, ValueError):
                warnings.append(f"{name} value {value!r} is invalid, using {spec['default']!r}.")
                value = float(spec["default"])
            value = round(_clamp(value, float(spec["min"]), float(spec["max"])), 3)
        elif field_type == "float_or_none":
            if value in (None, "", "null"):
                value = None
            else:
                try:
                    value = float(value)
                except (TypeError, ValueError):
                    warnings.append(f"{name} value {value!r} is invalid, clearing it.")
                    value = None
                if value is not None:
                    value = round(_clamp(value, float(spec["min"]), float(spec["max"])), 3)
        normalized[name] = value

    return normalized, warnings


def build_camera_settings_from_config(config: dict[str, Any]) -> dict[str, Any]:
    camera_cfg = deepcopy((config or {}).get("camera", {}))
    normalized, _warnings = normalize_camera_settings(camera_cfg)
    return normalized


def persist_camera_settings(settings: dict[str, Any]) -> None:
    runtime_cfg = load_runtime_config()
    runtime_cfg.setdefault("camera", {})
    for name, spec in CAMERA_FIELDS.items():
        if not spec.get("persist", True):
            continue
        runtime_cfg["camera"][name] = settings.get(name, spec.get("default"))
    save_runtime_config(runtime_cfg)


def update_runtime_camera_config(runtime, settings: dict[str, Any]) -> None:
    runtime.config.setdefault("camera", {})
    for name, spec in CAMERA_FIELDS.items():
        runtime.config["camera"][name] = settings.get(name, spec.get("default"))


def metadata_for_response() -> dict[str, Any]:
    return {
        "schema": get_camera_schema(),
        "supports_manual_gains": True,
    }
