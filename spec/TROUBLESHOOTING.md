# VLM_Monitors Troubleshooting

## Purpose

This file captures practical troubleshooting notes from recent fixes so operators and future agents do not repeat the same debugging cycle.

## Recent Fixes To Remember

- Situation Room is now a shared backend dashboard. Multiple browsers can enter `Situation Room`, but they all control the same AGX-hosted monitoring state.
- Phone `Camera SRC` should use the HTTPS `Public UI` URL, not LAN `http://...:5000`.
- HTTPS `Situation Room` playback now prefers same-origin HLS proxy playback instead of cross-origin WebRTC iframes, to avoid ngrok interstitial loops on phones.
- Remote source selection now tolerates delayed heartbeats better. A source can still be selected even if the browser timer was throttled.
- Remote source analysis waits briefly for the first tapped frame before surfacing `No frame available yet`.
- The UI now separates `selected scoring model` from `last inference model` semantics. The model shown in the panel should reflect current configuration immediately.

## Common Failure Modes

### Phone Can Publish But AGX Cannot Analyze The Source

Symptoms:

- source tile appears
- tile video plays
- `Auto Analysis` reports `No frame available yet for <source>`

Checks:

- confirm the source is selected with the green monitored state
- wait a few seconds after source selection before judging the result
- inspect whether backend can open the selected remote RTSP path
- if this remains flaky, consider replacing the current OpenCV RTSP tap with a GStreamer-based remote frame tap

Likely cause:

- remote playback and remote frame capture are separate paths; the browser can show video before the analysis tap has delivered the first frame

### Phone Situation Room Shows White Screen Or ngrok Warning Loop

Symptoms:

- phone enters `Situation Room`
- video area is white
- user sees `you are about to visit ... ngrok app`

Checks:

- confirm the phone opened the HTTPS `Public UI`
- confirm HLS proxy route `/proxy/hls/...` is reachable from the UI origin
- verify MediaMTX HLS is healthy at `http://localhost:8888/<path>/index.m3u8` on AGX

Likely cause:

- cross-origin WebRTC iframe playback on phone is less reliable than same-origin proxied playback

### Model Dropdown Changes But Monitoring Looks Unchanged

Symptoms:

- model dropdown changes
- prior inference result remains visible
- users assume the old model is still active

Checks:

- distinguish `current configured model` from `last completed inference model`
- trigger a new analysis run if auto analysis is off
- if auto analysis is on, allow the next run to complete before judging the new model's output

Likely cause:

- old inference results remain visible until a new run finishes
- Ollama requests already in flight are not forcibly canceled by this app

### Auto Analysis Turned Off But Status Still Looks Active

Symptoms:

- auto analysis toggle is off
- UI still appears risky or active

Checks:

- verify whether `Sound Detection` is still enabled
- confirm whether the panel is showing the last completed explanation rather than a new active run

Likely cause:

- sound risk and vision risk share the same high-level risk display

## Operational Reminders

- For phone camera sharing, HTTPS is mandatory in practice.
- Browser heartbeat timers on phones are not perfectly reliable, especially after app switching or tab backgrounding.
- If changing MediaMTX, HLS, or capture logic, review `../specs/FAQ.md` and `TROUBLESHOOTING.md` before refactoring.
- If playback works but analysis fails, debug the selected-source tap path, not only the UI.

## When To Escalate To Deeper Engineering

- repeated remote source analysis failures despite stable playback
- model changes appear configured but completed inference logs show the wrong model
- phone `Situation Room` works on desktop but fails consistently on Safari/iPhone
- AGX local camera disappears only when another client joins shared Situation Room
