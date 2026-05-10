# Architecture

## Summary

VLM_Monitors is a Jetson-targeted local monitoring stack. The current production-shaped path is Docker -> `src/server.py` -> Flask/Socket.IO UI -> GStreamer camera capture -> MediaMTX RTSP/HLS/WebRTC -> Ollama VLM analysis and notifications.

## Runtime Boundary

Current primary entrypoint:

```text
Dockerfile CMD ["python", "src/server.py"]
```

Legacy or alternate Streamlit entrypoint:

```text
src/app.py
```

Do not assume Streamlit is the active runtime unless the task specifically names it. The Docker and shell scripts expose the Flask server on `http://localhost:5000`.

## Component Flow

```text
AGX local camera (/dev/video0)
  -> GStreamer v4l2src pipeline
  -> CameraThread raw queue
  -> frame processor overlays local risk/sound state
  -> latest local frame stored in AppState
  -> FFmpeg publishes RTSP path `camera`
  -> MediaMTX serves RTSP, HLS, and WebRTC

browser Camera SRC
  -> operator selects Camera SRC role
  -> browser opens MediaMTX publish page on path <source_id>/publish
  -> MediaMTX receives remote stream on dynamic path <source_id>
  -> backend source registry marks source online
  -> Situation Room renders source tile from dynamic WebRTC or proxied HLS, depending on client context

selected source
  -> AnalysisThread
  -> local latest frame or selected remote frame tap
  -> InferenceEngine
  -> OllamaClient
  -> Ollama VLM on host
  -> AppState risk fields
  -> Socket.IO status_update
  -> Twilio/webhook alert if thresholds pass
```

## Camera And Streaming

`src/shared/camera.py` owns camera capture. It uses:

- `v4l2src` with `/dev/video0` by default.
- `queue max-size-buffers=1 leaky=downstream` to avoid stale frames.
- `videoconvert` to BGR.
- aggressive `v4l2-ctl` camera controls to stabilize FPS.
- a small raw queue and a one-frame RTSP queue.

The critical lesson from `specs/FAQ.md`: MediaMTX must load `mediamtx.yml`, and HLS web playback depends on `hlsAlwaysRemux: yes`.

## Backend

`src/server.py` initializes and owns:

- MediaMTX with `./temp/mediamtx ./mediamtx.yml`.
- `AppState`.
- `CameraThread`.
- `PromptStore`.
- `OllamaClient`.
- `InferenceEngine`.
- `AnalysisThread`.
- selected-source remote frame tap management.
- source registry and source selection/fallback logic.
- periodic metrics emitter.

The Flask app serves `static/index.html` and REST APIs. Socket.IO emits live risk/status/metrics/source updates.

## Multi-Source Situation Room

Current behavior:

- Multiple browsers can enter `Situation Room`.
- These browsers control the same AGX-hosted monitoring state.
- Browsers still land on a role gate before joining either path.
- Browser role selection is persisted locally in the browser.
- Situation Room shows a responsive source grid:
  - `1` source -> `1x1`
  - `2` sources -> `1x2`
  - `3-4` sources -> `2x2`
  - `5+` sources -> `3x3`
- The selected source is highlighted and is the only source analyzed by VLM.
- If the selected remote source disconnects, analysis falls back to `AGX Local Camera`.

## Browser Publishing Model

The browser Camera SRC flow is intentionally split into two steps:

1. choose `Camera SRC` role
2. press `Start Camera Sharing`

Only step 2 registers the source and starts heartbeats.

For Safari/iPhone, the publish page is opened in a top-level tab/window because cross-origin iframe permission prompts are unreliable for camera access.

For HTTPS `Situation Room` clients, playback may use a same-origin HLS proxy route instead of direct cross-origin WebRTC iframe playback.

## Secure Remote Access

For same-network desktop debugging, LAN `http://<agx-ip>:5000` still works.

For iPhone/Safari Camera SRC, the preferred operator path is:

- `run.sh` starts ngrok UI and WebRTC tunnels
- the browser opens the printed `Public UI` HTTPS URL
- frontend uses the printed `Public RTC` HTTPS base for MediaMTX WebRTC/publish pages

This secure-origin path is the current recommended remote flow.

## Inference

`src/pipelines/inference.py` uses a one-stage VLM prompt. It asks the selected model to answer `YES` or `NO` against the current risk criteria, then parses the response into `risk=True/False`.

Important behavior:

- If no frame is available, inference returns a safe non-risk result with an explanation.
- When a remote source is newly selected, analysis now waits briefly for the first tapped frame before surfacing `No frame available yet`.
- Latest analyzed frame is saved to `temp/short_cut.jpg`.
- Interactions are logged to `temp/llm.log`.
- Confidence is currently binary: `1.0` for risk, `0.0` for non-risk.

## Notifications

Risk alerts are controlled by shared state:

- `risk_threshold`: required consecutive risk count.
- `alert_cooldown`: minimum seconds between alerts.
- `enable_sms`: Twilio SMS toggle.
- `enable_webhook`: webhook toggle.
- `webhook_url`: n8n/Zapier-compatible endpoint.

Alerts should be changed carefully because camera inference, sound risk, and UI status share the same `AppState`.

## External Dependencies

- NVIDIA Jetson or compatible Linux + NVIDIA runtime.
- Docker and Docker Compose.
- USB camera, usually `/dev/video0`.
- Ollama running on the host at `localhost:11434`.
- MediaMTX binary at `temp/mediamtx`.
- Optional ngrok for public UI URL.
- Optional Twilio credentials for SMS.
