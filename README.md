# VLM_Monitors

Local-first, multi-source video monitoring for NVIDIA Jetson-class Linux hosts. Browser and phone cameras publish through MediaMTX; a Flask + Socket.IO control plane renders the shared Situation Room and sends only the selected source to a local Ollama vision-language model for risk inference.

![VLM_Monitors Situation Room](./demo.png)

## Runtime status

The supported runtime is:

```text
src/server.py
  ├─ Flask REST API + static WebUI
  ├─ Flask-SocketIO state/metrics events
  ├─ CameraThread (GStreamer capture)
  ├─ AnalysisThread (selected-source inference)
  └─ MediaMTX process management
```

`src/app.py` and `src/modes/*` are legacy/alternate Streamlit-oriented code paths. Do not treat them as the production entrypoint unless a change explicitly targets them.

## System topology

```text
/dev/video0 ── GStreamer ── CameraThread ── FFmpeg RTSP ─┐
                                                        │
phone/browser ── WebRTC publish ───────────────── MediaMTX
                                                        │
                              RTSP / HLS / WebRTC playback
                                                        │
                                         Situation Room UI
                                                        │
                                   selected source frame tap
                                                        │
                                  Ollama VLM inference engine
                                                        │
                             Socket.IO update + optional alerts
```

Key design constraints:

- one compute host owns Ollama inference and application state;
- many browser devices may publish camera streams;
- only the currently selected source is analyzed;
- source selection is shared across Situation Room clients;
- a disconnected selected source falls back to the AGX local camera;
- iOS/Safari camera publishing requires a secure HTTPS origin and a top-level publish page;
- remote HTTPS clients may use the same-origin HLS proxy instead of cross-origin WebRTC playback.

## Repository map

| Path | Responsibility |
| --- | --- |
| `src/server.py` | Primary Flask/Socket.IO runtime, APIs, source registry, analysis lifecycle |
| `src/shared/camera.py` | GStreamer capture, camera controls, overlays, RTSP publishing |
| `src/shared/state.py` | Thread-shared application and risk state |
| `src/pipelines/inference.py` | Frame-to-Ollama risk inference orchestration |
| `src/adapters/ollama_client.py` | Ollama model discovery and generation adapter |
| `src/services/` | Prompts, notifications, sound detection, devices, system metrics |
| `static/` | Flask-served HTML, CSS, and browser runtime |
| `mediamtx.yml` | RTSP/HLS/WebRTC server configuration |
| `run.sh` | Canonical preflight, lifecycle, health, and tunnel operator CLI |
| `docker-compose.yml` | Host-network Jetson runtime and device mounts |
| `spec/` | Progressive-disclosure architecture and operations documentation |
| `tests/` | Unit and integration coverage |

Start repository discovery at [`spec/PROJECT_MAP.md`](./spec/PROJECT_MAP.md). It links the relevant architecture, API, runtime, Situation Room, testing, and troubleshooting specifications.

## Development prerequisites

Target runtime:

- Linux on NVIDIA Jetson or a compatible NVIDIA Container Runtime host;
- Docker Engine with Docker Compose;
- NVIDIA Container Runtime;
- Ollama reachable from the host at `http://localhost:11434`;
- V4L2 camera, normally `/dev/video0`;
- optional ALSA/PulseAudio devices under `/dev/snd`;
- MediaMTX binary at `temp/mediamtx`;
- optional ngrok or Tailscale for HTTPS phone/browser access.

The Compose service uses host networking, privileged device access, NVIDIA runtime, and host-mounted source/data/temp paths. Review `docker-compose.yml` before running it outside the intended Jetson environment.

## Bootstrap and lifecycle

Pull at least one Ollama vision model before starting:

```bash
ollama pull bakllava
```

Start with interactive tunnel selection:

```bash
./run.sh up
```

Deterministic startup modes for scripts or CI-like operator flows:

```bash
./run.sh up --no-tunnel
./run.sh up --ngrok
./run.sh up --tailscale
```

Other lifecycle commands:

```bash
./run.sh status
./run.sh logs
./run.sh down_up
./run.sh rebuild
./run.sh down
```

`run.sh` performs Docker, NVIDIA runtime, device, Ollama, container, Flask, RTSP, HLS, and tunnel preflight/health checks. Prefer it over invoking `docker compose` directly when validating the complete stack.

## Service endpoints

Default local endpoints:

| Interface | URL |
| --- | --- |
| WebUI / REST / Socket.IO | `http://localhost:5000` |
| RTSP local camera | `rtsp://localhost:8554/camera` |
| HLS local camera | `http://localhost:8888/camera/index.m3u8` |
| Ollama host API | `http://localhost:11434` |

The backend also exposes a same-origin HLS route at `/proxy/hls/<path>/index.m3u8`. For the complete REST and Socket.IO contract, see [`spec/API.md`](./spec/API.md).

Remote phone access requires the HTTPS `Public UI` emitted by `run.sh`. `Public RTC` is an internal publish/playback base consumed by the frontend, not an operator landing page.

## Mobile WebUI contract

The WebUI is responsive without a frontend build step. Mobile behavior lives in `static/css/style.css` and currently provides:

- a single-column Situation Room at widths up to 600 px;
- compact header metrics and full-width mode controls;
- minimum 44 px interactive targets;
- stacked source metadata with two-column source actions;
- unconstrained document scrolling instead of a nested control-panel scroller;
- iOS safe-area support through `viewport-fit=cover` and `env(safe-area-inset-*)`;
- bottom-sheet role selection and full-width toast feedback;
- visible keyboard focus, tactile press feedback, and coarse-pointer hover safeguards;
- ARIA live status feedback for dynamic notifications;
- reduced-motion behavior for accessibility.

When changing the dashboard, verify at least 390×844 and 360×800 viewports in addition to desktop. Avoid fixed widths, horizontal overflow, and camera controls that depend on hover.

## Configuration and state

Runtime configuration is split between environment variables, JSON state under `data/`, and UI-driven backend state.

Important persisted/runtime artifacts:

- `data/risk_prompt.json`: active risk prompt;
- `data/prompt_history.json`: prompt history;
- `data/public_url_provider.txt`: selected tunnel provider;
- `data/ngrok_url.txt`: cached public UI URL;
- `data/ngrok_webrtc_url.txt`: cached public RTC URL;
- `temp/short_cut.jpg`: most recently analyzed frame;
- `temp/llm.log`: VLM interaction log.

Twilio and webhook configuration is optional. Never commit credentials or generated tunnel URLs.

## Testing

Run the automated suite from the repository root:

```bash
python3 -m pytest
```

Focused mobile contract tests:

```bash
python3 -m pytest tests/unit/test_mobile_webui.py -q
```

Lightweight syntax checks:

```bash
python3 -m py_compile src/server.py src/shared/camera.py src/pipelines/inference.py
bash -n run.sh
```

Runtime validation on the target host:

```bash
./run.sh status
curl -fsSL http://localhost:5000/api/status
curl -fsSL http://localhost:8888/camera/index.m3u8
```

Automated coverage does not replace target-hardware checks for V4L2, GStreamer, MediaMTX, HLS latency, NVIDIA runtime, or Ollama GPU behavior. See [`spec/TESTING.md`](./spec/TESTING.md) and [`spec/TROUBLESHOOTING.md`](./spec/TROUBLESHOOTING.md).

## Change workflow

1. Read `spec/PROJECT_MAP.md` and the linked domain specs.
2. Confirm the active path is Flask (`src/server.py`) rather than legacy Streamlit code.
3. Add a failing test for behavior changes.
4. Implement the smallest change that passes it.
5. Run the focused tests, then the complete suite.
6. For streaming changes, also verify RTSP, HLS, MediaMTX arguments, and real browser playback.
7. For UI changes, run desktop and phone viewport smoke tests.
8. Update the relevant `spec/` document when architecture, APIs, runtime operations, or durable UI behavior changes.

## Documentation

- [`spec/PROJECT_MAP.md`](./spec/PROJECT_MAP.md): onboarding and ownership map
- [`spec/ARCHITECTURE.md`](./spec/ARCHITECTURE.md): data flow and runtime boundaries
- [`spec/MODULES.md`](./spec/MODULES.md): source ownership
- [`spec/API.md`](./spec/API.md): REST and Socket.IO contract
- [`spec/RUNTIME.md`](./spec/RUNTIME.md): lifecycle, ports, tunnels, logs
- [`spec/SITUATION_ROOM.md`](./spec/SITUATION_ROOM.md): multi-source behavior
- [`spec/TESTING.md`](./spec/TESTING.md): automated and hardware verification
- [`spec/KNOWN_ISSUES.md`](./spec/KNOWN_ISSUES.md): active limitations
- [`spec/TODO.md`](./spec/TODO.md): engineering backlog
