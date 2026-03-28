from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from patrolbot.config import BASE_DIR


class SnapshotService:
    def __init__(self, config: dict, logger):
        self.config = config
        self.logger = logger
        snap_cfg = config.get('snapshots', {}) or {}
        directory = snap_cfg.get('directory', 'snapshots')
        self.base_dir = (BASE_DIR / directory).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def directory_path(self) -> Path:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        return self.base_dir

    def list_snapshots(self, limit: int | None = None) -> list[dict[str, Any]]:
        limit = int(limit or self.config.get('snapshots', {}).get('max_list_items', 200))
        items: list[dict[str, Any]] = []
        for path in sorted(self.directory_path().glob('*'), key=lambda p: p.stat().st_mtime, reverse=True):
            if not path.is_file() or path.suffix.lower() not in {'.jpg', '.jpeg', '.png', '.webp'}:
                continue
            stem = path.stem
            label = None
            timestamp = None
            if '_' in stem:
                parts = stem.split('_')
                if len(parts) >= 3:
                    timestamp = f"{parts[0]} {parts[1].replace('-', ':')}"
                    label = '_'.join(parts[2:])
            stat = path.stat()
            items.append({
                'name': path.name,
                'label': label,
                'timestamp': timestamp or datetime.fromtimestamp(stat.st_mtime).isoformat(timespec='seconds'),
                'size_bytes': stat.st_size,
                'mtime': stat.st_mtime,
            })
            if len(items) >= limit:
                break
        return items

    def resolve_snapshot(self, name: str) -> Path:
        path = (self.directory_path() / name).resolve()
        if self.directory_path() not in path.parents and path != self.directory_path():
            raise ValueError('invalid snapshot path')
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(name)
        return path

    def delete_snapshot(self, name: str) -> bool:
        path = self.resolve_snapshot(name)
        path.unlink(missing_ok=False)
        return True

    def delete_all(self) -> int:
        count = 0
        for item in list(self.directory_path().glob('*')):
            if item.is_file() and item.suffix.lower() in {'.jpg', '.jpeg', '.png', '.webp'}:
                item.unlink(missing_ok=True)
                count += 1
        return count
