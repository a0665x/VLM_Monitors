# LLM Monitor v2

LLM Monitor v2 is a Jetson-focused, local-first video monitoring system with:

- AGX local camera capture
- browser-based `Camera SRC` publishing from phones or laptops
- shared `Situation Room` monitoring UI
- local Ollama VLM risk analysis
- optional sound detection
- optional Twilio SMS and webhook alerts

The current production runtime is Flask + Socket.IO on port `5000`, with MediaMTX for RTSP/HLS/WebRTC and Ollama running on the host.

## Current Highlights

- Shared `Situation Room`: multiple clients can open the monitoring dashboard and operate the same backend state.
- `Camera SRC`: phones can publish camera streams into the AGX-hosted monitoring session.
- HTTPS-friendly remote viewing: phone `Situation Room` playback can use same-origin HLS proxy playback to avoid ngrok/WebRTC iframe issues.
- Local-first AI: video stays local to the AGX host; inference runs through local Ollama vision models.

## Architecture

```text
AGX local camera (/dev/video0)
  -> GStreamer capture
  -> CameraThread
  -> FFmpeg RTSP publish
  -> MediaMTX
  -> RTSP / HLS / WebRTC

browser Camera SRC
  -> HTTPS UI
  -> Start Camera Sharing
  -> MediaMTX publish page
  -> remote source registered in backend

selected source
  -> AnalysisThread
  -> InferenceEngine
  -> Ollama VLM
  -> status updates / alerts
```

## Prerequisites

Required:

- Linux host, ideally NVIDIA Jetson AGX / Orin class device
- Docker
- Docker Compose
- NVIDIA container runtime configured for Docker
- Ollama installed on the host and reachable at `http://localhost:11434`
- USB camera available at `/dev/video0`
- `temp/mediamtx` present and executable

Optional:

- ngrok: recommended when phones need to use `Camera SRC` over HTTPS
- Twilio credentials: only needed for SMS alerts
- webhook endpoint: only needed for webhook alerts

## Required Host Checks

Before starting, confirm these work on the host:

```bash
docker --version
docker compose version
curl -fsSL http://localhost:11434/api/tags
test -x temp/mediamtx
test -e /dev/video0
```

If you use NVIDIA runtime:

```bash
docker info --format '{{json .Runtimes}}'
```

You should see `nvidia` in the runtime list.

## Ollama Setup

Start Ollama on the host:

```bash
ollama serve
```

Pull at least one vision model, for example:

```bash
ollama pull qwen3-vl:8b
```

Other usable vision model examples:

- `llama3.2-vision:11b`
- `minicpm-v:8b`

## ngrok Setup

`ngrok` is optional for same-network desktop use, but strongly recommended for phone `Camera SRC`.

Install ngrok and log in once:

```bash
ngrok config add-authtoken <YOUR_NGROK_AUTHTOKEN>
```

When `ngrok` is installed, `./run.sh up` will try to create:

- `Public UI`: HTTPS browser UI
- `Public RTC`: HTTPS MediaMTX publish/playback base

Phones should use the HTTPS `Public UI`, not LAN `http://...:5000`.

## Quick Start

Start the full stack:

```bash
./run.sh up
```

Restart from clean Compose state:

```bash
./run.sh restart
```

Shortcut alias for down then up:

```bash
./run.sh down_up
```

Check runtime health:

```bash
./run.sh status
```

Follow logs:

```bash
./run.sh logs
```

Stop:

```bash
./run.sh down
```

## URLs

Local:

- UI: `http://localhost:5000`
- RTSP: `rtsp://localhost:8554/camera`
- HLS: `http://localhost:8888/camera/index.m3u8`

Remote / phone:

- use the `Public UI` printed by `./run.sh up`
- do not manually browse to `Public RTC`

## How To Use

### AGX Host

1. Open `http://localhost:5000`
2. Enter `Situation Room`
3. Wait for local and remote source tiles to appear
4. Choose which source to monitor
5. Use `Analyze Once` or `Auto Analysis`

### Phone As Camera SRC

1. Open the HTTPS `Public UI`
2. Enter `Camera SRC`
3. Fill in source name / source id
4. Press `Start Camera Sharing`
5. Grant camera permission
6. Start publishing from the opened publisher page

### Phone As Shared Situation Room Client

1. Open the HTTPS `Public UI`
2. Enter `Situation Room`
3. View the shared dashboard
4. Be aware that source selection affects the same backend state as the AGX host

## Alerts

Optional alert features:

- Twilio SMS
- webhook integration

By default, SMS and webhook toggles are off. Configure them in the UI before enabling.

## Important Operational Notes

- `Camera SRC` on phones should use HTTPS.
- Shared `Situation Room` means multiple clients can control the same monitored source.
- Remote playback and remote analysis are related but not identical paths; a tile can appear before the selected-source analysis tap has fully warmed up.
- If model selection changes, the UI should reflect the configured model immediately, while completed results still depend on the next inference cycle.

## Repository Hygiene Before Publishing

This project contains local-only files and sensitive config examples. Before pushing to GitHub, review:

- `twilio_config.ini`
- `twilio_config.txt`
- `data/ngrok_url.txt`
- `data/ngrok_webrtc_url.txt`

These should not be committed with real credentials or machine-specific URLs.

## Documentation

Read project docs in this order:

1. [spec/PROJECT_MAP.md](./spec/PROJECT_MAP.md)
2. [spec/ARCHITECTURE.md](./spec/ARCHITECTURE.md)
3. [spec/RUNTIME.md](./spec/RUNTIME.md)
4. [spec/API.md](./spec/API.md)
5. [spec/SITUATION_ROOM.md](./spec/SITUATION_ROOM.md)
6. [troubleshooting.md](./troubleshooting.md)
7. [ToDoList.md](./ToDoList.md)
8. [specs/FAQ.md](./specs/FAQ.md)

## Current Limitations

- End-to-end phone browser behavior still requires manual testing.
- Remote source frame tap is still based on OpenCV RTSP capture; a GStreamer replacement is planned.
- Older Streamlit-oriented files still exist in the repository but are not the current primary runtime.

## License

Add a top-level `LICENSE` file before publishing broadly on GitHub. Also review any bundled third-party binaries or packaging artifacts separately before redistribution.
