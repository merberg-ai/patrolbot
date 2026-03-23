from __future__ import annotations


class BaseDetector:
    name = "base"

    def is_available(self) -> bool:
        return True

    def detect(self, frame):
        """Return a list of Detection objects."""
        raise NotImplementedError
