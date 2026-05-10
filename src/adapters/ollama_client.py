"""Async Ollama HTTP client wrapper."""
from __future__ import annotations

import base64
import logging
import time
import json
from dataclasses import dataclass
import os
from typing import Any, Dict, Optional

try:  # pragma: no cover - allow test environments without httpx installed
    import httpx  # type: ignore
except Exception:  # pragma: no cover
    httpx = None  # type: ignore

logger = logging.getLogger(__name__)


class OllamaError(RuntimeError):
    """Raised when the Ollama API reports a failure."""


@dataclass
class OllamaResponse:
    text: str
    model: str
    latency_ms: int
    confidence: float
    risk: bool


class OllamaClient:
    """Thin wrapper around the Ollama HTTP endpoints."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "qwen3-vl:8b",
        timeout: float = 30.0,
    ) -> None:
        configured_base_url = os.getenv("OLLAMA_BASE_URL") or os.getenv("OLLAMA_HOST") or base_url
        self.base_url = configured_base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    async def ensure_model(self) -> None:
        """Verify the configured model exists on the local Ollama instance."""
        if httpx is None:  # pragma: no cover - dependency missing during certain tests
            raise OllamaError("httpx is not installed; install requirements to query Ollama.")
        url = f"{self.base_url}/api/tags"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            payload = resp.json()

        models = {item.get("name") for item in payload.get("models", [])}
        if self.model not in models:
            raise OllamaError(
                f"Model {self.model} not found. Run `ollama pull {self.model}` before launching."
            )

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        image_bytes: Optional[bytes] = None,
        model: Optional[str] = None,
    ) -> OllamaResponse:
        """Call the /api/generate endpoint with the provided prompts and optional image."""
        if httpx is None:  # pragma: no cover - dependency missing during certain tests
            raise OllamaError("httpx is not installed; install requirements to query Ollama.")
        
        # Combine system and user prompts for /api/generate
        full_prompt = f"{system_prompt}\n\n{user_prompt}"
        
        payload: Dict[str, Any] = {
            "model": model or self.model,
            "prompt": full_prompt,
            "stream": False,
        }

        if image_bytes:
            # For /api/generate, images go in the top-level images array
            # Run base64 encoding in thread to avoid blocking
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                b64_img = await loop.run_in_executor(None, lambda: base64.b64encode(image_bytes).decode("utf-8"))
            except RuntimeError:
                b64_img = base64.b64encode(image_bytes).decode("utf-8")
                
            payload["images"] = [b64_img]

        url = f"{self.base_url}/api/generate"
        start = time.perf_counter()
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(url, json=payload)
            try:
                resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                logger.error("Ollama HTTP error: %s", exc)
                raise OllamaError(str(exc)) from exc
            data = resp.json()

        elapsed_ms = int((time.perf_counter() - start) * 1000)
        # For /api/generate, response is in "response" field not "message"
        text = data.get("response", "")
        latency_ms = int(data.get("total_duration", elapsed_ms * 1000) / 1_000_000)
        if not latency_ms:
            latency_ms = elapsed_ms

        confidence = self._extract_confidence(text)
        risk = self._detect_risk(text, confidence)
        logger.debug("Ollama response: model=%s risk=%s conf=%.2f", self.model, risk, confidence)
        return OllamaResponse(
            text=text,
            model=data.get("model", self.model),
            latency_ms=latency_ms,
            confidence=confidence,
            risk=risk,
        )

    async def generate_stream(
        self,
        system_prompt: str,
        user_prompt: str,
        image_bytes: Optional[bytes] = None,
        model: Optional[str] = None,
        on_chunk=None,
    ) -> OllamaResponse:
        """Call the /api/generate endpoint in streaming mode and forward partial text."""
        if httpx is None:  # pragma: no cover - dependency missing during certain tests
            raise OllamaError("httpx is not installed; install requirements to query Ollama.")

        full_prompt = f"{system_prompt}\n\n{user_prompt}"
        payload: Dict[str, Any] = {
            "model": model or self.model,
            "prompt": full_prompt,
            "stream": True,
        }

        if image_bytes:
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                b64_img = await loop.run_in_executor(None, lambda: base64.b64encode(image_bytes).decode("utf-8"))
            except RuntimeError:
                b64_img = base64.b64encode(image_bytes).decode("utf-8")
            payload["images"] = [b64_img]

        url = f"{self.base_url}/api/generate"
        start = time.perf_counter()
        chunks: list[str] = []
        model_name = model or self.model

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream("POST", url, json=payload) as resp:
                try:
                    resp.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    logger.error("Ollama streaming HTTP error: %s", exc)
                    raise OllamaError(str(exc)) from exc

                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    data = json.loads(line)
                    model_name = data.get("model", model_name)
                    piece = data.get("response", "")
                    if piece:
                        chunks.append(piece)
                        if on_chunk is not None:
                            on_chunk("".join(chunks), False)
                    if data.get("done"):
                        break

        elapsed_ms = int((time.perf_counter() - start) * 1000)
        text = "".join(chunks)
        confidence = self._extract_confidence(text)
        risk = self._detect_risk(text, confidence)
        if on_chunk is not None:
            on_chunk(text, True)
        return OllamaResponse(
            text=text,
            model=model_name,
            latency_ms=elapsed_ms,
            confidence=confidence,
            risk=risk,
        )

    @staticmethod
    def _extract_confidence(text: str) -> float:
        """Attempt to extract a numeric confidence score from the textual answer."""
        marker = "confidence:"
        lowered = text.lower()
        if marker in lowered:
            try:
                value = lowered.split(marker, 1)[1].split()[0]
                return max(0.0, min(1.0, float(value)))
            except (ValueError, IndexError):
                pass
        return 0.5  # neutral default

    @staticmethod
    def _detect_risk(text: str, confidence: float) -> bool:
        """Derive a coarse risk flag from the response text + confidence."""
        keywords = ["unsafe", "danger", "risk", "fall"]
        text_lower = text.lower()
        if any(word in text_lower for word in keywords):
            return confidence >= 0.4
        return confidence >= 0.8


    @staticmethod
    def get_models(base_url: str = "http://localhost:11434", capability: Optional[str] = None) -> list[str]:
        """
        Fetch models from Ollama and optionally filter by capability ('vision' or 'tools').
        """
        try:
            if httpx is None:
                return []
            
            base_url = (os.getenv("OLLAMA_BASE_URL") or os.getenv("OLLAMA_HOST") or base_url).rstrip("/")
            url = f"{base_url}/api/tags"
            
            # Use synchronous client for Streamlit UI (usually runs in thread)
            # or we can use requests if httpx is async only? 
            # httpx.Client is sync.
            with httpx.Client(timeout=5.0) as client:
                resp = client.get(url)
                if resp.status_code != 200:
                    return []
                data = resp.json()
                
            all_models = [m["name"] for m in data.get("models", [])]
            
            if not capability:
                return all_models
                
            filtered_models = []
            with httpx.Client(timeout=20.0) as client: # Longer timeout for multiple calls
                for model in all_models:
                    try:
                        # Inspect model details
                        show_url = f"{base_url}/api/show"
                        resp = client.post(show_url, json={"name": model})
                        if resp.status_code != 200:
                            continue
                        
                        details = resp.json()
                        info = details.get("model_info", {})
                        families = details.get("details", {}).get("families") or []
                        template = details.get("template", "") or ""
                        
                        is_match = False
                        
                        if capability == "vision":
                            # Check for vision keywords in families or model_info
                            # 1. Families check
                            if any(f in ["clip", "mllama", "minicpm-v"] for f in families):
                                is_match = True
                            # 2. Model Info check
                            elif "vision" in str(info).lower() or "clip" in str(info).lower() or "projector" in str(info).lower():
                                is_match = True
                            # 3. Name check (fallback)
                            elif any(k in model.lower() for k in ["vision", "llava", "minicpm", "vl"]):
                                is_match = True
                                
                        elif capability == "tools":
                            # Check for tool support
                            # 1. Template check (most reliable for generic models)
                            if "tool" in template.lower():
                                is_match = True
                            # 2. Families check (known tool-supporting families)
                            elif any(f in ["llama3.1", "llama3.2", "mistral-nemo", "qwen2.5", "command-r", "firefunction"] for f in families):
                                is_match = True
                        
                        if is_match:
                            filtered_models.append(model)
                            
                    except Exception as e:
                        logger.warning(f"Failed to inspect model {model}: {e}")
                        continue
                        
            return filtered_models
            
        except Exception as e:
            logger.error(f"Error fetching models: {e}")
            return []


    @staticmethod
    def unload_model(model_name: str, base_url: str = "http://localhost:11434") -> None:
        """
        Explicitly unload a model from memory by setting keep_alive to 0.
        """
        try:
            if httpx is None:
                return
            
            base_url = (os.getenv("OLLAMA_BASE_URL") or os.getenv("OLLAMA_HOST") or base_url).rstrip("/")
            url = f"{base_url}/api/generate"
            
            payload = {
                "model": model_name,
                "keep_alive": 0
            }
            
            # Use a short timeout, we just want to trigger the unload
            with httpx.Client(timeout=2.0) as client:
                client.post(url, json=payload)
                logger.info(f"Requested unload for model: {model_name}")
                
        except Exception as e:
            logger.warning(f"Failed to unload model {model_name}: {e}")


__all__ = ["OllamaClient", "OllamaResponse", "OllamaError"]
