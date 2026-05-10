# Testing

## Summary

The current automated tests are narrow and mainly cover notifier behavior. Camera, HLS, Docker, MediaMTX, and Jetson GPU behavior still need manual verification on the target machine.

## Automated Tests

Run from the project root:

```bash
pytest
```

Focused notifier tests:

```bash
pytest tests/test_notifier.py
```

## Syntax And Import Checks

Useful lightweight checks:

```bash
python -m py_compile src/server.py src/shared/camera.py src/pipelines/inference.py
bash -n run.sh
```

## Manual Runtime Checks

Start:

```bash
./run.sh up
```

Verify:

```bash
docker ps --filter name=llm_monitor
./run.sh status
curl -fsSL http://localhost:5000/api/status
curl -fsSL http://localhost:8888/camera/index.m3u8
docker logs --tail 100 llm_monitor
```

Open:

```text
http://localhost:5000
```

## Hardware Checks

Run on the Jetson or target host:

```bash
v4l2-ctl --list-devices
v4l2-ctl -d /dev/video0 --list-formats-ext
curl -fsSL http://localhost:11434/api/tags
```

Use a physical hand-wave test in front of the camera to validate end-to-end HLS latency.

## Risk Areas

- MediaMTX process may run without `mediamtx.yml`; always verify process args if HLS breaks.
- `hlsAlwaysRemux: yes` is required for reliable browser HLS startup.
- Docker host-network behavior and NVIDIA runtime must be tested on the target machine.
- `src/app.py` Streamlit path is not covered by current Docker runtime checks.
- Notification tests mock Twilio/webhook clients and do not verify real credentials.
