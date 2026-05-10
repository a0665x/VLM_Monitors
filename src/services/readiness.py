"""Health check helpers for Ollama and the camera."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Protocol


@dataclass
class ComponentHealth:
    component: str
    ok: bool
    message: str


class OllamaClientProtocol(Protocol):
    async def ensure_model(self) -> None:  # pragma: no cover - protocol definition
        ...


class CameraProtocol(Protocol):
    def health(self) -> dict:  # pragma: no cover - protocol definition
        ...


async def check_ollama(client: OllamaClientProtocol) -> ComponentHealth:
    try:
        await asyncio.wait_for(client.ensure_model(), timeout=30)
    except Exception as exc:  # pragma: no cover - network/runtime dependent
        return ComponentHealth(component="ollama", ok=False, message=str(exc))
    return ComponentHealth(component="ollama", ok=True, message="OK")


def check_camera(camera: CameraProtocol) -> ComponentHealth:
    try:
        status = camera.health()
        ok = bool(status.get("ok", False))
        message = status.get("detail", "OK" if ok else "Unavailable")
        return ComponentHealth(component="camera", ok=ok, message=message)
    except Exception as exc:  # pragma: no cover - hardware dependent
        return ComponentHealth(component="camera", ok=False, message=str(exc))


__all__ = ["ComponentHealth", "check_camera", "check_ollama"]
