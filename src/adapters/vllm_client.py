"""Vision client for a vLLM OpenAI-compatible server."""
from __future__ import annotations

import base64
import json
import os
import time
import httpx
from .ollama_client import OllamaResponse


class VLLMClient:
    def __init__(self, base_url=None, model=None, timeout=None):
        self.base_url = (base_url or os.getenv("VLLM_BASE_URL", "http://127.0.0.1:8000/v1")).rstrip("/")
        self.model = model or os.getenv("VLM_MODEL", "Qwen/Qwen2.5-VL-3B-Instruct")
        self.timeout = timeout or float(os.getenv("VLM_TIMEOUT", "120"))
        key = os.getenv("VLLM_API_KEY")
        self.headers = {"Authorization": f"Bearer {key}"} if key else {}

    def _payload(self, system_prompt, user_prompt, image_bytes, model, stream):
        content = [{"type": "text", "text": user_prompt}]
        if image_bytes:
            encoded = base64.b64encode(image_bytes).decode("ascii")
            content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{encoded}"}})
        return {
            "model": model or self.model,
            "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": content}],
            "temperature": float(os.getenv("VLM_TEMPERATURE", "0")),
            "max_tokens": int(os.getenv("VLM_MAX_TOKENS", "128")),
            "stream": stream,
        }

    @staticmethod
    def _result(text, model, start):
        # InferenceEngine performs the final YES/NO interpretation.
        risk = text.strip().lower().startswith("yes")
        return OllamaResponse(text=text, model=model, latency_ms=int((time.perf_counter()-start)*1000),
                              confidence=1.0 if risk else 0.0, risk=risk)

    async def generate(self, system_prompt, user_prompt, image_bytes=None, model=None):
        payload = self._payload(system_prompt, user_prompt, image_bytes, model, False)
        start = time.perf_counter()
        async with httpx.AsyncClient(timeout=self.timeout, headers=self.headers) as client:
            response = await client.post(f"{self.base_url}/chat/completions", json=payload)
            response.raise_for_status()
            data = response.json()
        return self._result(data["choices"][0]["message"].get("content") or "", data.get("model", payload["model"]), start)

    async def generate_stream(self, system_prompt, user_prompt, image_bytes=None, model=None, on_chunk=None):
        payload = self._payload(system_prompt, user_prompt, image_bytes, model, True)
        start = time.perf_counter()
        text = ""
        model_name = payload["model"]
        async with httpx.AsyncClient(timeout=self.timeout, headers=self.headers) as client:
            async with client.stream("POST", f"{self.base_url}/chat/completions", json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    body = line[5:].strip()
                    if body == "[DONE]":
                        break
                    data = json.loads(body)
                    if "error" in data:
                        raise RuntimeError(f"vLLM stream error: {data['error']}")
                    model_name = data.get("model", model_name)
                    choices = data.get("choices", [])
                    piece = (choices[0].get("delta", {}).get("content") or "") if choices else ""
                    if piece:
                        text += piece
                        if on_chunk:
                            on_chunk(text, False)
        if on_chunk:
            on_chunk(text, True)
        return self._result(text, model_name, start)

    def get_models(self, capability=None):
        # /models lists served models; configure this server with a vision model.
        with httpx.Client(timeout=5, headers=self.headers) as client:
            response = client.get(f"{self.base_url}/models")
            response.raise_for_status()
            return [item["id"] for item in response.json()["data"]]

    def unload_model(self, model_name):
        # vLLM owns GPU memory for the lifetime of its service.
        return None
