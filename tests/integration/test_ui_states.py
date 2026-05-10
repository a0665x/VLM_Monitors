import asyncio

import pytest

gr = pytest.importorskip("gradio")
import numpy as np

from src.adapters.ollama_client import OllamaResponse
from src.app import MonitoringApp
from src.pipelines.camera import MockCamera
from src.services.prompts import PromptStore


class FakeOllamaClient:
    def __init__(self) -> None:
        self.risk = False

    async def generate(self, system_prompt: str, user_prompt: str, image_bytes=None) -> OllamaResponse:
        return OllamaResponse(
            text="All clear",
            model="fake",
            latency_ms=50,
            confidence=0.1,
            risk=self.risk,
        )

    async def ensure_model(self) -> None:
        return None


def test_monitoring_app_flow(tmp_path):
    pytest.importorskip("cv2")
    store = PromptStore(path=tmp_path / "prompt.json")
    store.load()
    app = MonitoringApp(camera=MockCamera(width=32, height=32), prompt_store=store, ollama_client=FakeOllamaClient())

    frame_np, state, message, log = asyncio.run(app.analyze_once())
    assert state == "Monitoring"
    assert "Frame" in log
    assert frame_np is None or isinstance(frame_np, np.ndarray)

    info = app.apply_prompt("Watch crib rails")
    assert "v2" in info

    qa_text = asyncio.run(app.ask_question("What is happening?"))
    assert "Q: What is happening?" in qa_text

    ui = app.build_ui()
    assert isinstance(ui, gr.Blocks)
