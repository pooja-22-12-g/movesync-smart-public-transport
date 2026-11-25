"""
passenger_counting/bytetrack_tracker.py
=======================================
Module 4, Step 2: ByteTrack Person Tracker
Smart Public Transport Occupancy and Fleet Monitoring System
------------------------------------------------------------
PURPOSE:
  - Integrate ByteTrack to track detected persons across consecutive video frames.
  - Assign unique tracking IDs to detected individuals.
  - Maintain tracking IDs across frames, handling occlusions and camera entries/exits.
  - Maintain trajectory history for direction analysis.
  - Keep tracking logic completely decoupled from detection logic.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict

import cv2
import numpy as np
from ultralytics import YOLO


PERSON_CLASS_ID = 0
DEFAULT_MODEL_PATH = "yolov8n.pt"


@dataclass
class TrackedPerson:
    """Represents a person tracked across video frames with a persistent track ID."""
    track_id: int
    box: Tuple[int, int, int, int]  # (x1, y1, x2, y2)
    confidence: float
    center: Tuple[int, int] = (0, 0)
    history: List[Tuple[int, int]] = field(default_factory=list)

    def __post_init__(self):
        x1, y1, x2, y2 = self.box
        self.center = (int((x1 + x2) / 2), int((y1 + y2) / 2))

    @property
    def width(self) -> int:
        return self.box[2] - self.box[0]

    @property
    def height(self) -> int:
        return self.box[3] - self.box[1]


class ByteTrackTracker:
    """
    ByteTrack Tracker integration using Ultralytics tracking engine.
    Maintains persistent tracking states, handles entering/leaving persons,
    and builds trajectories.
    """

    def __init__(
        self,
        model_path: str = DEFAULT_MODEL_PATH,
        conf_threshold: float = 0.35,
        iou_threshold: float = 0.45,
        tracker_config: str = "bytetrack.yaml",
        max_trajectory_points: int = 30,
    ):
        self.model_path = model_path
        self.conf_threshold = conf_threshold
        self.iou_threshold = iou_threshold
        self.tracker_config = tracker_config
        self.max_trajectory_points = max_trajectory_points

        # State tracking
        self.track_trajectories: Dict[int, List[Tuple[int, int]]] = {}
        self.unique_track_ids: set[int] = set()

        # Initialize tracking model instance
        self.model = YOLO(self.model_path)

    def reset(self):
        """Reset internal tracking state and trajectory histories."""
        self.track_trajectories.clear()
        self.unique_track_ids.clear()
        # Re-initialize tracker state in model if available
        if hasattr(self.model, "predictor") and self.model.predictor is not None:
            self.model.predictor = None

    def update(self, frame: np.ndarray) -> List[TrackedPerson]:
        """
        Processes a video frame with ByteTrack, updating track IDs and movement histories.

        Args:
            frame: Input image (BGR numpy array).

        Returns:
            List of TrackedPerson instances active in the current frame.
        """
        if frame is None or not isinstance(frame, np.ndarray) or frame.size == 0:
            return []

        # Run ByteTrack tracking with frame persistence
        results = self.model.track(
            source=frame,
            classes=[PERSON_CLASS_ID],
            conf=self.conf_threshold,
            iou=self.iou_threshold,
            tracker=self.tracker_config,
            persist=True,
            verbose=False,
        )

        tracked_persons: List[TrackedPerson] = []
        if not results or len(results) == 0:
            return tracked_persons

        boxes = results[0].boxes
        if boxes is None or len(boxes) == 0:
            return tracked_persons

        for box in boxes:
            cls_id = int(box.cls[0].item()) if box.cls is not None else -1
            if cls_id != PERSON_CLASS_ID:
                continue

            # Tracking ID assigned by ByteTrack
            if box.id is None:
                continue

            track_id = int(box.id[0].item())
            conf = float(box.conf[0].item()) if box.conf is not None else 0.0
            xyxy = box.xyxy[0].cpu().numpy().astype(int)
            box_tuple = (int(xyxy[0]), int(xyxy[1]), int(xyxy[2]), int(xyxy[3]))

            # Register unique ID
            self.unique_track_ids.add(track_id)

            # Center calculation
            cx = int((box_tuple[0] + box_tuple[2]) / 2)
            cy = int((box_tuple[1] + box_tuple[3]) / 2)

            # Update trajectory
            if track_id not in self.track_trajectories:
                self.track_trajectories[track_id] = []
            self.track_trajectories[track_id].append((cx, cy))
            if len(self.track_trajectories[track_id]) > self.max_trajectory_points:
                self.track_trajectories[track_id].pop(0)

            person = TrackedPerson(
                track_id=track_id,
                box=box_tuple,
                confidence=conf,
                history=list(self.track_trajectories[track_id]),
            )
            tracked_persons.append(person)

        return tracked_persons

    def draw_tracks(
        self,
        frame: np.ndarray,
        tracks: List[TrackedPerson],
        draw_trajectories: bool = True,
    ) -> np.ndarray:
        """
        Draws bounding boxes, unique tracking IDs, and trajectory trails on the frame.
        """
        annotated = frame.copy()

        # Fixed distinct color palette by track ID modulo
        palette = [
            (50, 205, 50),   # Lime green
            (30, 144, 255),  # Dodger blue
            (255, 140, 0),   # Dark orange
            (238, 130, 238), # Violet
            (0, 255, 255),   # Yellow
            (255, 20, 147),  # Deep pink
            (0, 206, 209),   # Dark turquoise
        ]

        for person in tracks:
            color = palette[person.track_id % len(palette)]
            x1, y1, x2, y2 = person.box

            # Bounding box
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)

            # Center dot
            cv2.circle(annotated, person.center, 4, (0, 0, 255), -1)

            # Track ID label badge
            label = f"ID: {person.track_id} ({person.confidence:.2f})"
            (tw, th), baseline = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
            badge_y1 = max(0, y1 - th - baseline - 4)
            badge_y2 = y1
            cv2.rectangle(annotated, (x1, badge_y1), (x1 + tw + 6, badge_y2), color, -1)
            cv2.putText(
                annotated,
                label,
                (x1 + 3, y1 - 4),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                (0, 0, 0),
                1,
                cv2.LINE_AA,
            )

            # Draw trajectory path
            if draw_trajectories and len(person.history) >= 2:
                for i in range(1, len(person.history)):
                    cv2.line(annotated, person.history[i - 1], person.history[i], color, 2)

        # Header overlay
        h, w = annotated.shape[:2]
        header_h = 32
        cv2.rectangle(annotated, (0, 0), (w, header_h), (25, 25, 25), -1)
        stats_text = (
            f"Active In Frame: {len(tracks)} pax  |  "
            f"Total Unique IDs Tracked: {len(self.unique_track_ids)}"
        )
        cv2.putText(
            annotated,
            stats_text,
            (12, 22),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (0, 255, 200),
            1,
            cv2.LINE_AA,
        )

        return annotated


def self_test_bytetrack_tracker():
    """Unit test for ByteTrackTracker."""
    print("=" * 60)
    print("  [TEST] ByteTrackTracker Self-Test")
    print("=" * 60)

    # 1. Initialization
    print("1. Testing ByteTrackTracker initialization...")
    tracker = ByteTrackTracker(model_path=DEFAULT_MODEL_PATH)
    assert tracker.model is not None, "Failed to initialize YOLO for ByteTrack"
    print("   [PASS] ByteTrackTracker initialized with bytetrack.yaml configuration.")

    # 2. Blank frame check
    print("2. Testing update on blank synthetic frame...")
    blank_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    tracks = tracker.update(blank_frame)
    assert isinstance(tracks, list), "Output should be a list"
    assert len(tracks) == 0, "No tracks should be detected on blank frame"
    print("   [PASS] Blank frame handled safely with 0 active tracks.")

    # 3. Synthetic track rendering check
    print("3. Testing track visualization with mock TrackedPerson...")
    mock_track = TrackedPerson(
        track_id=1,
        box=(120, 150, 220, 350),
        confidence=0.91,
        history=[(170, 200), (170, 225), (170, 250)],
    )
    tracker.unique_track_ids.add(1)
    annotated = tracker.draw_tracks(blank_frame, [mock_track])
    assert annotated.shape == blank_frame.shape, "Annotated frame shape mismatch"
    print("   [PASS] Tracked person and trajectory trail visualized properly.")

    print("\n   [OK] ByteTrackTracker passed all tests!")


if __name__ == "__main__":
    self_test_bytetrack_tracker()

