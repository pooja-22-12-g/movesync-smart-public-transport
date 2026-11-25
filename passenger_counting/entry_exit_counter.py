"""
passenger_counting/entry_exit_counter.py
========================================
Module 4, Step 3: Boarding and Alighting Detection via Virtual Line Crossing
Smart Public Transport Occupancy and Fleet Monitoring System
----------------------------------------------------------------------------
PURPOSE:
  - Define a configurable virtual counting line across a video frame.
  - Track previous and current center coordinates of each tracked person (by track_id).
  - Detect directional crossing of the virtual boundary:
      * Boarding: moving in the configured entry direction (e.g. top->bottom or left->right).
      * Alighting: moving in the reverse exit direction (e.g. bottom->top or right->left).
  - Prevent duplicate counts for the same person/track ID during a crossing event.
  - Maintain separate totals for boarding and alighting.
  - Calculate net passenger change: Net = Boarding - Alighting.
  - Handle track loss, re-entry, and unassigned tracks safely.
  - Provide frame annotation overlay showing counting line, active tracks, and statistics.
  - Completely independent of YOLO and ByteTrack implementations (receives clean coordinates/IDs).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Tuple, Optional, Any

import cv2
import numpy as np


class LineOrientation(str, Enum):
    HORIZONTAL = "horizontal"
    VERTICAL = "vertical"


class DirectionConfig(str, Enum):
    # For HORIZONTAL lines (y = constant):
    TOP_TO_BOTTOM_IS_BOARDING = "top_to_bottom"  # downward = boarding, upward = alighting
    BOTTOM_TO_TOP_IS_BOARDING = "bottom_to_top"  # upward = boarding, downward = alighting

    # For VERTICAL lines (x = constant):
    LEFT_TO_RIGHT_IS_BOARDING = "left_to_right"  # rightward = boarding, leftward = alighting
    RIGHT_TO_LEFT_IS_BOARDING = "right_to_left"  # leftward = boarding, rightward = alighting


class CrossingEvent(str, Enum):
    BOARDING = "BOARDING"
    ALIGHTING = "ALIGHTING"


@dataclass
class VirtualLine:
    """
    Configuration for a virtual counting line across the frame.

    orientation: 'horizontal' (divides top/bottom) or 'vertical' (divides left/right).
    position_pct: normalized position on axis (0.1 to 0.9).
                  0.5 means center of the frame.
    direction_config: which crossing direction corresponds to boarding.
    buffer_zone_px: optional hysteresis dead-zone around the line to prevent jitter toggling.
    """
    orientation: LineOrientation = LineOrientation.HORIZONTAL
    position_pct: float = 0.50
    direction_config: DirectionConfig = DirectionConfig.TOP_TO_BOTTOM_IS_BOARDING
    buffer_zone_px: int = 5

    def get_endpoints(self, width: int, height: int) -> Tuple[Tuple[int, int], Tuple[int, int]]:
        """Calculates (start_point, end_point) of the line in pixels."""
        if self.orientation == LineOrientation.HORIZONTAL:
            y = int(height * self.position_pct)
            return ((0, y), (width, y))
        else:
            x = int(width * self.position_pct)
            return ((x, 0), (x, height))

    def get_line_coordinate(self, width: int, height: int) -> int:
        """Returns the scalar coordinate (y for horizontal, x for vertical)."""
        if self.orientation == LineOrientation.HORIZONTAL:
            return int(height * self.position_pct)
        else:
            return int(width * self.position_pct)


@dataclass
class TrackCrossingRecord:
    """Stores the crossing state and event history for a single tracking ID."""
    track_id: int
    last_event: Optional[CrossingEvent] = None
    counted_direction: Optional[CrossingEvent] = None
    crossing_frame: Optional[int] = None
    crossing_timestamp: Optional[float] = None


@dataclass
class CountingSummary:
    """Summary of passenger counting statistics."""
    current_frame_detections: int
    unique_tracked_ids: int
    total_boarding: int
    total_alighting: int
    net_change: int
    active_track_ids: List[int] = field(default_factory=list)


class EntryExitCounter:
    """
    Independent boarding and alighting counter based on virtual line crossing.
    Receives tracking coordinates per frame and computes directional crossing events.
    """

    def __init__(self, virtual_line: Optional[VirtualLine] = None):
        self.line = virtual_line or VirtualLine()

        # Cumulative counters
        self.boarding_count: int = 0
        self.alighting_count: int = 0

        # Trajectory history: track_id -> [(x, y), ...]
        self.track_positions: Dict[int, List[Tuple[int, int]]] = {}

        # Tracking crossing records: track_id -> TrackCrossingRecord
        self.records: Dict[int, TrackCrossingRecord] = {}

        # Set of all unique tracking IDs ever observed
        self.all_unique_ids: set[int] = set()

        # Detailed event log
        self.event_log: List[Dict[str, Any]] = []

    def reset(self):
        """Resets all tracking states and counters."""
        self.boarding_count = 0
        self.alighting_count = 0
        self.track_positions.clear()
        self.records.clear()
        self.all_unique_ids.clear()
        self.event_log.clear()

    @property
    def net_passenger_change(self) -> int:
        """Net change = Boarding - Alighting."""
        return self.boarding_count - self.alighting_count

    def update(
        self,
        current_tracks: List[Dict[str, Any]],
        frame_width: int,
        frame_height: int,
        frame_idx: int = 0,
        timestamp_sec: float = 0.0,
    ) -> CountingSummary:
        """
        Processes tracked persons for the current frame.

        Args:
            current_tracks: List of dicts or objects with:
                            - 'track_id': int
                            - 'center': (cx, cy) or 'box': (x1, y1, x2, y2)
            frame_width: Frame width in pixels.
            frame_height: Frame height in pixels.
            frame_idx: Frame sequence number.
            timestamp_sec: Video timestamp in seconds.

        Returns:
            CountingSummary with updated counts.
        """
        line_val = self.line.get_line_coordinate(frame_width, frame_height)
        active_ids: List[int] = []

        for track in current_tracks:
            # Extract track_id
            track_id = track.get("track_id") if isinstance(track, dict) else getattr(track, "track_id", None)
            if track_id is None:
                # Unassigned or lost track ID — ignore safely
                continue

            # Extract center coordinates
            if isinstance(track, dict):
                if "center" in track:
                    cx, cy = track["center"]
                elif "box" in track:
                    x1, y1, x2, y2 = track["box"]
                    cx, cy = int((x1 + x2) / 2), int((y1 + y2) / 2)
                else:
                    continue
            else:
                if hasattr(track, "center"):
                    cx, cy = track.center
                elif hasattr(track, "box"):
                    x1, y1, x2, y2 = track.box
                    cx, cy = int((x1 + x2) / 2), int((y1 + y2) / 2)
                else:
                    continue

            self.all_unique_ids.add(track_id)
            active_ids.append(track_id)

            if track_id not in self.track_positions:
                self.track_positions[track_id] = []
                self.records[track_id] = TrackCrossingRecord(track_id=track_id)

            self.track_positions[track_id].append((cx, cy))

            # Maintain sliding window of trajectory (last 30 positions)
            if len(self.track_positions[track_id]) > 30:
                self.track_positions[track_id].pop(0)

            # Check crossing if we have at least 2 consecutive positions
            if len(self.track_positions[track_id]) >= 2:
                prev_pt = self.track_positions[track_id][-2]
                curr_pt = self.track_positions[track_id][-1]
                self._evaluate_crossing(
                    track_id=track_id,
                    prev_pt=prev_pt,
                    curr_pt=curr_pt,
                    line_val=line_val,
                    frame_idx=frame_idx,
                    timestamp_sec=timestamp_sec,
                )

        return CountingSummary(
            current_frame_detections=len(active_ids),
            unique_tracked_ids=len(self.all_unique_ids),
            total_boarding=self.boarding_count,
            total_alighting=self.alighting_count,
            net_change=self.net_passenger_change,
            active_track_ids=active_ids,
        )

    def _evaluate_crossing(
        self,
        track_id: int,
        prev_pt: Tuple[int, int],
        curr_pt: Tuple[int, int],
        line_val: int,
        frame_idx: int,
        timestamp_sec: float,
    ):
        """
        Determines if the step from prev_pt to curr_pt crossed the virtual line.
        Enforces strict duplicate count prevention for the same crossing event.
        """
        record = self.records[track_id]

        # Prevent duplicate count if this track was already counted for this continuous trajectory
        if record.counted_direction is not None:
            return

        buf = self.line.buffer_zone_px

        if self.line.orientation == LineOrientation.HORIZONTAL:
            prev_pos = prev_pt[1]
            curr_pos = curr_pt[1]

            # Downward movement across line
            if prev_pos < (line_val - buf) and curr_pos >= (line_val + buf):
                if self.line.direction_config == DirectionConfig.TOP_TO_BOTTOM_IS_BOARDING:
                    self._record_crossing(track_id, CrossingEvent.BOARDING, frame_idx, timestamp_sec)
                else:
                    self._record_crossing(track_id, CrossingEvent.ALIGHTING, frame_idx, timestamp_sec)

            # Upward movement across line
            elif prev_pos > (line_val + buf) and curr_pos <= (line_val - buf):
                if self.line.direction_config == DirectionConfig.TOP_TO_BOTTOM_IS_BOARDING:
                    self._record_crossing(track_id, CrossingEvent.ALIGHTING, frame_idx, timestamp_sec)
                else:
                    self._record_crossing(track_id, CrossingEvent.BOARDING, frame_idx, timestamp_sec)

        else:  # VERTICAL
            prev_pos = prev_pt[0]
            curr_pos = curr_pt[0]

            # Rightward movement across line
            if prev_pos < (line_val - buf) and curr_pos >= (line_val + buf):
                if self.line.direction_config == DirectionConfig.LEFT_TO_RIGHT_IS_BOARDING:
                    self._record_crossing(track_id, CrossingEvent.BOARDING, frame_idx, timestamp_sec)
                else:
                    self._record_crossing(track_id, CrossingEvent.ALIGHTING, frame_idx, timestamp_sec)

            # Leftward movement across line
            elif prev_pos > (line_val + buf) and curr_pos <= (line_val - buf):
                if self.line.direction_config == DirectionConfig.LEFT_TO_RIGHT_IS_BOARDING:
                    self._record_crossing(track_id, CrossingEvent.ALIGHTING, frame_idx, timestamp_sec)
                else:
                    self._record_crossing(track_id, CrossingEvent.BOARDING, frame_idx, timestamp_sec)

    def _record_crossing(
        self,
        track_id: int,
        event_type: CrossingEvent,
        frame_idx: int,
        timestamp_sec: float,
    ):
        """Records a valid crossing event and increments the appropriate counter."""
        record = self.records[track_id]
        record.counted_direction = event_type
        record.last_event = event_type
        record.crossing_frame = frame_idx
        record.crossing_timestamp = timestamp_sec

        if event_type == CrossingEvent.BOARDING:
            self.boarding_count += 1
            delta = +1
        else:
            self.alighting_count += 1
            delta = -1

        self.event_log.append({
            "track_id": track_id,
            "event": event_type.value,
            "frame": frame_idx,
            "timestamp_sec": round(timestamp_sec, 2),
            "net_after": self.net_passenger_change,
        })

    def draw_overlay(
        self,
        frame: np.ndarray,
        active_tracks: List[Dict[str, Any]],
        show_trajectories: bool = True,
    ) -> np.ndarray:
        """
        Draws the counting line, directional arrows, status headers,
        and track indicators on an OpenCV frame.
        """
        annotated = frame.copy()
        h, w = frame.shape[:2]

        # 1. Draw virtual counting line (Bright Orange: BGR (0, 165, 255))
        (x_start, y_start), (x_end, y_end) = self.line.get_endpoints(w, h)
        cv2.line(annotated, (x_start, y_start), (x_end, y_end), (0, 165, 255), 3)

        # 2. Gate Label & Direction indicator
        dir_label = f"Virtual Gate: {self.line.direction_config.value.replace('_', ' ').title()}"
        cv2.putText(
            annotated,
            dir_label,
            (x_start + 12, max(25, y_start - 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (0, 165, 255),
            2,
            cv2.LINE_AA,
        )

        # 3. Draw trajectories & status per tracked person
        for track in active_tracks:
            track_id = track.get("track_id") if isinstance(track, dict) else getattr(track, "track_id", None)
            if track_id is None:
                continue

            record = self.records.get(track_id)
            color = (50, 205, 50)  # Default lime green
            if record and record.counted_direction == CrossingEvent.BOARDING:
                color = (0, 215, 255)  # Gold for boarded
            elif record and record.counted_direction == CrossingEvent.ALIGHTING:
                color = (255, 100, 100)  # Blue/Red for alighted

            # Draw trajectory path
            if show_trajectories and track_id in self.track_positions:
                pts = self.track_positions[track_id]
                for i in range(1, len(pts)):
                    cv2.line(annotated, pts[i - 1], pts[i], color, 2)

        # 4. Top Statistics Header Dashboard Bar
        header_h = 38
        cv2.rectangle(annotated, (0, 0), (w, header_h), (20, 20, 20), -1)

        summary_text = (
            f"Frame: {len(active_tracks)} pax  |  "
            f"Unique Tracked: {len(self.all_unique_ids)}  |  "
            f"Boarded: +{self.boarding_count}  |  "
            f"Alighted: -{self.alighting_count}  |  "
            f"Net: {self.net_passenger_change:+d}"
        )
        cv2.putText(
            annotated,
            summary_text,
            (14, 25),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.58,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )

        return annotated


# ──────────────────────────────────────────────────────────────────────────────
# SELF-TEST SUITE: SYNTHETIC TRACKING-COORDINATE VERIFICATION
# ──────────────────────────────────────────────────────────────────────────────

def run_self_tests() -> bool:
    """
    Executes controlled synthetic tracking-coordinate test cases covering:
      1. Crossing in boarding direction.
      2. Crossing in alighting direction.
      3. Person who does NOT cross the line.
      4. Person crossing only once (single count).
      5. Duplicate-count prevention for same continuous trajectory.
      6. Multiple people crossing in the same video stream.
      7. Vertical line crossing configuration.
      8. Missing/None tracking ID handling.
    """
    print("=" * 64)
    print("  Module 4, Step 3: EntryExitCounter — Self-Test Suite")
    print("  Controlled Synthetic Tracking-Coordinate Verification")
    print("=" * 64)

    total_checks = 0
    passed_checks = 0

    def check(description: str, condition: bool, note: str = ""):
        nonlocal total_checks, passed_checks
        total_checks += 1
        if condition:
            passed_checks += 1
            print(f"  [PASS] {description}" + (f"  ({note})" if note else ""))
        else:
            print(f"  [FAIL] {description}" + (f"  ({note})" if note else ""))

    # Setup frame dimensions: 640 x 480
    w, h = 640, 480

    # ── TEST 1: Person crossing in Boarding direction ──────────────────────────
    print("\n[TEST 1] Person Crossing in Boarding Direction")
    line = VirtualLine(
        orientation=LineOrientation.HORIZONTAL,
        position_pct=0.5,  # line at y = 240
        direction_config=DirectionConfig.TOP_TO_BOTTOM_IS_BOARDING,
        buffer_zone_px=5,
    )
    counter = EntryExitCounter(line)

    # Frame 1: Person 1 at y = 200 (above line)
    s1 = counter.update([{"track_id": 1, "center": (320, 200)}], w, h, frame_idx=1)
    check("Frame 1: Before crossing, boarding is 0", s1.total_boarding == 0)

    # Frame 2: Person 1 moves to y = 260 (below line)
    s2 = counter.update([{"track_id": 1, "center": (320, 260)}], w, h, frame_idx=2)
    check("Frame 2: Crosses downward -> Boarding count is 1", s2.total_boarding == 1)
    check("Frame 2: Alighting remains 0", s2.total_alighting == 0)
    check("Frame 2: Net change is +1", s2.net_change == 1)

    # ── TEST 2: Person crossing in Alighting direction ─────────────────────────
    print("\n[TEST 2] Person Crossing in Alighting Direction")
    counter.reset()

    # Frame 1: Person 2 at y = 280 (below line)
    counter.update([{"track_id": 2, "center": (320, 280)}], w, h, frame_idx=1)
    # Frame 2: Person 2 moves upward to y = 210 (above line)
    s_alight = counter.update([{"track_id": 2, "center": (320, 210)}], w, h, frame_idx=2)
    check("Upward crossing registered as Alighting count 1", s_alight.total_alighting == 1)
    check("Boarding remains 0", s_alight.total_boarding == 0)
    check("Net change is -1", s_alight.net_change == -1)

    # ── TEST 3: Person who does NOT cross the line ────────────────────────────
    print("\n[TEST 3] Person Who Does Not Cross the Line")
    counter.reset()
    # Moves from y = 100 to y = 180 (never crosses line at y = 240)
    counter.update([{"track_id": 3, "center": (300, 100)}], w, h, frame_idx=1)
    counter.update([{"track_id": 3, "center": (300, 150)}], w, h, frame_idx=2)
    s_no_cross = counter.update([{"track_id": 3, "center": (300, 180)}], w, h, frame_idx=3)
    check("No crossing event -> Boarding is 0", s_no_cross.total_boarding == 0)
    check("No crossing event -> Alighting is 0", s_no_cross.total_alighting == 0)
    check("Track 3 registered in unique tracked IDs", s_no_cross.unique_tracked_ids == 1)

    # ── TEST 4 & 5: Duplicate-Count Prevention (Crossing Only Once) ───────────
    print("\n[TEST 4 & 5] Crossing Only Once & Duplicate-Count Prevention")
    counter.reset()
    # Person 4 crosses from y = 220 to y = 270
    counter.update([{"track_id": 4, "center": (320, 220)}], w, h, frame_idx=1)
    counter.update([{"track_id": 4, "center": (320, 270)}], w, h, frame_idx=2)  # Crossed
    # Continues moving down in frames 3, 4, 5
    counter.update([{"track_id": 4, "center": (320, 310)}], w, h, frame_idx=3)
    counter.update([{"track_id": 4, "center": (320, 350)}], w, h, frame_idx=4)
    s_dup = counter.update([{"track_id": 4, "center": (320, 400)}], w, h, frame_idx=5)
    check("Boarding count remains strictly 1 across consecutive frames", s_dup.total_boarding == 1)
    check("No duplicate event logged in event_log", len(counter.event_log) == 1)

    # ── TEST 6: Multiple People Crossing in the Same Stream ───────────────────
    print("\n[TEST 6] Multiple People Crossing Simultaneously")
    counter.reset()
    # Frame 1: Person 10 above line, Person 20 below line, Person 30 far away
    counter.update([
        {"track_id": 10, "center": (200, 190)},
        {"track_id": 20, "center": (400, 280)},
        {"track_id": 30, "center": (500, 50)},
    ], w, h, frame_idx=1)

    # Frame 2: Person 10 boards (crosses down), Person 20 alights (crosses up), Person 30 stays far
    s_multi = counter.update([
        {"track_id": 10, "center": (200, 270)},
        {"track_id": 20, "center": (400, 200)},
        {"track_id": 30, "center": (500, 80)},
    ], w, h, frame_idx=2)

    check("Simultaneous boarding count is 1", s_multi.total_boarding == 1)
    check("Simultaneous alighting count is 1", s_multi.total_alighting == 1)
    check("Net change equals 0 (+1 - 1 = 0)", s_multi.net_change == 0)
    check("Unique tracked person IDs equals 3", s_multi.unique_tracked_ids == 3)
    check("Current frame detection count equals 3", s_multi.current_frame_detections == 3)

    # ── TEST 7: Vertical Line Crossing Configuration ──────────────────────────
    print("\n[TEST 7] Vertical Virtual Line Configuration (Left-to-Right)")
    v_line = VirtualLine(
        orientation=LineOrientation.VERTICAL,
        position_pct=0.5,  # line at x = 320
        direction_config=DirectionConfig.LEFT_TO_RIGHT_IS_BOARDING,
        buffer_zone_px=5,
    )
    v_counter = EntryExitCounter(v_line)

    # Moves from x = 280 (left) to x = 360 (right) -> Boarding
    v_counter.update([{"track_id": 50, "center": (280, 240)}], w, h, frame_idx=1)
    s_vert = v_counter.update([{"track_id": 50, "center": (360, 240)}], w, h, frame_idx=2)
    check("Vertical line: Left-to-right registered as Boarding 1", s_vert.total_boarding == 1)

    # Moves from x = 370 (right) to x = 270 (left) -> Alighting
    v_counter.update([{"track_id": 60, "center": (370, 240)}], w, h, frame_idx=3)
    s_vert2 = v_counter.update([{"track_id": 60, "center": (270, 240)}], w, h, frame_idx=4)
    check("Vertical line: Right-to-left registered as Alighting 1", s_vert2.total_alighting == 1)

    # ── TEST 8: Missing Tracking IDs and Frame Overlay ────────────────────────
    print("\n[TEST 8] Missing Tracking IDs & Overlay Rendering Safety")
    blank_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    # Unassigned track (missing or None track_id)
    s_safe = counter.update([{"track_id": None, "center": (100, 200)}], w, h, frame_idx=10)
    check("None track_id handled safely without exception", s_safe is not None)

    annotated = counter.draw_overlay(blank_frame, [{"track_id": 10, "center": (200, 270)}])
    check("Frame overlay generated with correct dimensions", annotated.shape == blank_frame.shape)

    # ── SUMMARY ───────────────────────────────────────────────────────────────
    print("\n" + "=" * 64)
    print(f"  RESULTS: {passed_checks}/{total_checks} checks passed, {total_checks - passed_checks} failed")
    if passed_checks == total_checks:
        print("  [OK] ALL ENTRY/EXIT COUNTER TESTS PASSED")
    else:
        print("  [FAIL] SOME TESTS FAILED")
    print("=" * 64)

    return passed_checks == total_checks


if __name__ == "__main__":
    run_self_tests()
