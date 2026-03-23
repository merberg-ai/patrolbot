from __future__ import annotations

from patrolbot.vision.detectors.haar_face import HaarFaceDetector
from patrolbot.vision.detectors.haar_body import HaarBodyDetector
from patrolbot.vision.detectors.motion import MotionDetector
from patrolbot.vision.detectors.yolo import YoloDetector


def build_detector(name: str, config: dict):
    name = str(name or 'face').strip().lower()
    if name in {'face', 'haar_face'}:
        return HaarFaceDetector()
    if name in {'body', 'haar_body'}:
        return HaarBodyDetector()
    if name == 'motion':
        return MotionDetector(min_area=int(config.get('min_area', 1500)))
    if name == 'yolo':
        raw_classes = config.get('yolo_classes', [])
        if isinstance(raw_classes, str):
            raw_classes = [x.strip() for x in raw_classes.split(',') if x.strip()]
        return YoloDetector(
            model_name=str(config.get('yolo_model', 'yolov8n.pt')),
            class_names=list(raw_classes or []),
            confidence_min=float(config.get('confidence_min', 0.45)),
            max_results=int(config.get('max_results', 20)),
            enabled=bool(config.get('enable_yolo', False)),
            imgsz=int(config.get('yolo_imgsz', 480)),
        )
    return HaarFaceDetector()


__all__ = [
    'HaarFaceDetector',
    'HaarBodyDetector',
    'MotionDetector',
    'YoloDetector',
    'build_detector',
]
