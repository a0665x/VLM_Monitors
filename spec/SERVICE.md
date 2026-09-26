# Headless service and iOS direction

## Current scope

The repository now supports a native x86 Linux service in addition to the existing Jetson Docker path. A single Gunicorn worker owns the camera and shared in-memory state. Ollama and vLLM run as separate inference services, chosen at application startup with `VLM_BACKEND`.

```text
USB camera -> GStreamer -> CameraThread -> software H.264 / Jetson encoder
                                             -> MediaMTX
                                             -> Flask HLS proxy -> iOS AVPlayer
Selected source frame -> bounded image size -> Ollama OR vLLM
                                             -> REST / Socket.IO -> iOS client
Private remote access: iPhone Tailscale -> Tailscale Serve HTTPS -> localhost:5000
```

Only one source is analyzed at a time. All clients share selection and analysis settings. The iOS application is a future separate client; it is not implemented here.

## Native x86 installation

Host requirements: Linux x86_64, GStreamer `v4l2src`/`videoconvert`, a readable V4L2 camera, `/usr/bin/python3` (tested with 3.10), and a user systemd session. GPU inference is external to the web service.

```bash
bash scripts/bootstrap-local.sh --vllm
ollama pull qwen2.5vl:3b
# Edit .env to match the camera and chosen model.
./run.sh local-up
./run.sh local-status
./run.sh local-logs
```

- `requirements-service.txt`: web/camera dependencies in `.venv`.
- `requirements-vllm.txt`: separate `.venv-vllm`; compatibility profile for driver 560 / CUDA 12.6 / RTX 2080 Ti.
- `config/local.env.example` -> `.env`: monitor configuration.
- `config/vllm.env.example` -> `.env.vllm`: vLLM process configuration.
- `config/mediamtx.local.yml`: loopback RTSP/HLS/WebRTC listeners.
- `./run.sh local-restart`: apply `.env` changes.
- `./run.sh local-down`: disable and stop the monitor user service.

The unit is installed under `~/.config/systemd/user/vlm-monitor.service` and starts with the user's systemd session. Running through logout / before login requires user lingering (`sudo loginctl enable-linger <user>`); installation does not automatically enable it. Use one worker: multiple workers would compete for the same camera and diverge in state.

The example environment defaults to automatic camera mode discovery; this test host supports 2560x720 YUY2 @30, which is not a universal webcam mode. Explicit width/height bypass `v4l2-ctl` mode discovery. `v4l2-ctl` is optional with explicit dimensions, but needed for automatic discovery and exposure controls. The local profile requests auto exposure with `CAMERA_EXPOSURE_MODE=auto`; the Jetson default remains its existing manual controls. This host uses an Ubuntu v4l-utils package extracted under `temp/v4l-package/root`, which `start-local.sh` adds to PATH when present. `VIDEO_ENCODER=software` uses system FFmpeg or the imageio-ffmpeg binary. The bundled static FFmpeg was observed to crash resolving `localhost`; use numeric `127.0.0.1` for RTSP.

## Inference backends

Ollama profile in `.env`:

```dotenv
VLM_BACKEND=ollama
VLM_MODEL=qwen2.5vl:3b
OLLAMA_BASE_URL=http://127.0.0.1:11434
```

vLLM profile in `.env`:

```dotenv
VLM_BACKEND=vllm
VLM_MODEL=Qwen/Qwen2.5-VL-3B-Instruct
VLLM_BASE_URL=http://127.0.0.1:8000/v1
```

Start vLLM with `./run.sh vllm-up`, wait until `/v1/models` responds, then select vLLM and its model in WebUI Settings. Runtime UI changes do not require restarting the monitor. Stop it with `./run.sh vllm-down`. vLLM is installed as an on-demand user service and is not enabled automatically at login.

The 11 GB GPU should host one active inference engine at a time. Before loading vLLM, stop analysis and unload any Ollama models used by this experiment (`ollama stop qwen2.5vl:3b`). Before returning to Ollama, stop the vLLM service. Installing both frameworks does not mean both large models fit simultaneously.

The current vLLM profile uses FP16, V0 + XFORMERS, eager execution, one concurrent sequence, 2048 context tokens and a bounded image pixel count for Turing compatibility. It is an explicit legacy compatibility profile, not a claim that the newest vLLM release has been tested. CUDA/driver upgrades can be evaluated separately.

Both adapters accept `VLM_MAX_TOKENS`, `VLM_TEMPERATURE`, and `VLM_TIMEOUT`. `VLM_FRAME_MAX_EDGE` limits the analyzed JPEG size independently of playback. `0` preserves the full frame. Small inputs improve speed but may remove details relevant to detection.

## iOS client contract

Use one base URL. On the host it is `http://127.0.0.1:5000`; after private Serve setup it is the host's `https://<machine>.<tailnet>.ts.net` URL.

| Purpose | API |
| --- | --- |
| Discover service/backend | `GET /api/service` |
| Sources and selected id | `GET /api/sources` |
| Native AVPlayer playback | Resolve each source `hls_proxy_path` against the base URL |
| Latest inference/state | `GET /api/status` |
| One-shot analysis | `POST /api/analysis/trigger` |
| Auto-analysis | `POST /api/analysis/auto` with `{"enabled":true}` |
| Model/interval/threshold | `POST /api/analysis/config` |
| Real-time updates | Socket.IO at `/socket.io`, events in `API.md` |

Socket.IO is not a plain WebSocket protocol. A first iOS prototype can poll REST and play HLS with AVPlayer; later use a compatible Socket.IO client. Resolve relative HLS paths against the service URL, never the internal `localhost` URLs also present in legacy source fields.

Viewing needs only the UI/HLS proxy origin. Publishing an iPhone camera is a separate capability requiring a WebRTC publisher and its network path; the native iOS publisher is not implemented by this change.

## Private cross-network access

The host and iPhone join the same Tailscale tailnet. Serve provides HTTPS and tailnet access controls across different Wi-Fi/mobile networks. No public Funnel is required for this design.

```bash
# Explicitly share the monitoring service with authorized tailnet devices:
./run.sh local-tailnet
# Inspect:
tailscale serve status
```

`local-tailnet` uses `tailscale serve --bg --https=443 http://127.0.0.1:5000`. It is a separate opt-in action from local startup. Tailnet HTTPS may need account-owner enablement, and the local command may require `sudo` or a configured Tailscale operator. Review the existing Serve configuration before changing it.

The current application has no per-user application authorization. The native profile listens on loopback and relies on the private access boundary. A public App Store service for arbitrary users would additionally need application identity, authorization, session/token lifecycle, and suitable video delivery. Those are future work, not features already implemented.

## Performance experiments

```bash
VLM_BACKEND=ollama VLM_MODEL=qwen2.5vl:3b VLM_MAX_TOKENS=64 \
  .venv/bin/python scripts/benchmark_vlm.py temp/benchmark.jpg --output logs/benchmark-ollama.json
VLM_BACKEND=vllm VLM_MODEL=Qwen/Qwen2.5-VL-3B-Instruct VLM_MAX_TOKENS=64 \
  .venv/bin/python scripts/benchmark_vlm.py temp/benchmark.jpg --output logs/benchmark-vllm.json
```

The script accepts either one JPEG or a directory containing at least four JPEGs. It records a first request plus three subsequent requests, output text and per-frame SHA-256. A directory tests the same saved sequence across engines without repeating an identical frame. Repeated identical images may hit prompt/image caches; these results are not a changing-video FPS measurement. Ollama's quantized weights and vLLM's FP16 weights are not an identical numerical model. Compare quality, first-result latency and steady-state behavior as separate outcomes.

## References

- [vLLM CUDA installation](https://docs.vllm.ai/en/v0.9.2/getting_started/installation/gpu.html)
- [Qwen2.5-VL on Ollama](https://ollama.com/library/qwen2.5vl)
- [Tailscale Serve](https://tailscale.com/docs/features/tailscale-serve)
