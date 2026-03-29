import sys
sys.path.insert(0, r"d:\SRC\patrolbot")
from patrolbot.vision.detectors.yolo import YoloDetector
import cv2

frame = cv2.imread("d:\\SRC\\patrolbot\\zidane.jpg")

det = YoloDetector(enabled=True)
print("Status:", det.status())
boxes = det.detect(frame)
print(f"Detected {len(boxes)} objects")
for b in boxes:
    print(b)
