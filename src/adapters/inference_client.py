"""Select the inference service once at process startup."""
import os
from .ollama_client import OllamaClient
from .vllm_client import VLLMClient


def backend_name():
    name = os.getenv("VLM_BACKEND", "ollama").lower()
    if name not in {"ollama", "vllm"}:
        raise ValueError(f"Unsupported VLM_BACKEND: {name}")
    return name


def default_model():
    fallback = "Qwen/Qwen2.5-VL-3B-Instruct" if backend_name() == "vllm" else "qwen3-vl:8b"
    return os.getenv("VLM_MODEL", fallback)


def create_inference_client(backend=None, model=None):
    backend = backend or backend_name()
    model = model or default_model()
    if backend == "vllm":
        return VLLMClient(model=model)
    if backend != "ollama":
        raise ValueError("Unknown inference backend")
    return OllamaClient(model=model, timeout=float(os.getenv("VLM_TIMEOUT", "120")))
