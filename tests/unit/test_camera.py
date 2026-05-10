import pytest

from src.pipelines.camera import FrameCapture, MockCamera


def test_mock_camera_produces_frames():
    pytest.importorskip("cv2")
    camera = MockCamera(width=64, height=48)
    frame = camera.capture_frame(prompt_version=1)
    assert isinstance(frame, FrameCapture)
    assert frame.source == "mock-camera"
    assert frame.prompt_version == 1
    assert frame.preview_bytes  # bytes not empty
    assert camera.health()["ok"]
