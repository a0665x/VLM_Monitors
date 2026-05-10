# API

## Summary

The current API is implemented in `src/server.py` with Flask and Flask-SocketIO. The frontend under `static/` uses these endpoints for status, metrics, analysis control, source registry, mode switching, device switching, prompt updates, and live events.

## REST Endpoints

### UI

- `GET /`: serves `static/index.html`.
- `GET /proxy/hls/<path>`: proxies MediaMTX HLS assets through the UI origin for remote HTTPS clients.

### Status And Metrics

- `GET /api/status`: current risk, sound risk, score, explanation, auto-analysis state, consecutive count, and timestamp.
- `GET /api/metrics`: CPU/RAM/GPU metrics from `SystemMonitor`.
- `GET /api/public-urls`: current cached ngrok UI / WebRTC public URLs, if available.

Additional status fields now include:

- `source_id`
- `source_label`
- `scoring_model`
- `ui_mode`
- `situation_room_client_id`
- `enable_sms`
- `enable_webhook`
- `webhook_url`

### Analysis

- `POST /api/analysis/trigger`: starts one background analysis run.
- `POST /api/analysis/auto`: enable/disable automatic analysis with JSON `{ "enabled": true|false }`.
- `POST /api/analysis/config`: update model, interval, or consecutive-risk threshold.

Recognized fields:

```json
{
  "model": "qwen3-vl:8b",
  "interval": 5,
  "threshold": 3,
  "show_inference_overlay": true
}
```

### Notifications

- `POST /api/config/twilio`: configure Twilio SID/token/from/to/custom message/cooldown.
- `POST /api/config/notifications`: toggle SMS/webhook and set `webhook_url`.

### Devices

- `GET /api/devices/video`: available video devices and current device.
- `GET /api/devices/audio`: available audio devices and current device.
- `POST /api/devices/switch`: switch video/audio devices and restart relevant threads.

Payload shape:

```json
{
  "video_device": "/dev/video0",
  "audio_device": "default",
  "enable_audio": false
}
```

### Sources And Modes

- `GET /api/sources`: list known sources and selected source id.
- `POST /api/sources/register`: register or update a remote browser source.
- `POST /api/sources/heartbeat`: keep a remote source online.
- `POST /api/sources/select`: choose the single source used for VLM analysis.
- `POST /api/sources/disconnect`: remove a remote source tile; if selected, fallback to `AGX Local Camera`.
- `POST /api/mode`: switch a browser between `situation` and `camera`.

`POST /api/mode` payload:

```json
{
  "mode": "camera",
  "client_id": "client-abc123",
  "source_id": "phone-a",
  "label": "Phone A",
  "register_source": false
}
```

Notes:

- Situation Room is now shared across multiple clients
- switching to `camera` no longer auto-registers a browser source unless source registration is explicitly requested elsewhere

### Sound Detection

- `POST /api/sound/toggle`: enable or disable sound detection.

Payload:

```json
{ "enabled": true }
```

### Prompts And Models

- `GET /api/prompt/current`: current risk prompt text/version/timestamp.
- `POST /api/prompt/update`: update risk prompt with JSON `{ "text": "..." }`.
- `GET /api/prompt/history`: prompt history texts.
- `GET /api/models/vision`: available vision models from Ollama, with fallback defaults.

## Socket.IO Events

### Client Events

- `connect`: server emits `connected`.
- `disconnect`: logs disconnect.
- `request_status`: server emits current `status_update`.

### Server Events

- `connected`: basic connection acknowledgement.
- `status_update`: risk, score, explanation, sound fields, timestamp.
- `metrics_update`: periodic system metrics every 2 seconds.
- `sources_update`: source registry and selected source id.
- `inference_stream`: partial or final inference text for monitored-source overlay display.

## Implementation Notes

- Handlers assume `initialize_backend()` has run and global `app_state`, `prompt_store`, `inference_engine`, and `analysis_thread` are initialized.
- Analysis runs in background threads. Be careful with shared state and locking when adding fields.
- `AnalysisThread` can analyze either the AGX local frame or a selected remote source frame tap.
- Source selection resets visible risk state and can immediately retarget auto-analysis.
