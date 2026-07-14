# Situation Room

## Summary

This document describes the current multi-source runtime, not a future plan.

## Current Roles

The browser UI now has two explicit roles:

- `Situation Room`
- `Camera SRC`

Browsers first land on a role gate. The selected role is stored in browser `localStorage` so the same device usually returns to the same role on reload.

## Situation Room

Situation Room is the shared operator dashboard hosted by the service-host backend.

Current rules:

- multiple browsers can open Situation Room at the same time
- these browsers are controlling the same backend state
- clients see the same source grid and Risk Intelligence state
- clients can select exactly one source for VLM analysis
- clients can disconnect remote source tiles manually

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

## Why Publish Opens In A New Tab

For iPhone/Safari, camera permission is unreliable when the publish page is embedded as a cross-origin iframe.

The current implementation therefore opens:

```text
https://<public-webrtc-base>/<source_id>/publish
```

in a top-level tab/window so Safari can prompt for camera access more reliably.

## URLs

Local service-host operator URL:

```text
http://localhost:5000
```

Remote phone Camera SRC URL:

```text
Public UI printed by ./run.sh up
(through either ngrok or Tailscale, depending on the startup tunnel selection)
```

The frontend internally uses the printed `Public RTC` base URL for:

- source tile playback
- Camera SRC publish page

For HTTPS `Situation Room` viewing on phones, the frontend can use same-origin proxied HLS playback to avoid ngrok/WebRTC iframe problems. `run.sh` is now responsible for choosing and printing the correct HTTPS entry path first.

## Mobile Layout Contract

`static/css/style.css` defines a dedicated phone layout at `max-width: 600px`:

- all Situation Room source grids collapse to one column
- header metrics compact without hiding runtime status
- source actions use touch-sized controls with a 44 px minimum target
- the control panel returns to normal document scrolling rather than a nested viewport-height scroller
- the role gate behaves as a bottom sheet
- toasts span the available width above the device safe area and announce updates through an ARIA live region
- keyboard focus remains visible and touch presses receive tactile feedback
- coarse-pointer devices do not inherit hover-only transforms
- `viewport-fit=cover` and `env(safe-area-inset-*)` support notched iOS devices
- `prefers-reduced-motion` disables nonessential animation

Treat 390x844 and 360x800 as the minimum phone smoke-test viewports. Mobile controls must not depend on hover or create horizontal document overflow.

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

- `agx-local`: service host local camera source
- browser-provided source ids such as `phone-a`, `front-door`, `warehouse-2`

## Analysis Routing

Only one source is analyzed at a time.

Rules:

- if selected source is `agx-local`, VLM uses the local `latest_frame`
- if selected source is remote, backend starts a selected-source frame tap from the remote MediaMTX path
- newly selected remote sources may need a short warm-up before the first analysis frame is available
- if selected remote source disappears, backend falls back to `agx-local`

Source switching resets visible risk state so the old source result is not shown on the new source.

## Tunnel-Related Notes

- `ngrok` is simple but can hit request or plan limits during long-running phone sessions.
- `Tailscale` is now supported directly from `run.sh` as another HTTPS path.
- If Tailscale operator permission is missing, `run.sh` can prompt to run the required `sudo` commands for `5000` and `8889`.

## Known Constraints

- Browser role persistence is local to each browser profile.
- Browser pop-up blocking can interfere with opening the publish page.
- End-to-end mobile browser testing is still manual.
- Local LAN HTTP URLs are useful for desktop debugging but are not the preferred phone Camera SRC path.
