# Runtime

## Summary

Use this as the quick reference for running, stopping, debugging, and validating VLM_Monitors.

## Primary Commands

Start and run layered checks:

```bash
./run.sh up
```

Restart from a clean runtime state:

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
- Optional Tailscale UI when selected: `https://<tailnet-dns-name>`
- Optional Tailscale WebRTC when selected: `https://<tailnet-dns-name>:8443`

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

## Local Dependencies

- Docker with NVIDIA runtime.
- USB camera, normally `/dev/video0`.
- Ollama already running on host.
- `temp/mediamtx` executable present.
- `mediamtx.yml` configured for RTSP, HLS, and WebRTC.
- Optional ngrok installed on host.
- Optional Tailscale installed on host.
- For remote iPhone/Safari Camera SRC, ngrok should be configured with a valid authtoken in the operator user config.
- For remote Tailscale access, `tailscale up` must already have completed successfully.

## Logs And Artifacts

- Docker logs: `docker compose logs -f`
- Ngrok public URL cache: `data/ngrok_url.txt`
- Ngrok WebRTC public URL cache: `data/ngrok_webrtc_url.txt`
- Tunnel provider cache: `data/public_url_provider.txt`
- Ngrok runtime log: `logs/ngrok-ui.log`
- Tailscale UI log: `logs/tailscale-ui.log`
- Tailscale WebRTC log: `logs/tailscale-webrtc.log`
- Prompt data: `data/risk_prompt.json`, `data/prompt_history.json`

## `run.sh` Flow

`./run.sh up` performs these steps:

1. Check project files, Docker, Docker Compose, and Docker daemon.
2. Check NVIDIA runtime.
3. Check host `/dev/video0` and `/dev/snd`.
4. Check Ollama at `http://localhost:11434`.
5. Clean old public URL cache, stop old ngrok processes, and remove leftover `llm_monitor` name conflicts if needed.
6. Build/start Docker Compose.
7. Confirm container state and mounted devices.
8. Wait for Flask API.
9. Wait for RTSP TCP port.
10. Wait for HLS manifest.
11. Check video/audio device REST APIs.
12. Let the operator choose a remote HTTPS tunnel path: `ngrok`, `Tailscale`, or none.
13. Start the selected tunnel path and cache the resulting public URLs.
14. If Tailscale operator permissions are missing, print the exact `sudo` commands and optionally prompt to run them immediately.
15. Print local, LAN, and remote operator URLs plus role-specific instructions.

## Current Startup UX

Current operator-facing behavior:

- Tunnel choice can be selected interactively with left/right arrow keys.
- Tunnel selection can also be forced with `--ngrok`, `--tailscale`, or `--no-tunnel`.
- Startup waits for Flask/HLS/RTSP using a single-line elapsed-seconds progress display instead of repeatedly printing `curl` errors.
- `restart` / `down_up` clean both Docker runtime leftovers and old tunnel state before starting again.

## Remote Browser Flow

When the selected tunnel starts successfully, `./run.sh up` prints:

- `Public UI`: HTTPS URL for the browser UI
- `Public RTC`: HTTPS base URL for MediaMTX publish/playback

Recommended usage:

- service host operator: open `http://localhost:5000`
- remote phone camera device: open `Public UI`
- phone then selects `Camera SRC`, fills source id / label, and presses `Start Camera Sharing`

Do not manually open `Public RTC` in the browser; it is a backend URL used by the frontend to build publish/playback pages.

## Tailscale Permission Recovery

If `tailscale funnel` fails with `serve config denied` or `access denied`, `run.sh` can now:

- explain that operator permission is missing
- print the required commands:
  - `sudo tailscale set --operator=$USER`
  - `sudo tailscale funnel --bg --https=443 http://127.0.0.1:5000`
  - `sudo tailscale funnel --bg --https=8443 http://127.0.0.1:8889`
- ask whether it should run them immediately

If the operator answers no, the script stops and asks for manual completion before retrying.
