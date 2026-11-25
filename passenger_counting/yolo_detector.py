"""
passenger_counting/yolo_detector.py
===================================
Module 4, Step 2: YOLO Person Detection
Smart Public Transport Occupancy and Fleet Monitoring System
------------------------------------------------------------
PURPOSE:
  - Load the pretrained YOLO model (e.g., yolov8n.pt or future models/weights/best.pt).
  - Detect ONLY the 'person' class (COCO class ID 0).
  - Return bounding box coordinates (x1, y1, x2, y2), confidence, and center point.
  - Draw bounding boxes, confidence scores, and detection count on frames.
  - Handle missing weights and loading errors gracefully.
  - Strictly no custom training or fine-tuning.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Tuple, Optional

import cv2
import numpy as np
from ultralytics import YOLO


PERSON_CLASS_ID = 0  # Standard COCO class ID for 'person'
DEFAULT_MODEL_PATH = "yolov8n.pt"
CUSTOM_MODEL_PATH = os.path.join("models", "weights", "best.pt")


@dataclass
class PersonDetection:
    """Represents a single detected person in a frame."""
    box: Tuple[int, int, int, int]  # (x1, y1, x2, y2)
    confidence: float
    class_id: int = PERSON_CLASS_ID
    class_name: str = "person"
    center: Tuple[int, int] = (0, 0)

    def __post_init__(self):
        x1, y1, x2, y2 = self.box
        self.center = (int((x1 + x2) / 2), int((y1 + y2) / 2))

    @property
    def width(self) -> int:
        return self.box[2] - self.box[0]

    @property
    def height(self) -> int:
        return self.box[3] - self.box[1]


class YOLOPersonDetector:
    """
    Wrapper for YOLO person detection.
    Strictly filters for class 0 ('person') and provides bounding boxes and visualizations.
    """

    def __init__(
        self,
        model_path: str = DEFAULT_MODEL_PATH,
        conf_threshold: float = 0.35,
        iou_threshold: float = 0.45,
    ):
        self.model_path = model_path
        self.conf_threshold = conf_threshold
        self.iou_threshold = iou_threshold
        self.model: Optional[YOLO] = None
        self._load_model()

    def _load_model(self):
        """Loads the YOLO model with error checking."""
        if not os.path.exists(self.model_path) and not self.model_path.endswith(".pt"):
            raise FileNotFoundError(f"Model file not found at: {self.model_path}")
        try:
            self.model = YOLO(self.model_path)
        except Exception as e:
            raise RuntimeError(f"Failed to initialize YOLO model from {self.model_path}: {e}")

    def detect(self, frame: np.ndarray) -> List[PersonDetection]:
        """
        Runs YOLO detection on a single frame and filters for person class.

        Args:
            frame: Input image as numpy array (BGR format).

        Returns:
            List of PersonDetection instances.
        """
        if self.model is None:
            raise RuntimeError("YOLO model is not initialized.")

        if frame is None or not isinstance(frame, np.ndarray) or frame.size == 0:
            return []

        # Run inference filtering only class 0 ('person')
        results = self.model.predict(
            source=frame,
            classes=[PERSON_CLASS_ID],
            conf=self.conf_threshold,
            iou=self.iou_threshold,
            verbose=False,
        )

        detections: List[PersonDetection] = []
        if not results or len(results) == 0:
            return detections

        boxes = results[0].boxes
        if boxes is None or len(boxes) == 0:
            return detections

        for box in boxes:
            cls_id = int(box.cls[0].item()) if box.cls is not None else -1
            if cls_id != PERSON_CLASS_ID:
                continue

            conf = float(box.conf[0].item()) if box.conf is not None else 0.0
            xyxy = box.xyxy[0].cpu().numpy().astype(int)

            detection = PersonDetection(
                box=(int(xyxy[0]), int(xyxy[1]), int(xyxy[2]), int(xyxy[3])),
                confidence=conf,
                class_id=PERSON_CLASS_ID,
                class_name="person",
            )
            detections.append(detection)

        return detections

    def draw_detections(
        self,
        frame: np.ndarray,
        detections: List[PersonDetection],
        box_color: Tuple[int, int, int] = (0, 255, 0),
        text_color: Tuple[int, int, int] = (0, 0, 0),
    ) -> np.ndarray:
        """
        Draws bounding boxes, confidence badges, and passenger count on the frame.
        """
        annotated = frame.copy()

        for det in detections:
            x1, y1, x2, y2 = det.box

            # Draw bounding box
            cv2.rectangle(annotated, (x1, y1), (x2, y2), box_color, 2)

            # Draw center point
            cv2.circle(annotated, det.center, 3, (0, 0, 255), -1)

            # Draw label badge
            label = f"person {det.confidence:.2f}"
            (tw, th), baseline = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
            badge_y1 = max(0, y1 - th - baseline - 4)
            badge_y2 = y1
            cv2.rectangle(annotated, (x1, badge_y1), (x1 + tw + 6, badge_y2), box_color, -1)
            cv2.putText(
                annotated,
                label,
                (x1 + 3, y1 - 4),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                text_color,
                1,
                cv2.LINE_AA,
            )

        # Header badge showing current detection count
        h, w = annotated.shape[:2]
        header_h = 32
        cv2.rectangle(annotated, (0, 0), (w, header_h), (25, 25, 25), -1)
        count_text = f"People Detected in Frame: {len(detections)}"
        cv2.putText(
            annotated,
            count_text,
            (12, 22),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 255, 0) if detections else (200, 200, 200),
            2,
            cv2.LINE_AA,
        )

        return annotated


def self_test_yolo_detector():
    """Unit test for YOLOPersonDetector."""
    print("=" * 60)
    print("  [TEST] YOLOPersonDetector Self-Test")
    print("=" * 60)

    # 1. Model Loading
    print("1. Testing model initialization...")
    detector = YOLOPersonDetector(model_path=DEFAULT_MODEL_PATH)
    assert detector.model is not None, "Failed to load model"
    print("   [PASS] YOLOv8n initialized successfully.")

    # 2. Synthetic Frame Inference
    print("2. Testing inference on blank synthetic frame (640x480)...")
    blank_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    dets = detector.detect(blank_frame)
    assert isinstance(dets, list), "Output should be a list"
    assert len(dets) == 0, "Blank frame should yield 0 detections"
    print("   [PASS] Blank frame handled safely with 0 detections.")

    # 3. Annotation on Synthetic Frame
    print("3. Testing annotation function with mock detection...")
    mock_det = PersonDetection(box=(100, 100, 200, 300), confidence=0.88)
    annotated = detector.draw_detections(blank_frame, [mock_det])
    assert annotated.shape == blank_frame.shape, "Annotated frame shape mismatch"
    print("   [PASS] Frame annotation generated successfully.")

    print("\n   [OK] YOLOPersonDetector passed all tests!")


if __name__ == "__main__":
    self_test_yolo_detector()

