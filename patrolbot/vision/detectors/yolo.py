from __future__ import annotations

import logging

from patrolbot.vision.detectors.base import BaseDetector
from patrolbot.vision.models import Detection

logger = logging.getLogger('patrolbot')


class YoloDetector(BaseDetector):
    name = 'yolo'

    def __init__(
        self,
        model_name: str = 'yolov8n.pt',
        class_names: list[str] | None = None,
        confidence_min: float = 0.45,
        max_results: int = 20,
        enabled: bool = False,
        imgsz: int = 480,
    ):
        self.class_names = [c.strip().lower() for c in (class_names or []) if str(c).strip()]
        self.confidence_min = float(confidence_min)
        self.max_results = int(max_results)
        self.imgsz = int(imgsz)
        self._model = None
        self._error = None
        self._model_name = model_name
        self._enabled = bool(enabled)
        self._yolo_cls = None
        if not self._enabled:
            self._error = 'disabled by config (set tracking.enable_yolo=true to allow YOLO)'
            return
        try:
            from ultralytics import YOLO
            self._yolo_cls = YOLO
        except Exception as exc:
            self._error = f'ultralytics import failed: {exc}'
            logger.error('YOLO unavailable: %s', exc)

    def _ensure_model(self) -> bool:
        if self._model is not None:
            return True
        if self._yolo_cls is None:
            return False
        try:
            self._model = self._yolo_cls(self._model_name)
            self._error = None
            return True
        except Exception as exc:
            self._error = f'model load failed: {exc}'
            self._model = None
            logger.error('YOLO model load failed for %s: %s', self._model_name, exc)
            return False

    def is_available(self) -> bool:
        return self._enabled and self._yolo_cls is not None

    def status(self) -> str:
        if not self._enabled:
            return self._error or 'disabled'
        if self._model is not None:
            return f'ready: {self._model_name}'
        if self._error and 'model load failed' in self._error:
            return f'error: {self._error}'
        if self._yolo_cls is not None:
            return f'available (lazy load): {self._model_name}'
        return f'unavailable: {self._error or "import failed"}'

    def detect(self, frame):
        if frame is None or not self._ensure_model():
            return []
        results = self._model.predict(
            frame,
            verbose=False,
            conf=self.confidence_min,
            max_det=self.max_results,
            imgsz=self.imgsz,
            device='cpu',
        )
        out = []
        if not results:
            return out
        result = results[0]
        names = getattr(result, 'names', {}) or {}
        boxes = getattr(result, 'boxes', None)
        if boxes is None:
            return out
        for box in boxes:
            cls_id = int(box.cls[0].item())
            conf = float(box.conf[0].item())
            x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
            label = str(names.get(cls_id, cls_id)).lower()
            if self.class_names and label not in self.class_names:
                continue
            bw = max(0, x2 - x1)
            bh = max(0, y2 - y1)
            out.append(Detection(label, conf, x1, y1, bw, bh, x1 + bw / 2.0, y1 + bh / 2.0, int(bw * bh), self.name))
        return out
