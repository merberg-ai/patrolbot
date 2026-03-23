from __future__ import annotations

import cv2

from patrolbot.vision.detectors.base import BaseDetector
from patrolbot.vision.models import Detection


class MotionDetector(BaseDetector):
    name = 'motion'

    def __init__(self, min_area: int = 1500):
        self.min_area = int(min_area)
        self.bg = cv2.createBackgroundSubtractorMOG2(history=400, varThreshold=24, detectShadows=False)
        self._warmup = 0

    def is_available(self) -> bool:
        return self.bg is not None

    def detect(self, frame):
        if frame is None or not self.is_available():
            return []
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (11, 11), 0)
        mask = self.bg.apply(gray)
        self._warmup += 1
        if self._warmup < 15:
            return []
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        mask = cv2.dilate(mask, kernel, iterations=1)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        out = []
        frame_area = frame.shape[0] * frame.shape[1]
        for c in contours:
            area = int(cv2.contourArea(c))
            if area < self.min_area:
                continue
            x, y, w, h = cv2.boundingRect(c)
            box_area = int(w * h)
            if box_area > int(frame_area * 0.40):
                continue
            out.append(Detection('motion', 1.0, int(x), int(y), int(w), int(h), x + w / 2.0, y + h / 2.0, box_area, self.name))
        return out
