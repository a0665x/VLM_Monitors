# Modules

## Summary

This map describes the project by ownership area. Use it before editing source files so changes land in the right layer.

## Top-Level Files

- `Dockerfile`: container image; installs Flask, Playwright base, GStreamer, FFmpeg, audio utilities, and Python dependencies.
- `docker-compose.yml`: host-network container runtime with NVIDIA runtime, camera/audio device mounts, and source/data/temp volumes.
- `run.sh`: canonical operator entrypoint for `up`, `restart`, `status`, `logs`, `down`, `rebuild`, and `destroy`.
- `mediamtx.yml`: MediaMTX RTSP/HLS config; HLS behavior is sensitive to this file.
- `requirements.txt`: Python dependency set.

## `src/server.py`

Current main backend. Owns:

- Flask and Socket.IO app creation.
- backend initialization order.
- MediaMTX startup.
- `AnalysisThread`.
- source registry APIs and single-Situation-Room lock.
- selected-source remote frame tap thread.
- REST routes under `/api/*`.
- Socket.IO connection/status/metrics events.
- metric emitter background thread.

## `src/shared/`

Shared runtime state and camera pipeline:

- `state.py`: `AppState`, the in-memory state object shared across threads and handlers.
- `camera.py`: `CameraThread`, device enumeration, GStreamer capture, camera control, RTSP publishing, and overlay application.
- `camera.py.bak`: backup artifact; do not treat as active code unless explicitly comparing history.

## `src/pipelines/`

Pipeline abstractions:

- `camera.py`: frame capture protocol/mock helpers used by inference.
- `inference.py`: VLM risk inference orchestration, result dataclasses, alert state, and frame/log persistence.

## `src/adapters/`

External model adapters:

- `ollama_client.py`: Ollama model discovery, generation, capability filtering, and unload behavior.

## `src/services/`

Support services:

- `prompts.py`: risk prompt persistence and history.
- `notifier.py`: Twilio SMS and webhook notification logic.
- `sound_detection.py`: optional sound classifier thread and FPS/risk updates.
- `system_monitor.py`: CPU/RAM/GPU metrics.
- `device_manager.py`: device discovery helpers.
- `readiness.py`, `qa.py`, `gemini_handler.py`: supporting service code; inspect before changing related UI or chat behavior.

## `src/tools/`

Tool-calling support:

- `registry.py`: tool registry.
- `camera_capture.py`: current-frame capture tool.
- `web_scraper.py`: web scraping tool.

These are mainly referenced by the Streamlit interactive chat code.

## `src/modes/`

Streamlit-oriented legacy or alternate mode modules:

- `risk_detection.py`
- `interactive_chat.py`

The current Docker runtime does not start these directly. Use them only for tasks that explicitly target the Streamlit UI path.

## `static/`

Current Flask-served frontend:

- `index.html`: UI shell.
- `css/style.css`: styling for role gate, Situation Room grid, Camera SRC, and Risk Intelligence.
- `js/app.js`: browser logic, role selection persistence, source registry, ngrok public URL handling, REST calls, and Socket.IO updates.

## `tests/`

Existing tests focus on notification behavior:

- `tests/test_notifier.py`
- `tests/conftest.py`
- `tests/unit/test_server_status.py`: status payload, auto-analysis reset, source/mode behavior, and source disconnect fallback.

There are no comprehensive tests for camera, Docker, HLS, MediaMTX, or Jetson-specific GPU behavior.
