# VLM_Monitors To Do List

## High Priority

- Replace the selected remote source OpenCV RTSP tap with a GStreamer-based capture path for better Jetson stability and lower frame-acquisition latency.
- Separate `current configured model`, `currently running model`, and `last completed inference model` in the UI so model transitions are unambiguous.
- Split the combined risk indicator into explicit `Vision Risk` and `Sound Risk` states.
- Add stronger source health signals than browser heartbeat alone, ideally including backend stream-open success and recent frame timestamps.

## Situation Room And Phone UX

- Add a Safari/iPhone specific playback strategy matrix and choose the most stable default automatically.
- Reduce or remove the need for ngrok interstitial-sensitive flows where possible.
- Add clearer in-UI labels distinguishing:
  - shared Situation Room controller
  - camera publishing client
  - source currently selected for analysis

## GStreamer Work

- Prototype a remote-source frame tap using GStreamer instead of OpenCV `VideoCapture`.
- Benchmark end-to-end latency for:
  - AGX local camera playback
  - remote browser Camera SRC playback
  - remote browser source analysis
- Investigate whether HLS proxy playback on phones should stay permanent or become a fallback only.
- Review whether the local camera pipeline can reduce conversion overhead or use more Jetson-friendly memory flow.

## Testing

- Add automated tests for `/api/analysis/config` model-switch behavior.
- Add coverage for shared Situation Room semantics with multiple clients.
- Add integration checks for source selection, source fallback, and delayed first-frame analysis.
- Add smoke checks for `/proxy/hls/<path>` routing.

## Documentation

- Keep `spec/` aligned with the actual shared Situation Room design.
- Add a concise operator troubleshooting flowchart after the runtime stabilizes.
- Review older root docs for stale Streamlit language and outdated networking assumptions.
