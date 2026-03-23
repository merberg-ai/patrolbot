from __future__ import annotations
from copy import deepcopy
from pathlib import Path
from typing import Any
import yaml
BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = BASE_DIR / 'config' / 'default.yaml'
RUNTIME_CONFIG_PATH = BASE_DIR / 'config' / 'runtime.yaml'
def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result
def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text()) or {}
    if not isinstance(data, dict):
        raise ValueError(f'Config file {path} must contain a mapping at top level')
    return data
def load_runtime_config() -> dict[str, Any]:
    return _load_yaml(RUNTIME_CONFIG_PATH)
def load_config() -> dict[str, Any]:
    return _deep_merge(_load_yaml(DEFAULT_CONFIG_PATH), load_runtime_config())
def save_runtime_config(data: dict[str, Any]) -> None:
    RUNTIME_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    RUNTIME_CONFIG_PATH.write_text(yaml.safe_dump(data, sort_keys=False))
