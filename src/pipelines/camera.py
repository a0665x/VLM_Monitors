"""Camera abstractions for the monitoring pipeline."""
from __future__ import annotations

import time
import uuid
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import numpy as np

try:  # pragma: no cover - import guarded for environments without OpenCV
    import cv2  # type: ignore
except Exception:  # pragma: no cover - fallback for doc builds
    cv2 = None  # type: ignore


@dataclass
class FrameCapture:
    id: str
    timestamp: str
    source: str
    preview_bytes: bytes
    prompt_version: int
    status: str = "pending"
    error: Optional[str] = None


class CameraError(RuntimeError):
    pass


class CameraSource:
    """Base class for camera implementations."""

    def capture_frame(self, prompt_version: int) -> FrameCapture:  # pragma: no cover - interface only
        raise NotImplementedError

    def health(self) -> dict:  # pragma: no cover - interface only
        raise NotImplementedError


class OpenCVCamera(CameraSource):
    def __init__(self, device: str | int | None = None, width: int = 640, height: int = 480, fps: int = 10) -> None:
        # Force FFMPEG low latency flags
        import os
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "flags;low_delay|fflags;nobuffer"
        
        # Prioritize argument, then env var, then default
        if device is None:
            env_url = os.getenv("CAMERA_URL")
            if env_url:
                self.device = env_url
            else:
                self.device = "/dev/video0"
        else:
            self.device = device
            
        self.width = width
        self.height = height
        self.fps = fps
        self._capture = None
        
        # Threading for low-latency RTSP
        self._latest_frame = None
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread = None
        self._last_read_time = 0.0

    def _ensure_capture(self) -> None:
        if self._capture is not None:
            return
        if cv2 is None:
            raise CameraError("OpenCV is not available; install opencv-python")
            
        # Handle numeric device index if string is a number
        device_to_open = self.device
        if isinstance(self.device, str) and self.device.isdigit():
            device_to_open = int(self.device)
            
        cap = cv2.VideoCapture(device_to_open)
        
        # Optimize buffer size for RTSP to reduce latency
        if isinstance(self.device, str) and (self.device.startswith("rtsp://") or self.device.startswith("udp://")):
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            
        # Only set props for local devices (not RTSP streams usually)
        if not str(self.device).startswith("rtsp://"):
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            cap.set(cv2.CAP_PROP_FPS, self.fps)
            
        if not cap.isOpened():
            raise CameraError(f"Unable to open camera device {self.device}")
        self._capture = cap
        
        # Start background thread
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()

    def _capture_loop(self) -> None:
        """Continuously read frames to keep buffer empty."""
        while not self._stop_event.is_set() and self._capture is not None:
            if not self._capture.isOpened():
                break
            
            # Read frame
            success, frame = self._capture.read()
            if success:
                with self._lock:
                    self._latest_frame = frame
                    self._last_read_time = time.time()
            else:
                # If read fails, wait a bit to avoid busy loop
                time.sleep(0.01)

    def capture_frame(self, prompt_version: int) -> FrameCapture:
        self._ensure_capture()
        
        # Wait for first frame if needed
        start_wait = time.time()
        while self._latest_frame is None:
            if time.time() - start_wait > 5.0:
                raise CameraError("Timeout waiting for camera frame")
            time.sleep(0.1)
            
        with self._lock:
            frame = self._latest_frame.copy()
            
        if frame is None:
             raise CameraError("Failed to read from camera")

        preview_bytes = _encode_jpeg(frame)
        timestamp = datetime.now(timezone.utc).isoformat()
        return FrameCapture(
            id=str(uuid.uuid4()),
            timestamp=timestamp,
            source=str(self.device),
            preview_bytes=preview_bytes,
            prompt_version=prompt_version,
        )

    def health(self) -> dict:
        try:
            if self._capture is None:
                 return {"ok": False, "detail": "Camera not initialized"}
            if not self._capture.isOpened():
                 return {"ok": False, "detail": "Camera connection lost"}
            
            # Check if we are getting fresh frames
            if time.time() - self._last_read_time > 5.0:
                 return {"ok": False, "detail": "No frames received in last 5s"}
                 
        except Exception as exc:
            return {"ok": False, "detail": str(exc)}
        return {"ok": True, "detail": f"Streaming from {self.device}"}

    def close(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None
            
        if self._capture is not None:
            self._capture.release()
            self._capture = None


class MockCamera(CameraSource):
    def __init__(self, width: int = 640, height: int = 480) -> None:
        self.width = width
        self.height = height
        self._last_frame_time = 0.0
        self._counter = 0

    def capture_frame(self, prompt_version: int) -> FrameCapture:
        now = time.time()
        if now - self._last_frame_time < 0.05:
            time.sleep(0.05)
        self._last_frame_time = now
        self._counter += 1
        frame = self._generate_mock_frame()
        preview_bytes = _encode_jpeg(frame)
        timestamp = datetime.now(timezone.utc).isoformat()
        return FrameCapture(
            id=str(uuid.uuid4()),
            timestamp=timestamp,
            source="mock-camera",
            preview_bytes=preview_bytes,
            prompt_version=prompt_version,
        )

    def _generate_mock_frame(self) -> np.ndarray:
        gradient = np.linspace(0, 255, self.width, dtype=np.uint8)
        frame = np.tile(gradient, (self.height, 1))
        frame = np.stack([frame, np.flipud(frame), gradient.reshape(1, -1).repeat(self.height, axis=0)], axis=2)
        frame = frame.astype(np.uint8)
        frame = np.roll(frame, self._counter % self.width, axis=1)
        return frame

    def health(self) -> dict:
        return {"ok": True, "detail": "Mock camera active"}


def _encode_jpeg(frame: np.ndarray) -> bytes:
    if cv2 is None:
        raise CameraError("OpenCV is required for JPEG encoding")
    success, buffer = cv2.imencode(".jpg", frame)
    if not success:
        raise CameraError("Failed to encode frame to JPEG")
    return buffer.tobytes()


__all__ = [
    "FrameCapture",
    "CameraSource",
    "OpenCVCamera",
    "MockCamera",
    "CameraError",
]
