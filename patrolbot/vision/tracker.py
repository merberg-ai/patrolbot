from __future__ import annotations

from math import hypot


class VisionTracker:
    def __init__(self, config: dict | None = None):
        self.apply_config(config or {})

    def apply_config(self, config: dict | None) -> None:
        config = config or {}
        self.pan_gain = float(config.get('pan_gain', 0.06))
        self.tilt_gain = float(config.get('tilt_gain', 0.06))
        self.x_deadzone_px = int(config.get('x_deadzone_px', 48))
        self.y_deadzone_px = int(config.get('y_deadzone_px', 36))
        self.smoothing_alpha = float(config.get('smoothing_alpha', 0.4))
        self.invert_error_x = bool(config.get('invert_error_x', False))
        self.invert_error_y = bool(config.get('invert_error_y', False))
        self.preferred_target = str(config.get('preferred_target', 'largest')).strip().lower()
        self.target_label = str(config.get('target_label', '') or '').strip().lower()
        self.min_target_area = int(config.get('min_target_area', 0))
        self.lock_iou_min = float(config.get('follow_target_lock_iou_min', 0.12))
        self.lock_center_px = float(config.get('follow_target_lock_center_px', 160))
        self.switch_margin = float(config.get('follow_target_switch_margin', 1.2))
        self._last_target = None

    def _distance_from_center(self, det, frame_w: int, frame_h: int) -> float:
        dx = det.center_x - (frame_w / 2.0)
        dy = det.center_y - (frame_h / 2.0)
        return (dx * dx) + (dy * dy)


    def reset(self) -> None:
        self._last_target = None

    def _iou(self, a, b) -> float:
        if a is None or b is None:
            return 0.0
        ax1, ay1, ax2, ay2 = a.x, a.y, a.x + a.w, a.y + a.h
        bx1, by1, bx2, by2 = b.x, b.y, b.x + b.w, b.y + b.h
        ix1 = max(ax1, bx1)
        iy1 = max(ay1, by1)
        ix2 = min(ax2, bx2)
        iy2 = min(ay2, by2)
        iw = max(0, ix2 - ix1)
        ih = max(0, iy2 - iy1)
        inter = iw * ih
        if inter <= 0:
            return 0.0
        union = max(1, (a.w * a.h) + (b.w * b.h) - inter)
        return inter / float(union)

    def _center_distance(self, a, b) -> float:
        return hypot(float(a.center_x) - float(b.center_x), float(a.center_y) - float(b.center_y))

    def _preferred_score(self, det, frame_w: int, frame_h: int):
        preferred = self.preferred_target
        if preferred == 'center':
            return (-self._distance_from_center(det, frame_w, frame_h), getattr(det, 'confidence', 0.0), getattr(det, 'area', 0))
        if preferred == 'highest_confidence':
            return (getattr(det, 'confidence', 0.0), getattr(det, 'area', 0), -self._distance_from_center(det, frame_w, frame_h))
        return (getattr(det, 'area', 0), getattr(det, 'confidence', 0.0), -self._distance_from_center(det, frame_w, frame_h))

    def _matches_locked_target(self, det) -> bool:
        last = self._last_target
        if last is None:
            return False
        if getattr(last, 'label', None) and getattr(det, 'label', None) and str(last.label).lower() != str(det.label).lower():
            return False
        iou = self._iou(last, det)
        center_dist = self._center_distance(last, det)
        return iou >= self.lock_iou_min or center_dist <= self.lock_center_px

    def choose_target(self, detections, frame_w: int, frame_h: int):
        if not detections:
            self._last_target = None
            return None
        candidates = [d for d in detections if getattr(d, 'area', 0) >= self.min_target_area]
        if not candidates:
            self._last_target = None
            return None
        if self.target_label:
            labeled = [d for d in candidates if str(getattr(d, 'label', '')).lower() == self.target_label]
            if labeled:
                candidates = labeled

        locked_choice = None
        if self._last_target is not None:
            locked_pool = [d for d in candidates if self._matches_locked_target(d)]
            if locked_pool:
                locked_choice = max(
                    locked_pool,
                    key=lambda d: (self._iou(self._last_target, d), -self._center_distance(self._last_target, d), *self._preferred_score(d, frame_w, frame_h)),
                )

        preferred_choice = max(candidates, key=lambda d: self._preferred_score(d, frame_w, frame_h))
        choice = preferred_choice
        if locked_choice is not None:
            locked_score = self._preferred_score(locked_choice, frame_w, frame_h)
            preferred_score = self._preferred_score(preferred_choice, frame_w, frame_h)
            if preferred_choice is locked_choice:
                choice = locked_choice
            elif preferred_score[0] <= 0:
                choice = locked_choice
            elif locked_score[0] > 0 and (preferred_score[0] / max(1e-6, locked_score[0])) < self.switch_margin:
                choice = locked_choice

        self._last_target = choice
        return choice

    def move_to_target(self, target, frame_w: int, frame_h: int, current_pan: float, current_tilt: float):
        if not target:
            return None, None
        err_x = float(target.center_x - (frame_w / 2.0))
        err_y = float(target.center_y - (frame_h / 2.0))
        if self.invert_error_x:
            err_x = -err_x
        if self.invert_error_y:
            err_y = -err_y
        adj_x = 0.0 if abs(err_x) < self.x_deadzone_px else err_x
        adj_y = 0.0 if abs(err_y) < self.y_deadzone_px else err_y
        target_pan = float(current_pan) + (adj_x * self.pan_gain)
        target_tilt = float(current_tilt) + (adj_y * self.tilt_gain)
        alpha = max(0.0, min(1.0, self.smoothing_alpha))
        next_pan = (alpha * target_pan) + ((1.0 - alpha) * float(current_pan))
        next_tilt = (alpha * target_tilt) + ((1.0 - alpha) * float(current_tilt))
        return next_pan, next_tilt
