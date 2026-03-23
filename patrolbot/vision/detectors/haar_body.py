from __future__ import annotations

import cv2

from patrolbot.vision.detectors.base import BaseDetector
from patrolbot.vision.models import Detection


class HaarBodyDetector(BaseDetector):
    name = 'body'

    def __init__(self):
        self.hog = cv2.HOGDescriptor()
        self.hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())

    def is_available(self) -> bool:
        return self.hog is not None

    def detect(self, frame):
        if frame is None or not self.is_available():
            return []
        scale = 1.0
        h, w = frame.shape[:2]
        work = frame
        if w > 640:
            scale = 640.0 / float(w)
            nh = max(64, int(h * scale))
            work = cv2.resize(frame, (640, nh))
        rects, weights = self.hog.detectMultiScale(
            work,
            winStride=(8, 8),
            padding=(8, 8),
            scale=1.03,
            useMeanshiftGrouping=False,
        )
        out = []
        inv = 1.0 / scale
        for (x, y, ww, hh), conf in zip(rects, weights):
            x = int(x * inv)
            y = int(y * inv)
            ww = int(ww * inv)
            hh = int(hh * inv)
            if hh < ww or hh < 100:
                continue
            out.append(Detection('person', float(conf), x, y, ww, hh, x + ww / 2.0, y + hh / 2.0, int(ww * hh), self.name))
        return out
