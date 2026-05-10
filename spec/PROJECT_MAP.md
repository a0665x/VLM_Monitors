# Project Map

## Name

VLM_Monitors

## Description

VLM_Monitors is a local-first monitoring system that turns old phones and browsers into camera publishers, then centralizes them in one shared Situation Room on a compute-capable Linux service host. It combines live camera capture, RTSP/HLS/WebRTC streaming, local Ollama VLM risk analysis, optional sound detection, and optional Twilio/webhook alerts.

The current runtime is a Flask + Socket.IO backend served by `src/server.py` on port `5000`. Some older Streamlit-oriented files still exist, especially `src/app.py` and `src/modes/*`; treat them as legacy or alternate UI code unless a task explicitly targets Streamlit.

## Read First

- [Architecture](./ARCHITECTURE.md): system boundaries, runtime entrypoints, and video/inference flow.
- [Modules](./MODULES.md): source tree ownership map and important files.
- [Runtime](./RUNTIME.md): Docker commands, ports, local dependencies, logs, tunnel behavior, and configuration.
- [API](./API.md): REST and Socket.IO interface exposed by `src/server.py`.
- [Situation Room](./SITUATION_ROOM.md): current multi-source Camera SRC / Situation Room behavior.
- [Troubleshooting](./TROUBLESHOOTING.md): likely field failures and debugging reminders.
- [To Do List](./TODO.md): follow-up engineering work and optimization backlog.
- [Project Overview](./PROJECT_OVERVIEW.md): broader technical narrative and performance context.
- [PRD](./PRD.md): product requirements and product intent.
- [Documentation Index](./DOCUMENTATION_INDEX.md): human-facing navigation map for project docs.
- [User Manual](./USER_MANUAL.md): operator-oriented usage guide.
- [Testing](./TESTING.md): available tests and verification commands.
- [Known Issues](./KNOWN_ISSUES.md): current browser, tunnel, and multi-source caveats.
- [Documentation Inventory](./references/documentation-inventory.md): existing root docs and how they map into this `./spec` structure.
- [Critical FAQ](../specs/FAQ.md): troubleshooting lessons, especially MediaMTX and HLS pitfalls.

## Spec Harness

Use the spec in this order:

1. `spec/PROJECT_MAP.md`: level-1 orientation and file map.
2. Level-2 behavior docs:
   `ARCHITECTURE.md`, `MODULES.md`, `RUNTIME.md`, `API.md`, `SITUATION_ROOM.md`, `TESTING.md`, `KNOWN_ISSUES.md`.
3. Spec supplements:
   `TROUBLESHOOTING.md`, `TODO.md`, `PROJECT_OVERVIEW.md`, `PRD.md`, `DOCUMENTATION_INDEX.md`, `USER_MANUAL.md`.
4. Deep references:
   `spec/references/*` and legacy `specs/FAQ.md`.

## Major Concepts

- `CameraThread`: captures `/dev/video0` through GStreamer, keeps the newest frame, overlays risk state, and publishes RTSP through FFmpeg.
- `MediaMTX`: RTSP/HLS/WebRTC server for both local camera and browser-published Camera SRC streams.
- `Flask backend`: `src/server.py` owns REST endpoints, Socket.IO updates, backend initialization, analysis thread, device switching, and notifications.
- `Risk detection`: `AnalysisThread` sends the latest frame to `InferenceEngine`, which calls Ollama VLM models through `OllamaClient`.
- `Situation Room`: many Camera SRC devices publish streams to one shared backend dashboard, while Risk Intelligence analyzes only the selected source.
- `Role gate`: browsers choose `Situation Room` or `Camera SRC` before joining the active UI flow; the choice is persisted in browser storage.
- `Tunnel choice`: `run.sh` now lets the operator choose `ngrok`, `Tailscale`, or no public tunnel before finishing startup.
- `Tailscale recovery`: if operator permission is missing, `run.sh` can show the exact `sudo tailscale set --operator` and `sudo tailscale funnel` commands and ask whether to run them.
- `Single-line wait progress`: startup waits for Flask/HLS/RTSP using one updating progress line instead of repeatedly printing `curl` errors.

## Change Guide

- For video capture, RTSP, HLS, latency, or camera controls, read [Architecture](./ARCHITECTURE.md), [Runtime](./RUNTIME.md), and [Critical FAQ](../specs/FAQ.md) before editing `src/shared/camera.py`, `src/server.py`, `mediamtx.yml`, or `static/js/app.js`.
- For backend API or UI state changes, read [API](./API.md), then edit `src/server.py`, `src/shared/state.py`, and frontend files under `static/`.
- For inference behavior, read [Modules](./MODULES.md), then inspect `src/pipelines/inference.py`, `src/adapters/ollama_client.py`, and `src/services/prompts.py`.
- For Docker/runtime changes, read [Runtime](./RUNTIME.md), then update `run.sh`, `Dockerfile`, and `docker-compose.yml` together.
- For documentation changes, preserve user-facing docs in place and update this map plus [Documentation Inventory](./references/documentation-inventory.md).

## File Map

- `src/server.py`: current main Flask/Socket.IO runtime.
- `src/shared/camera.py`: GStreamer capture, frame processing, overlays, and RTSP writing.
- `src/pipelines/inference.py`: Ollama VLM risk inference orchestration and frame logging.
- `src/shared/state.py`: shared in-memory app state used by camera, analysis, sound, and API handlers.
- `static/index.html`, `static/css/style.css`, `static/js/app.js`: current web UI assets.
- `Dockerfile`, `docker-compose.yml`: container image and host-network runtime.
- `run.sh`: primary operator script for startup, restart, status, logs, rebuild, shutdown, tunnel selection, and startup-time recovery prompts.
- `mediamtx.yml`: RTSP/HLS/WebRTC server configuration.
- `demo.png`: current UI / monitoring screenshot for README and presentations.

## Known Gaps

- `src/app.py` and `src/modes/*` remain Streamlit-oriented and may not represent the current primary runtime.
- Automated test coverage is still narrow; camera, HLS, Docker, and GPU behavior require manual/hardware verification.
- Long-running remote access through `ngrok` can hit plan/request limits; `Tailscale` is now a supported path in `run.sh`.
