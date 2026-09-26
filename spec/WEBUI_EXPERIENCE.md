# Portable installation and monitoring workspace

## Entry points

Run `./run.sh` in an interactive Linux terminal to select x86_64 or aarch64 installation, start/restart/status, optional vLLM, or Tailscale sharing. Noninteractive invocations without arguments print help. Existing Docker commands remain available for legacy deployments.

`./run.sh setup --arch x86_64 --dry-run` and `--arch aarch64 --dry-run` preview the install plan without modifying the machine. Actual installation rejects an architecture mismatch. Debian/Ubuntu prerequisites are installed via sudo when missing. Existing `.env` files are preserved. New installs use automatic camera mode detection and software H264; explicit camera dimensions can be set in `.env`.

The installer uses architecture-specific MediaMTX 1.21.1 and the [official Ollama Linux installer](https://docs.ollama.com/linux), reuses an existing Ollama installation, and pulls `qwen2.5vl:3b` (override with `INSTALL_OLLAMA_MODEL`). ARM64 is a general Linux path, not a Jetson-only path. Physical ARM hardware was not available for validation.

The optional pinned vLLM profile targets x86 NVIDIA CUDA 12.6, tested on this RTX 2080 Ti. Other hardware requires an appropriate [vLLM installation](https://docs.vllm.ai/en/stable/getting_started/installation/) and `VLLM_BASE_URL`. ARM installation of this x86 wheel is explicitly rejected. The install menu does not configure NVIDIA drivers or pretend all ARM devices use JetPack.

## Main workflow

1. Open the monitoring workspace. Live camera stays visible.
2. Select person, baby distress, fire, smoke, pet, or custom criteria. Selecting a preset immediately persists its prompt through the existing prompt API; it does not start monitoring automatically.
3. Edit the prompt if needed and press Apply. Unsaved edits are labeled. Baby distress is visual only; the separate audio feature is an amplitude trigger, not a crying classifier.
4. Analyze once or start/pause continuous monitoring. The interval is the wait after each inference completes.
5. Results distinguish waiting, running, error, target detected, and no target detected. The old binary score is no longer presented as a confidence probability.

Settings contain the engine/model, analysis interval, consecutive-trigger threshold, overlay, notification and camera/audio controls. Native dialogs support Escape and focus handling. Phone layout stacks controls and camera with two-column scenario cards.

## Engine API

- `GET /api/settings/engine?backend=ollama|vllm`: readiness, models, active backend/model.
- `POST /api/settings/engine`: `{ "backend": "ollama", "model": "qwen2.5vl:3b" }`.
- Invalid request: 400. Inference in flight: 409. Unavailable engine/model: 503; old client/settings remain active.
- Successful changes replace the inference client under the inference lock and atomically persist `temp/engine-settings.json`. Saved engine settings override `.env` defaults on startup. Deleting that settings file restores environment defaults.
- Engine selection connects to an already running server. It does not start arbitrary processes or download models from the web request. With limited GPU memory, stop/unload the other engine before starting vLLM.

## Private mobile viewing

`GET /api/share` reads local Tailscale status and Serve configuration, with bounded subprocess timeouts. It returns a share URL only when HTTPS port 443 routes `/` to this service's loopback port and Funnel is not enabled. `GET /api/share/qr.svg` generates the QR locally; no camera or URL is sent to a third-party QR service. Inactive sharing returns 409 for QR.

The operator enables sharing with `./run.sh local-tailnet` or the installation menu. Mobile devices need membership and access to the same Tailnet. HTTPS viewing uses the existing same-origin HLS proxy. This is a shared control workspace, not per-user authentication or a read-only viewer.

## Validation

36 tests passed, 1 legacy Gradio test module skipped. Tests cover atomic engine settings, busy/unavailable behavior, matching/private Serve routes, SVG QR generation, and existing API/playback regressions. Browser tests cover preset application and live Ollama analysis (about 2.9 seconds in this run); vLLM unavailable state disables Apply. x86/ARM64 installer plans and shell/JavaScript syntax checked. Full clean-machine/physical ARM installation and a remote iPhone scan require those devices and active Tailscale Serve.

Final browser pass also verified start/pause, saved Ollama settings after service restart, and a 390 px viewport with no horizontal overflow. Sharing remains inactive pending explicit permission; no remote scan has been claimed.

新版手機掃碼與相機網路參見 [CLIENT_NETWORK.md](CLIENT_NETWORK.md)。QR 現在指向 `/join`，本機 Tailscale Serve 已由使用者啟用。

## Sidebar and languages (2026-09-26)

- Host navigation: **Monitor**, **Connect phones**, **Settings**, with hash links; bottom navigation on narrow screens.
- Settings owns the runtime Ollama/vLLM engine and model selector. Apply verifies availability, saves the selection, and affects subsequent inference without a service restart. An unavailable engine cannot be applied. Engine processes must already be running.
- Display languages: English (default), Traditional Chinese, Japanese, Korean. Stored per browser/origin as `vlm-language`; language changes also synchronize same-origin tabs.
- Host and `/join` share `locales.js` and `i18n.js`. User prompts, source names, model identifiers and raw model output are preserved. Switching language does not restart camera publishing.
- Static text is annotated once and dynamic status text uses `i18n.text`. Translation uses text nodes, never HTML from model output.
- Browser checks: all four locales, runtime Ollama apply, unavailable vLLM, desktop and 390px mobile layouts. Real iOS testing remains separate from browser viewport checks.
