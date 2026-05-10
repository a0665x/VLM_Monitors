# Known Issues

## Summary

This file tracks current runtime caveats in the Flask + Socket.IO + MediaMTX implementation.

## Browser And Role Selection

- Device role is now chosen through a browser-local role gate and persisted in `localStorage` under `llm-monitor-role`.
- If an operator wants to reuse the same browser for a different role, they must switch modes explicitly from the segmented control.
- If browser storage is cleared, the role gate appears again on next load.
- Multiple Situation Room clients now share one backend state, so a remote client can change the monitored source for everyone.

## Camera SRC On iPhone / Safari

- iPhone Camera SRC should use the `Public UI` HTTPS URL from `./run.sh up`, not LAN `http://...:5000`.
- Safari camera permission is more reliable when the MediaMTX publish page opens in a top-level tab/window. The current implementation intentionally avoids relying on an embedded cross-origin iframe for permission prompts.
- `Start Camera Sharing` opens the publish URL in a new tab/window. Popup blocking can break this flow; if it does, allow popups for the UI origin.
- Phone Situation Room playback may use HLS proxy playback instead of direct WebRTC iframe playback.

## ngrok

- `run.sh` merges the user's ngrok config with project tunnel config so that the operator's existing `authtoken` is reused.
- The current ngrok setup expects:
  - UI tunnel -> local `5000`
  - WebRTC/publish tunnel -> local `8889`
- If ngrok auth fails, `run.sh` prints the recent ngrok log tail from `logs/ngrok-ui.log`.

## Source Registry

- A browser entering `Camera SRC` mode no longer auto-registers `Browser SRC`.
- A source appears in Situation Room only after the operator starts sharing and the browser begins source registration / heartbeat.
- Remote sources are marked offline after heartbeat timeout and the selected source falls back to `AGX Local Camera`.
- Remote source analysis can still fail transiently if playback is visible but the backend selected-source frame tap has not produced a frame yet.

## Testing Gaps

- There is still no end-to-end automated browser test for:
  - ngrok HTTPS camera sharing
  - iPhone/Safari permission flow
  - multi-source tile lifecycle
- These paths still require manual hardware verification.
