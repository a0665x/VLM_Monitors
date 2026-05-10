# Runtime

## Summary

Use this as the quick reference for running, stopping, debugging, and validating LLM Monitor v2. For historical troubleshooting details, read `../specs/FAQ.md`.

## Primary Commands

Start and run layered checks:

```bash
./run.sh up
```

Restart from a clean Compose container state:

```bash
./run.sh restart
```

Explicit down-then-up operator shortcut:

```bash
./run.sh down_up
```

Check Docker, Ollama, container, API, RTSP, HLS, and device API status:

```bash
./run.sh status
```

Rebuild from scratch:

```bash
./run.sh rebuild
```

Follow logs:

```bash
./run.sh logs
```

Stop:

```bash
./run.sh down
```

`run.sh` is the only shell entrypoint kept in the project root.

## URLs And Ports

- Web UI: `http://localhost:5000`
- RTSP stream: `rtsp://localhost:8554/camera`
- HLS stream: `http://localhost:8888/camera/index.m3u8`
- HLS proxy for remote HTTPS UI clients: `/proxy/hls/<path>/index.m3u8`
- Ollama host API: `http://localhost:11434`
- Optional ngrok inspection: `http://localhost:4040/api/tunnels`

The older `http://localhost:8501` Streamlit URL is not the current Docker runtime.

## Docker Runtime

`docker-compose.yml` runs service `llm-monitor` as container `llm_monitor` with:

- fixed image name `llm-monitor:latest`
- `network_mode: host`
- `privileged: true`
- NVIDIA runtime
- `/dev/video0` and `/dev/snd` device mounts
- source, data, and temp volume mounts
- PulseAudio socket/cookie mounts
- healthcheck on `http://localhost:5000/api/status`

Because source is volume-mounted, many Python/static changes are visible without rebuilding, but dependency or image-level changes require rebuild.

## Local Dependencies

- Docker with NVIDIA runtime.
- USB camera, normally `/dev/video0`.
- Ollama already running on host.
- `temp/mediamtx` executable present.
- `mediamtx.yml` configured for RTSP and HLS.
- Optional ngrok installed on host.
- For remote iPhone/Safari Camera SRC, ngrok should be configured with a valid authtoken in the operator's user config.

If NVIDIA runtime is missing, install NVIDIA Container Toolkit and configure Docker before running this project.

## Logs And Artifacts

- Docker logs: `docker compose logs -f`
- App temp log: `temp/app.log`
- LLM inference log: `temp/llm.log`
- Latest analyzed frame: `temp/short_cut.jpg`
- Ngrok public URL cache: `data/ngrok_url.txt`
- Ngrok WebRTC public URL cache: `data/ngrok_webrtc_url.txt`
- Ngrok runtime log: `logs/ngrok-ui.log`
- Prompt data: `data/risk_prompt.json`, `data/prompt_history.json`

## Critical MediaMTX Settings

Keep these aligned with `../specs/FAQ.md`:

```yaml
hls: yes
hlsAddress: :8888
hlsAlwaysRemux: yes
paths:
  camera:
    source: publisher
```

`src/server.py` should start MediaMTX with the config file:

```text
./temp/mediamtx ./mediamtx.yml
```

If HLS returns 404, verify both the config values and the running process arguments.

## Common Verification Commands

```bash
./run.sh status
docker ps --filter name=llm_monitor
docker logs --tail 100 llm_monitor
curl -fsSL http://localhost:5000/api/status
curl -fsSL http://localhost:8888/camera/index.m3u8
ps aux | grep mediamtx
```

Camera and GStreamer checks:

```bash
v4l2-ctl --list-devices
v4l2-ctl -d /dev/video0 --list-formats-ext
gst-launch-1.0 --version
```

Ollama checks:

```bash
curl -fsSL http://localhost:11434/api/tags
```

## Rebuild Guidance

Use:

```bash
./run.sh rebuild
```

Rebuild after dependency, Dockerfile, or image-level system package changes. Restart is usually enough for mounted config and source changes.

## `run.sh` Flow

`./run.sh up` performs these steps:

1. Check project files, Docker, Docker Compose, and Docker daemon.
2. Check NVIDIA runtime.
3. Check host `/dev/video0` and `/dev/snd`.
4. Check Ollama at `http://localhost:11434`.
5. Build/start Docker Compose.
6. Confirm container state and mounted devices.
7. Wait for Flask API.
8. Wait for RTSP TCP port.
9. Wait for HLS manifest.
10. Check video/audio device REST APIs.
11. Start optional ngrok when installed.
12. Print local, LAN, and remote operator URLs plus current role-specific instructions.

## Remote Browser Flow

When ngrok starts successfully, `./run.sh up` prints:

- `Public UI`: HTTPS URL for the browser UI
- `Public RTC`: HTTPS base URL for MediaMTX publish/playback

Recommended usage:

- AGX operator: open `http://localhost:5000`
- iPhone / remote camera device: open `Public UI`
- iPhone then selects `Camera SRC`, fills source id / label, and presses `Start Camera Sharing`

Do not manually open `Public RTC` in the browser; it is a backend URL used by the frontend to build publish/playback pages.

`./run.sh restart` first runs `docker compose down --remove-orphans`, then executes the same startup checks.
`./run.sh down_up` is an alias for the same restart behavior.
