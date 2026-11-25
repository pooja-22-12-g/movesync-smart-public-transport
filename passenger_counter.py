"""
passenger_counter.py
====================
Module 4 — Passenger Counting using YOLO and ByteTrack
Smart Public Transport Occupancy and Fleet Monitoring System
------------------------------------------------------------
PURPOSE:
  - Detect people in video frames using pretrained YOLO (COCO class 0: person).
  - Track passenger movements across frames using ByteTrack.
  - Count directional entry/exit crossing events across a configurable virtual line.
  - Compute updated bus occupancy safely:
        Updated Occupancy = Previous Occupancy + Boarding - Alighting
  - Validate capacity limits and guard against negative occupancy.
  - Store video session counts separately from historical CSV dataset.
  - Provide modular extension slots for future custom YOLO models (`models/weights/best.pt`)
    and automated camera/edge feeds.

NOTE:
  - This module uses pretrained YOLO person detection and ByteTrack multi-object tracking.
  - Custom training on bus-passenger datasets has NOT been performed yet.
  - Video sessions are recorded locally in `data/cv_sessions/` to keep historical data untouched.
"""

from __future__ import annotations

import os
import json
import math
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import List, Dict, Tuple, Optional, Any

import cv2
import numpy as np
import pandas as pd
from ultralytics import YOLO

# ──────────────────────────────────────────────────────────────────────────────
# CONSTANTS & CONFIGURATION
# ──────────────────────────────────────────────────────────────────────────────

DEFAULT_PRETRAINED_MODEL = "yolov8n.pt"
CUSTOM_MODEL_PATH = os.path.join("models", "weights", "best.pt")
SESSIONS_DIR = os.path.join("data", "cv_sessions")

PERSON_CLASS_ID = 0  # COCO class index for 'person'

# Counting line directions:
# 'vertical': line is vertical (x = constant), boarding is left->right or right->left
# 'horizontal': line is horizontal (y = constant), boarding is top->bottom or bottom->top
LINE_ORIENTATION_HORIZONTAL = "horizontal"
LINE_ORIENTATION_VERTICAL = "vertical"


# ──────────────────────────────────────────────────────────────────────────────
# DATA STRUCTURES
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class Detection:
    """Represents a single detected person in a frame."""
    box: Tuple[int, int, int, int]  # (x1, y1, x2, y2)
    confidence: float
    track_id: Optional[int] = None
    center: Tuple[int, int] = (0, 0)

    def __post_init__(self):
        x1, y1, x2, y2 = self.box
        self.center = (int((x1 + x2) / 2), int((y1 + y2) / 2))


@dataclass
class CountingLine:
    """
    Virtual counting line across the frame.
    For horizontal: y = position_pct * frame_height.
      If direction == 'top_to_bottom', moving downward is BOARDING, upward is ALIGHTING.
      If direction == 'bottom_to_top', moving upward is BOARDING, downward is ALIGHTING.
    For vertical: x = position_pct * frame_width.
      If direction == 'left_to_right', moving rightward is BOARDING, leftward is ALIGHTING.
      If direction == 'right_to_left', moving leftward is BOARDING, rightward is ALIGHTING.
    """
    orientation: str = LINE_ORIENTATION_HORIZONTAL
    position_pct: float = 0.50  # fraction of frame (0.1 to 0.9)
    direction: str = "top_to_bottom"  # 'top_to_bottom', 'bottom_to_top', 'left_to_right', 'right_to_left'


@dataclass
class VideoSessionResult:
    """Stores the aggregated results of a video processing session."""
    session_id: str
    bus_id: str
    route_id: str
    model_name: str
    timestamp: str
    video_source: str
    total_frames: int
    fps: float
    previous_occupancy: int
    bus_capacity: int
    boarding_count: int
    alighting_count: int
    net_change: int
    updated_occupancy: int
    exceeds_capacity: bool
    unique_tracks_seen: int
    events: List[Dict[str, Any]] = field(default_factory=list)


# ──────────────────────────────────────────────────────────────────────────────
# MODEL MANAGER
# ──────────────────────────────────────────────────────────────────────────────

def get_available_models() -> Dict[str, str]:
    """
    Returns a dictionary of available models:
    e.g. {'Pretrained YOLOv8n (COCO person)': 'yolov8n.pt', ...}
    Checks whether a custom trained model exists at models/weights/best.pt.
    """
    models = {
        "Pretrained YOLOv8n (Standard COCO)": DEFAULT_PRETRAINED_MODEL,
        "Pretrained YOLOv8s (Standard COCO)": "yolov8s.pt",
    }
    if os.path.exists(CUSTOM_MODEL_PATH):
        models["Custom Bus Model (models/weights/best.pt)"] = CUSTOM_MODEL_PATH
    return models


def load_yolo_model(model_path: str = DEFAULT_PRETRAINED_MODEL) -> YOLO:
    """
    Loads YOLO model from path. If pretrained model is requested and not found locally,
    Ultralytics handles the download automatically.
    """
    return YOLO(model_path)


# ──────────────────────────────────────────────────────────────────────────────
# BYTE-TRACK PASSENGER COUNTER
# ──────────────────────────────────────────────────────────────────────────────

class PassengerCounter:
    """
    Tracks passengers and counts directional line-crossings.
    Maintains track history, avoids duplicate counts per tracking ID,
    and supports horizontal or vertical virtual counting gates.
    """

    def __init__(
        self,
        counting_line: Optional[CountingLine] = None,
        min_confidence: float = 0.35,
        buffer_zone_px: int = 20,
    ):
        self.line = counting_line or CountingLine()
        self.min_confidence = min_confidence
        self.buffer_zone_px = buffer_zone_px

        # Tracking state
        # track_id -> list of centers [(x, y), ...]
        self.track_history: Dict[int, List[Tuple[int, int]]] = {}
        # track_id -> crossed state ('BOARDING' or 'ALIGHTING' or None)
        self.counted_tracks: Dict[int, str] = {}
        # Set of all unique track IDs encountered
        self.all_track_ids: set[int] = set()

        # Cumulative totals
        self.boarding_count: int = 0
        self.alighting_count: int = 0
        self.events: List[Dict[str, Any]] = []

    def reset(self):
        """Reset all tracking and counting counters."""
        self.track_history.clear()
        self.counted_tracks.clear()
        self.all_track_ids.clear()
        self.boarding_count = 0
        self.alighting_count = 0
        self.events.clear()

    def get_line_coords(self, width: int, height: int) -> Tuple[Tuple[int, int], Tuple[int, int]]:
        """Calculates start and end coordinates of the virtual counting line."""
        if self.line.orientation == LINE_ORIENTATION_HORIZONTAL:
            y = int(height * self.line.position_pct)
            return ((0, y), (width, y))
        else:
            x = int(width * self.line.position_pct)
            return ((x, 0), (x, height))

    def process_detections(
        self,
        results,
        frame_width: int,
        frame_height: int,
        frame_idx: int = 0,
        timestamp_sec: float = 0.0,
    ) -> List[Detection]:
        """
        Parses YOLO/ByteTrack results, updates movement history, checks line crossing,
        and returns current active detections.
        """
        active_detections: List[Detection] = []
        if not results or len(results) == 0:
            return active_detections

        r = results[0]
        boxes = r.boxes
        if boxes is None or len(boxes) == 0:
            return active_detections

        # Line coordinates
        (x_start, y_start), (x_end, y_end) = self.get_line_coords(frame_width, frame_height)
        line_val = y_start if self.line.orientation == LINE_ORIENTATION_HORIZONTAL else x_start

        for box in boxes:
            cls_id = int(box.cls[0].item()) if box.cls is not None else -1
            if cls_id != PERSON_CLASS_ID:
                continue

            conf = float(box.conf[0].item()) if box.conf is not None else 0.0
            if conf < self.min_confidence:
                continue

            xyxy = box.xyxy[0].cpu().numpy().astype(int)
            track_id = int(box.id[0].item()) if (box.id is not None) else None

            det = Detection(
                box=(int(xyxy[0]), int(xyxy[1]), int(xyxy[2]), int(xyxy[3])),
                confidence=conf,
                track_id=track_id,
            )
            active_detections.append(det)

            if track_id is not None:
                self.all_track_ids.add(track_id)
                cx, cy = det.center

                if track_id not in self.track_history:
                    self.track_history[track_id] = []
                self.track_history[track_id].append((cx, cy))

                # Keep only recent trajectory (last 30 points)
                if len(self.track_history[track_id]) > 30:
                    self.track_history[track_id].pop(0)

                # Check for line crossing if not already counted for this pass
                if track_id not in self.counted_tracks and len(self.track_history[track_id]) >= 2:
                    self._check_line_crossing(
                        track_id=track_id,
                        line_val=line_val,
                        frame_idx=frame_idx,
                        timestamp_sec=timestamp_sec,
                    )

        return active_detections

    def _check_line_crossing(
        self,
        track_id: int,
        line_val: int,
        frame_idx: int,
        timestamp_sec: float,
    ):
        """
        Determines if a tracked trajectory crossed the line and records directional event.
        """
        # If already counted for an active trajectory crossing, prevent duplicate count
        if track_id in self.counted_tracks:
            return

        traj = self.track_history[track_id]
        if len(traj) < 2:
            return

        prev_pt = traj[-2]
        curr_pt = traj[-1]

        event_type = None

        if self.line.orientation == LINE_ORIENTATION_HORIZONTAL:
            prev_pos = prev_pt[1]
            curr_pos = curr_pt[1]

            # Crossing top to bottom (prev_pos < line_val <= curr_pos)
            if prev_pos < line_val and curr_pos >= line_val:
                event_type = "BOARDING" if self.line.direction == "top_to_bottom" else "ALIGHTING"
            # Crossing bottom to top (prev_pos > line_val >= curr_pos)
            elif prev_pos > line_val and curr_pos <= line_val:
                event_type = "ALIGHTING" if self.line.direction == "top_to_bottom" else "BOARDING"

        else:  # VERTICAL LINE
            prev_pos = prev_pt[0]
            curr_pos = curr_pt[0]

            # Crossing left to right (prev_pos < line_val <= curr_pos)
            if prev_pos < line_val and curr_pos >= line_val:
                event_type = "BOARDING" if self.line.direction == "left_to_right" else "ALIGHTING"
            # Crossing right to left (prev_pos > line_val >= curr_pos)
            elif prev_pos > line_val and curr_pos <= line_val:
                event_type = "ALIGHTING" if self.line.direction == "left_to_right" else "BOARDING"

        if event_type == "BOARDING":
            self.boarding_count += 1
            self.counted_tracks[track_id] = "BOARDING"
            self.events.append({
                "frame": frame_idx,
                "timestamp_sec": round(timestamp_sec, 2),
                "track_id": track_id,
                "event": "BOARDING",
                "net_change": +1,
            })
        elif event_type == "ALIGHTING":
            self.alighting_count += 1
            self.counted_tracks[track_id] = "ALIGHTING"
            self.events.append({
                "frame": frame_idx,
                "timestamp_sec": round(timestamp_sec, 2),
                "track_id": track_id,
                "event": "ALIGHTING",
                "net_change": -1,
            })

    def annotate_frame(
        self,
        frame: np.ndarray,
        detections: List[Detection],
        show_trajectories: bool = True,
    ) -> np.ndarray:
        """
        Draws bounding boxes, IDs, trajectories, and the virtual counting gate on the frame.
        """
        annotated = frame.copy()
        h, w = frame.shape[:2]

        # Draw counting line
        (x_start, y_start), (x_end, y_end) = self.get_line_coords(w, h)
        cv2.line(annotated, (x_start, y_start), (x_end, y_end), (0, 165, 255), 3)  # Bright Orange line

        # Line label
        label_text = f"Virtual Gate ({self.line.direction.replace('_', ' ').title()})"
        cv2.putText(
            annotated,
            label_text,
            (x_start + 10, y_start - 10 if y_start > 20 else y_start + 20),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (0, 165, 255),
            2,
            cv2.LINE_AA,
        )

        # Draw detections
        for det in detections:
            x1, y1, x2, y2 = det.box
            color = (0, 255, 0)  # Green for tracked person
            if det.track_id in self.counted_tracks:
                action = self.counted_tracks[det.track_id]
                color = (0, 200, 255) if action == "BOARDING" else (255, 100, 100)

            # Bounding box
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)

            # Center point
            cv2.circle(annotated, det.center, 4, (0, 0, 255), -1)

            # ID and confidence label
            id_str = f"ID:{det.track_id}" if det.track_id is not None else "Det"
            label = f"{id_str} {det.confidence:.2f}"
            cv2.rectangle(annotated, (x1, max(0, y1 - 22)), (x1 + 110, max(0, y1)), color, -1)
            cv2.putText(
                annotated,
                label,
                (x1 + 4, max(14, y1 - 5)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                (0, 0, 0),
                1,
                cv2.LINE_AA,
            )

            # Trajectory tail
            if show_trajectories and det.track_id and det.track_id in self.track_history:
                pts = self.track_history[det.track_id]
                for i in range(1, len(pts)):
                    cv2.line(annotated, pts[i - 1], pts[i], color, 2)

        # Overlay summary statistics header bar
        header_h = 40
        cv2.rectangle(annotated, (0, 0), (w, header_h), (30, 30, 30), -1)
        stats_str = (
            f"Frame: {len(detections)} pax  |  "
            f"Boarded: +{self.boarding_count}  |  "
            f"Alighted: -{self.alighting_count}  |  "
            f"Net: {self.boarding_count - self.alighting_count:+d}"
        )
        cv2.putText(
            annotated,
            stats_str,
            (15, 26),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )

        return annotated


# ──────────────────────────────────────────────────────────────────────────────
# OCCUPANCY CALCULATION & VALIDATION
# ──────────────────────────────────────────────────────────────────────────────

def calculate_updated_occupancy(
    previous_occupancy: int,
    boarding: int,
    alighting: int,
    bus_capacity: int = 60,
) -> Dict[str, Any]:
    """
    Computes updated occupancy using the official formula:
        Updated Occupancy = Previous Occupancy + Boarding - Alighting

    Validates:
      - Raw formula value
      - Clamped valid value (>= 0)
      - Capacity overflow detection (exceeds bus_capacity)
      - Occupancy percentage
    """
    if previous_occupancy < 0:
        raise ValueError("previous_occupancy cannot be negative.")
    if boarding < 0 or alighting < 0:
        raise ValueError("boarding and alighting must be non-negative integers.")
    if bus_capacity <= 0:
        raise ValueError("bus_capacity must be greater than zero.")

    raw_occupancy = previous_occupancy + boarding - alighting
    clamped_occupancy = max(0, raw_occupancy)
    exceeds_capacity = raw_occupancy > bus_capacity
    underflow_detected = raw_occupancy < 0

    occ_pct = round((clamped_occupancy / bus_capacity) * 100.0, 1)

    return {
        "previous_occupancy": previous_occupancy,
        "boarding": boarding,
        "alighting": alighting,
        "net_change": boarding - alighting,
        "raw_occupancy": raw_occupancy,
        "updated_occupancy": clamped_occupancy,
        "bus_capacity": bus_capacity,
        "occupancy_pct": occ_pct,
        "exceeds_capacity": exceeds_capacity,
        "underflow_detected": underflow_detected,
    }


# ──────────────────────────────────────────────────────────────────────────────
# SESSION PERSISTENCE (SEPARATE FROM HISTORICAL CSV)
# ──────────────────────────────────────────────────────────────────────────────

def save_session_result(session_result: VideoSessionResult) -> str:
    """
    Saves video session count results to a JSON file in data/cv_sessions/
    to guarantee the original data/bus_occupancy.csv remains completely untouched.
    """
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    filename = f"session_{session_result.session_id}.json"
    filepath = os.path.join(SESSIONS_DIR, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(asdict(session_result), f, indent=2)

    return filepath


def load_all_session_results() -> List[Dict[str, Any]]:
    """Loads all saved video counting sessions from data/cv_sessions/."""
    if not os.path.exists(SESSIONS_DIR):
        return []

    sessions = []
    for fname in sorted(os.listdir(SESSIONS_DIR), reverse=True):
        if fname.endswith(".json"):
            try:
                with open(os.path.join(SESSIONS_DIR, fname), "r", encoding="utf-8") as f:
                    sessions.append(json.load(f))
            except Exception:
                continue
    return sessions


# ──────────────────────────────────────────────────────────────────────────────
# SELF-TEST SUITE
# ──────────────────────────────────────────────────────────────────────────────

def run_self_tests() -> bool:
    """Runs verification checks for Module 4."""
    print("=" * 64)
    print("  Module 4: Passenger Counting — Self-Test Suite")
    print("  YOLO Person Detection + ByteTrack Movement Counter")
    print("=" * 64)

    total = 0
    passed = 0

    def check(desc: str, cond: bool, note: str = ""):
        nonlocal total, passed
        total += 1
        if cond:
            passed += 1
            print(f"  [PASS] {desc}" + (f"  ({note})" if note else ""))
        else:
            print(f"  [FAIL] {desc}" + (f"  ({note})" if note else ""))

    # Test 1: Occupancy formula validation
    print("\n[TEST 1] Occupancy Calculation Logic")
    res1 = calculate_updated_occupancy(20, 5, 2, 60)
    check("Normal boarding & alighting (20 + 5 - 2 = 23)", res1["updated_occupancy"] == 23)
    check("Occupancy percentage calculation (23/60 = 38.3%)", res1["occupancy_pct"] == 38.3)
    check("Not exceeding capacity", not res1["exceeds_capacity"])

    # Overcrowded condition
    res2 = calculate_updated_occupancy(55, 10, 0, 60)
    check("Overcrowding detection (55 + 10 = 65 > 60)", res2["exceeds_capacity"] and res2["raw_occupancy"] == 65)

    # Underflow clamping guard
    res3 = calculate_updated_occupancy(2, 0, 5, 60)
    check("Underflow guard clamps occupancy to 0", res3["updated_occupancy"] == 0 and res3["underflow_detected"])

    # Test 2: Counting line and crossing logic
    print("\n[TEST 2] Virtual Line Crossing Logic (ByteTrack Trajectory)")
    counter = PassengerCounter(CountingLine(orientation=LINE_ORIENTATION_HORIZONTAL, position_pct=0.5, direction="top_to_bottom"))
    line_y = 240  # 480 * 0.5

    # Simulate Person 1 crossing downwards (Boarding)
    counter.track_history[1] = [(300, 200), (300, 260)]
    counter._check_line_crossing(track_id=1, line_val=line_y, frame_idx=10, timestamp_sec=0.5)
    check("Downwards crossing registered as BOARDING", counter.boarding_count == 1 and counter.alighting_count == 0)
    check("Track 1 marked as counted", counter.counted_tracks.get(1) == "BOARDING")

    # Simulate duplicate check for same track
    counter._check_line_crossing(track_id=1, line_val=line_y, frame_idx=11, timestamp_sec=0.6)
    check("No duplicate count for same track ID", counter.boarding_count == 1)

    # Simulate Person 2 crossing upwards (Alighting)
    counter.track_history[2] = [(350, 270), (350, 210)]
    counter._check_line_crossing(track_id=2, line_val=line_y, frame_idx=15, timestamp_sec=0.8)
    check("Upwards crossing registered as ALIGHTING", counter.alighting_count == 1)
    check("Net change equals 0 (+1 boarding - 1 alighting)", (counter.boarding_count - counter.alighting_count) == 0)

    # Test 3: Session Persistence
    print("\n[TEST 3] Session Persistence (Historical CSV untouched)")
    sess = VideoSessionResult(
        session_id="test_sess_001",
        bus_id="KA-BUS-001",
        route_id="R205",
        model_name="yolov8n.pt",
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        video_source="test_synthetic_stream",
        total_frames=100,
        fps=30.0,
        previous_occupancy=25,
        bus_capacity=60,
        boarding_count=4,
        alighting_count=2,
        net_change=2,
        updated_occupancy=27,
        exceeds_capacity=False,
        unique_tracks_seen=6,
    )
    saved_path = save_session_result(sess)
    check("Session saved to data/cv_sessions/", os.path.exists(saved_path))
    loaded = load_all_session_results()
    check("Loaded session matches saved data", any(s["session_id"] == "test_sess_001" for s in loaded))

    # Clean up test session file
    if os.path.exists(saved_path):
        os.remove(saved_path)

    # Test 4: Model loading & inference check
    print("\n[TEST 4] Pretrained YOLO and ByteTrack Inference")
    try:
        model = load_yolo_model(DEFAULT_PRETRAINED_MODEL)
        check("YOLO model loaded successfully", model is not None)
        dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        # Test YOLO detection & tracker invocation
        results = model.track(
            dummy_frame,
            classes=[PERSON_CLASS_ID],
            tracker="bytetrack.yaml",
            persist=True,
            verbose=False,
        )
        check("YOLO + ByteTrack executed without runtime errors", results is not None)
    except Exception as e:
        check("Model inference test", False, str(e))

    print("\n" + "=" * 64)
    print(f"  RESULTS: {passed}/{total} passed, {total - passed} failed")
    if passed == total:
        print("  ✅ ALL MODULE 4 SELF-TESTS PASSED")
    else:
        print("  ❌ SOME TESTS FAILED")
    print("=" * 64)

    return passed == total


if __name__ == "__main__":
    run_self_tests()
