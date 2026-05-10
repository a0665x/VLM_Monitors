import asyncio

import pytest

from src.adapters.ollama_client import OllamaResponse
from src.pipelines.camera import FrameCapture
from src.pipelines.inference import InferenceEngine
from src.services.prompts import PromptStore, RiskPrompt

import numpy as np

try:
    import cv2  # type: ignore
except Exception:  # pragma: no cover
    cv2 = None  # type: ignore


class DummyCamera:
    def __init__(self, preview_bytes: bytes):
        self.preview_bytes = preview_bytes
        self._captures = 0

    def capture_frame(self, prompt_version: int) -> FrameCapture:
        self._captures += 1
        return FrameCapture(
            id=f"frame-{self._captures}",
            timestamp="2025-11-18T00:00:00Z",
            source="dummy",
            preview_bytes=self.preview_bytes,
            prompt_version=prompt_version,
        )

    def health(self) -> dict:
        return {"ok": True, "detail": "dummy"}


class DummyPromptStore(PromptStore):
    def __init__(self, prompt: RiskPrompt):
        self._prompt = prompt

    def load(self) -> RiskPrompt:  # type: ignore[override]
        return self._prompt

    def update(self, text: str, updated_by: str | None = None) -> RiskPrompt:  # pragma: no cover - not used
        raise NotImplementedError


class DummyClient:
    def __init__(self, risk: bool):
        self._risk = risk

    async def generate(self, system_prompt: str, user_prompt: str, image_bytes=None) -> OllamaResponse:
        return OllamaResponse(
            text="unsafe" if self._risk else "clear",
            model="dummy",
            latency_ms=100,
            confidence=0.9 if self._risk else 0.1,
            risk=self._risk,
        )


def _jpeg_bytes() -> bytes:
    pytest.importorskip("cv2")
    frame = np.zeros((32, 32, 3), dtype=np.uint8)
    success, buffer = cv2.imencode(".jpg", frame)
    assert success
    return buffer.tobytes()


def test_engine_transitions_to_risk_state():
    store = DummyPromptStore(RiskPrompt(text="alert"))
    engine = InferenceEngine(
        camera=DummyCamera(_jpeg_bytes()),
        prompt_store=store,
        ollama_client=DummyClient(risk=True),
    )
    _, result, alert = asyncio.run(engine.process_next_frame())
    assert result.risk is True
    assert alert.state == "risk"


def test_engine_clears_after_acknowledgement():
    store = DummyPromptStore(RiskPrompt(text="alert"))
    camera = DummyCamera(_jpeg_bytes())
    engine = InferenceEngine(camera=camera, prompt_store=store, ollama_client=DummyClient(risk=True))
    asyncio.run(engine.process_next_frame())
    engine.acknowledge_alert()
    engine.ollama_client = DummyClient(risk=False)  # type: ignore
    asyncio.run(engine.process_next_frame())
    assert engine.alert_state.state == "monitoring"
