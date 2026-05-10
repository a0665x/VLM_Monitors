# Turn Your Old Phones Into Security Cameras

Turn old phones, backup phones, and tablets into live monitoring cameras, then use one compute-capable Linux host to collect feeds, switch sources, run local VLM risk analysis, and send alerts only when something actually matters.

![VLM_Monitors demo](./demo.png)

This project is built around a very specific practical need:

- stop wasting old phones and use them as `Camera SRC` publishers
- centralize multiple phone feeds inside one shared `Situation Room`
- run Ollama VLM on only one compute-capable service host
- switch analysis between sources in real time
- keep the system local-first instead of sending video to a cloud service

The current production runtime is Flask + Socket.IO + MediaMTX + Ollama. The main entrypoint is `src/server.py`, not the older Streamlit path.

## Agent Onboarding First

This repository includes a shareable onboarding skill:

- [`skills/project-spec-onboarding/SKILL.md`](./skills/project-spec-onboarding/SKILL.md)

If you are new to this project, or want an agent to understand it quickly, use this skill first and start from `./spec/PROJECT_MAP.md` instead of blindly scanning the whole codebase.

Example prompt:

```text
Please use $project-spec-onboarding to initialize understanding of this repository. Start from ./spec/PROJECT_MAP.md, then summarize the current architecture, runtime flow, and which docs/files should be read first before making changes.
```

English example:

```text
Use $project-spec-onboarding to initialize understanding of this repository. Start from ./spec/PROJECT_MAP.md, then summarize the current architecture, runtime flow, and which docs/files should be read first before making changes.
```

## What You Get

- `Situation Room`: one shared dashboard for multiple phone/browser feeds
- `Camera SRC`: a phone can become a camera publisher through an HTTPS page
- local Ollama VLM: analyze only the currently selected source instead of burning compute on every feed
- remote HTTPS access: choose `ngrok` or `Tailscale`
- optional alerts: SMS / webhook
- Optional sound detection

## Architecture

```text
local / phone camera
  -> Camera SRC browser publish
  -> MediaMTX
  -> shared Situation Room grid
  -> selected source only
  -> Ollama VLM analysis
  -> UI updates / alerts

service host local camera
  -> GStreamer capture
  -> CameraThread
  -> FFmpeg RTSP publish
  -> MediaMTX
  -> RTSP / HLS / WebRTC
```

## Prerequisites

Required:

- one Linux service host with enough compute to run local vision models
- Docker
- Docker Compose
- NVIDIA container runtime configured for Docker on the currently tested path
- Ollama installed on the host and reachable at `http://localhost:11434`
- USB camera available at `/dev/video0`
- `temp/mediamtx` present and executable

Optional:

- `ngrok`: simple HTTPS tunnel for phone access
- `Tailscale`: better long-running remote-access path
- Twilio credentials: only needed for SMS alerts
- webhook endpoint: only needed for webhook alerts

## Ollama Setup

Start Ollama on the host:

```bash
ollama serve
```

Recommended first model:

```bash
ollama pull bakllava
```

Other usable vision model suggestions:

- `bakllava`
- `minicpm-v:8b`
- `llama3.2-vision:11b`
- `qwen3-vl:8b`

## Tunnel Setup

`run.sh` now supports two HTTPS paths for phone / remote browser usage:

- `ngrok`
- `Tailscale`

When you run `./run.sh up` or `./run.sh down_up`, the script can prompt you to choose one with left/right arrow keys.

### ngrok

Install and authenticate once:

```bash
ngrok config add-authtoken <YOUR_NGROK_AUTHTOKEN>
```

The script will create:

- `Public UI`: HTTPS browser UI
- `Public RTC`: HTTPS MediaMTX publish/playback base

### Tailscale

Typical setup:

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

If operator permission is missing, `run.sh` can now detect that and ask whether it should run the required `sudo tailscale set --operator=...` and `sudo tailscale funnel ...` commands for you.

## Quick Start

`./run.sh up` already performs preflight checks. If Docker, Ollama, MediaMTX, camera devices, NVIDIA runtime, ngrok, or Tailscale prerequisites are missing, it stops early and prints what to install or verify.

Start the full stack:

```bash
./run.sh up
```

Restart cleanly:

```bash
./run.sh down_up
```

Force a tunnel mode without using the arrow-key prompt:

```bash
./run.sh up --ngrok
./run.sh up --tailscale
./run.sh up --no-tunnel
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

- use the HTTPS `Public UI` printed by `./run.sh up`
- do not manually browse to `Public RTC`

## How To Use

### Service Host

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
4. Be aware that source selection affects the same backend state as the service host

## Docs

Read these first:

- [`spec/PROJECT_MAP.md`](./spec/PROJECT_MAP.md)
- [`spec/ARCHITECTURE.md`](./spec/ARCHITECTURE.md)
- [`spec/RUNTIME.md`](./spec/RUNTIME.md)
- [`spec/SITUATION_ROOM.md`](./spec/SITUATION_ROOM.md)
- [`spec/TROUBLESHOOTING.md`](./spec/TROUBLESHOOTING.md)
- [`spec/TODO.md`](./spec/TODO.md)
