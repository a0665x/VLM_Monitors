# Situation Room

## Summary

This document describes the current multi-source runtime, not a future plan.

## Current Roles

The browser UI now has two explicit roles:

- `Situation Room`
- `Camera SRC`

Browsers first land on a role gate. The selected role is stored in browser `localStorage` so the same device usually returns to the same role on reload.

## Situation Room

Situation Room is the shared operator dashboard hosted by the AGX backend.

Current rules:

- multiple browsers can open Situation Room at the same time
- these browsers are controlling the same backend state
- clients see the same source grid and Risk Intelligence state
- clients can select exactly one source for VLM analysis
- clients can disconnect remote source tiles manually

Grid behavior:

- `1` source -> single tile
- `2` sources -> two tiles
- `3-4` sources -> `2x2`
- `5+` sources -> `3x3`

Per-tile behavior:

- selected source -> green border + `MONITORED`
- selected source action button -> `Monitoring`
- selected source with risk -> red flashing border
- offline source -> dimmed
- remote source -> `Disconnect` button

## Camera SRC

Camera SRC is for browser-based camera publishing only.

Current flow:

1. operator selects `Camera SRC`
2. browser stays idle; it does not auto-register a source just by entering the role
3. operator fills `source id` and `label`
4. operator presses `Start Camera Sharing`
5. frontend registers the source, starts heartbeat, and opens the MediaMTX publish page in a new tab/window
6. operator grants camera permission there and starts publishing

This split is intentional. It avoids unwanted `Browser SRC` tiles appearing just because a browser opened the UI.

## Why Publish Opens In A New Tab

For iPhone/Safari, camera permission is unreliable when the publish page is embedded as a cross-origin iframe.

The current implementation therefore opens:

```text
https://<public-webrtc-base>/<source_id>/publish
```

in a top-level tab/window so Safari can prompt for camera access more reliably.

## URLs

Local AGX operator URL:

```text
http://localhost:5000
```

Remote iPhone Camera SRC URL:

```text
Public UI printed by ./run.sh up
```

The frontend internally uses the printed `Public RTC` base URL for:

- source tile playback
- Camera SRC publish page

For HTTPS `Situation Room` viewing on phones, the frontend can use same-origin proxied HLS playback to avoid ngrok/WebRTC iframe problems.

## Source Registry

Backend source registry fields currently include:

- `id`
- `label`
- `kind`
- `status`
- `is_local`
- `last_seen`
- `rtsp_url`
- `webrtc_url`
- `publish_url`
- `hls_url`

Current important IDs:

- `agx-local`: AGX host local camera source
- browser-provided source ids such as `phone-a`, `front-door`, `warehouse-2`

## Analysis Routing

Only one source is analyzed at a time.

Rules:

- if selected source is `agx-local`, VLM uses the AGX local `latest_frame`
- if selected source is remote, backend starts a selected-source frame tap from the remote MediaMTX path
- newly selected remote sources may need a short warm-up before the first analysis frame is available
- if selected remote source disappears, backend falls back to `agx-local`

Source switching resets visible risk state so the old source result is not shown on the new source.

## Known Constraints

- Browser role persistence is local to each browser profile.
- Browser pop-up blocking can interfere with opening the publish page.
- End-to-end mobile browser testing is still manual.
- Local LAN HTTP URLs are useful for desktop debugging but are not the preferred iPhone Camera SRC path.
