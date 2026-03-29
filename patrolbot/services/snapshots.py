from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
import re

from patrolbot.config import BASE_DIR


class SnapshotService:
    def __init__(self, config: dict, logger, runtime=None):
        self.config = config
        self.logger = logger
        self.runtime = runtime
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

    def _slugify(self, value: str | None) -> str:
        text = (value or 'snapshot').strip().lower()
        text = re.sub(r'[^a-z0-9]+', '_', text).strip('_')
        return text or 'snapshot'

    def _capture_bgr_frame(self):
        runtime = self.runtime
        if runtime is None:
            raise RuntimeError('snapshot runtime unavailable')
        camera = getattr(runtime.registry, 'camera', None)
        if camera is None:
            raise RuntimeError('camera unavailable')
        frame = camera.read_bgr() if hasattr(camera, 'read_bgr') else None
        if frame is None:
            raise RuntimeError('camera returned no frame')
        vision = getattr(runtime, 'vision', None)
        if vision and hasattr(vision, 'render_snapshot_frame'):
            try:
                rendered = vision.render_snapshot_frame(frame)
                if rendered is not None:
                    frame = rendered
            except Exception as exc:
                self.logger.warning('Snapshot overlay rendering failed: %s', exc)
        return frame

    def take_snapshot(self, reason: str = '', label: str | None = None) -> dict[str, Any]:
        runtime = self.runtime
        frame = self._capture_bgr_frame()
        camera = getattr(runtime.registry, 'camera', None) if runtime else None
        if camera is None or not hasattr(camera, 'encode_jpeg'):
            raise RuntimeError('camera jpeg encoder unavailable')
        jpeg = camera.encode_jpeg(frame)
        if not jpeg:
            raise RuntimeError('jpeg encoding failed')

        stamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        suffix = self._slugify(label or reason or 'snapshot')
        filename = f'{stamp}_{suffix}.jpg'
        path = self.directory_path() / filename
        path.write_bytes(jpeg)

        if runtime is not None:
            runtime.state.snapshot_last_saved = filename
            runtime.state.snapshot_count = len(self.list_snapshots(limit=9999))

        self.logger.info('Snapshot saved: %s reason=%s label=%s', filename, reason or '-', label or '-')
        return {
            'ok': True,
            'name': filename,
            'path': str(path),
            'label': label,
            'reason': reason,
            'size_bytes': path.stat().st_size,
            'timestamp': datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec='seconds'),
        }

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
