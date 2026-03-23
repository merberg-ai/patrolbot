from __future__ import annotations

import cv2

from patrolbot.vision.detectors.base import BaseDetector
from patrolbot.vision.models import Detection


class HaarFaceDetector(BaseDetector):
    name = 'face'

    def __init__(self):
        base = cv2.data.haarcascades
        self.cascade = cv2.CascadeClassifier(base + 'haarcascade_frontalface_default.xml')
        self.profile = cv2.CascadeClassifier(base + 'haarcascade_profileface.xml')

    def is_available(self) -> bool:
        return self.cascade is not None and not self.cascade.empty()

    def _mk(self, x, y, w, h, label='face', conf=1.0):
        return Detection(label, conf, int(x), int(y), int(w), int(h), x + w / 2.0, y + h / 2.0, int(w * h), self.name)

    def detect(self, frame):
        if frame is None or not self.is_available():
            return []
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.equalizeHist(gray)
        items = self.cascade.detectMultiScale(
            gray,
            scaleFactor=1.05,
            minNeighbors=3,
            minSize=(36, 36),
            flags=cv2.CASCADE_SCALE_IMAGE,
        )
        out = [self._mk(x, y, w, h) for (x, y, w, h) in items]
        if self.profile is not None and not self.profile.empty():
            prof = self.profile.detectMultiScale(
                gray,
                scaleFactor=1.05,
                minNeighbors=3,
                minSize=(36, 36),
                flags=cv2.CASCADE_SCALE_IMAGE,
            )
            for (x, y, w, h) in prof:
                out.append(self._mk(x, y, w, h, label='face-profile', conf=0.9))
            flipped = cv2.flip(gray, 1)
            prof2 = self.profile.detectMultiScale(
                flipped,
                scaleFactor=1.05,
                minNeighbors=3,
                minSize=(36, 36),
                flags=cv2.CASCADE_SCALE_IMAGE,
            )
            fw = gray.shape[1]
            for (x, y, w, h) in prof2:
                rx = fw - (x + w)
                out.append(self._mk(rx, y, w, h, label='face-profile', conf=0.9))
        dedup = []
        for d in sorted(out, key=lambda z: z.area, reverse=True):
            keep = True
            for k in dedup:
                ix1 = max(d.x, k.x)
                iy1 = max(d.y, k.y)
                ix2 = min(d.x + d.w, k.x + k.w)
                iy2 = min(d.y + d.h, k.y + k.h)
                iw = max(0, ix2 - ix1)
                ih = max(0, iy2 - iy1)
                inter = iw * ih
                union = d.area + k.area - inter
                iou = (inter / union) if union else 0.0
                if iou > 0.4:
                    keep = False
                    break
            if keep:
                dedup.append(d)
        return dedup
