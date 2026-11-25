# Sample Videos Directory for Passenger Counting (Module 4)

Place your test video files (`.mp4`, `.avi`, `.mov`, `.mkv`) in this folder.

### What kind of video works best?
- Overhead or door-facing camera angle overlooking the bus entrance / exit.
- Clear view of passengers boarding and alighting.
- Standard resolutions (720p or 1080p) at 15–30 FPS.

### Note on Pretrained Models & Custom Training
- Module 4 by default uses the pretrained `yolov8n.pt` model (detecting the standard COCO `person` class) combined with ByteTrack tracking.
- Once you collect and label a domain-specific bus passenger dataset, place the fine-tuned model weights at:
  `models/weights/best.pt`
- The system automatically checks for `models/weights/best.pt` and lets you select it in the dashboard.
