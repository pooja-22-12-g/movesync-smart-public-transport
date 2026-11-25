"""
passenger_counting/passenger_counting.py
========================================
Module 4, Step 2: Video Processing Pipeline for YOLO & ByteTrack
Smart Public Transport Occupancy and Fleet Monitoring System
------------------------------------------------------------
PURPOSE:
  - Coordinate video ingestion (MP4, AVI) via OpenCV.
  - Run sequential frame-by-frame person detection and ByteTrack tracking.
  - Keep tracking and detection modules cleanly decoupled.
  - Ensure safe resource acquisition and deterministic release of cv2.VideoCapture.
  - Provide a standalone execution test and diagnostics.
"""

from __future__ import annotations

import os
import time
from typing import Optional, Callable, Dict, Any, List

import cv2
import numpy as np

try:
    from passenger_counting.yolo_detector import YOLOPersonDetector
    from passenger_counting.bytetrack_tracker import ByteTrackTracker, TrackedPerson
except ModuleNotFoundError:
    from yolo_detector import YOLOPersonDetector
    from bytetrack_tracker import ByteTrackTracker, TrackedPerson


class VideoPassengerTracker:
    """
    Coordinates video reading, sequential frame processing,
    person detection, ByteTrack tracking, and video writing/display.
    """

    def __init__(
        self,
        model_path: str = "yolov8n.pt",
        conf_threshold: float = 0.35,
        iou_threshold: float = 0.45,
    ):
        self.model_path = model_path
        self.conf_threshold = conf_threshold
        self.iou_threshold = iou_threshold

        # Decoupled tracker and detector components
        self.tracker = ByteTrackTracker(
            model_path=model_path,
            conf_threshold=conf_threshold,
            iou_threshold=iou_threshold,
        )

    def process_video_file(
        self,
        video_path: str,
        output_path: Optional[str] = None,
        max_frames: Optional[int] = None,
        frame_callback: Optional[Callable[[int, np.ndarray, List[TrackedPerson]], bool]] = None,
    ) -> Dict[str, Any]:
        """
        Reads and processes a video file frame-by-frame.

        Args:
            video_path: Path to MP4, AVI, or other OpenCV-supported video file.
            output_path: Optional path to save the annotated video.
            max_frames: Maximum number of frames to process (useful for preview/testing).
            frame_callback: Optional callback receiving (frame_idx, annotated_frame, active_tracks).
                           If callback returns False, processing stops early.

        Returns:
            Dictionary containing processing summary statistics.
        """
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found at: {video_path}")

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError(f"Could not open video file: {video_path}. Verify file format (MP4/AVI).")

        total_file_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = float(cap.get(cv2.CAP_PROP_FPS))
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        writer: Optional[cv2.VideoWriter] = None
        if output_path:
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            writer = cv2.VideoWriter(output_path, fourcc, fps if fps > 0 else 30.0, (width, height))

        self.tracker.reset()
        frames_processed = 0
        start_time = time.time()

        try:
            while True:
                if max_frames and frames_processed >= max_frames:
                    break

                ret, frame = cap.read()
                if not ret or frame is None:
                    break

                frames_processed += 1

                # Update ByteTrack tracker
                active_tracks = self.tracker.update(frame)

                # Render annotations
                annotated_frame = self.tracker.draw_tracks(frame, active_tracks)

                if writer:
                    writer.write(annotated_frame)

                if frame_callback:
                    should_continue = frame_callback(frames_processed, annotated_frame, active_tracks)
                    if should_continue is False:
                        break

        finally:
            # Guarantee safe resource release
            cap.release()
            if writer:
                writer.release()

        elapsed = time.time() - start_time
        effective_fps = round(frames_processed / elapsed, 2) if elapsed > 0 else 0.0

        return {
            "video_path": video_path,
            "total_file_frames": total_file_frames,
            "frames_processed": frames_processed,
            "fps": fps,
            "resolution": (width, height),
            "effective_processing_fps": effective_fps,
            "elapsed_seconds": round(elapsed, 2),
            "unique_people_tracked": len(self.tracker.unique_track_ids),
        }


def self_test_video_pipeline():
    """Unit test for VideoPassengerTracker."""
    print("=" * 60)
    print("  [TEST] VideoPassengerTracker Self-Test")
    print("=" * 60)

    # 1. Pipeline initialization
    print("1. Initializing VideoPassengerTracker...")
    pipeline = VideoPassengerTracker(model_path="yolov8n.pt")
    assert pipeline.tracker is not None, "Failed to initialize pipeline tracker"
    print("   [PASS] Pipeline tracker initialized cleanly.")

    # 2. Synthetic video test (creating temporary 15-frame video to verify OpenCV stream)
    temp_video_path = os.path.join("data", "cv_sessions", "synthetic_test_video.avi")
    os.makedirs(os.path.join("data", "cv_sessions"), exist_ok=True)

    fourcc = cv2.VideoWriter_fourcc(*"MJPG")
    out = cv2.VideoWriter(temp_video_path, fourcc, 15.0, (320, 240))
    for i in range(15):
        frame = np.full((240, 320, 3), i * 15, dtype=np.uint8)
        out.write(frame)
    out.release()
    print("2. Created synthetic 15-frame test video (OpenCV MJPG AVI)...")

    # 3. Process synthetic video
    print("3. Processing synthetic video through YOLO + ByteTrack pipeline...")
    stats = pipeline.process_video_file(temp_video_path, max_frames=10)
    assert stats["frames_processed"] == 10, f"Expected 10 frames, got {stats['frames_processed']}"
    assert stats["resolution"] == (320, 240), f"Expected (320, 240), got {stats['resolution']}"
    print(f"   [PASS] Processed {stats['frames_processed']} frames successfully.")

    # Cleanup temporary synthetic file
    if os.path.exists(temp_video_path):
        os.remove(temp_video_path)

    print("\n   [OK] VideoPassengerTracker passed all tests!")


if __name__ == "__main__":
    self_test_video_pipeline()

