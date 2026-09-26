# Local validation — 2026-09-26

## Host and installed profiles

- Ubuntu 22.04 x86_64, RTX 2080 Ti (11 GB), NVIDIA driver 560.35.03.
- Existing Ollama 0.11.7 system service reused; added `qwen2.5vl:3b` (3.8B total parameters, Q4_K_M).
- Installed isolated vLLM 0.9.2+cu126, PyTorch 2.7.0+cu126, Transformers 4.53.3, XFORMERS 0.0.30.
- Downloaded `Qwen/Qwen2.5-VL-3B-Instruct` weights; FP16 profile successfully initialized on compute capability 7.5.
- MediaMTX 1.21.1; local camera 2560x720 YUY2 @30, software H.264 publishing, automatic exposure.
- Default monitoring service uses Ollama; vLLM is installed and tested but stopped after comparison to release GPU memory.

## Verification

- 31 automated tests passed; one legacy Gradio integration module skipped because Gradio is not part of the headless environment.
- Real camera processing stabilizes around 30 FPS.
- Browser WebRTC preview connected, including after limiting all media listeners to loopback.
- HLS proxy master playlist, variant playlist and actual MP4 segment all returned HTTP 200.
- Fixed an observed MediaMTX session failure by preserving query parameters through the HLS proxy; byte-range forwarding is covered by a regression test.
- Both inference backends completed camera analysis through the monitor API.
- vLLM streaming end-to-end analysis completed in 1628 ms for the current risk prompt; this is a different request from the benchmark below.
- The service is managed by user systemd; user lingering is not enabled, so pre-login / logout-independent operation is not yet configured.
- Tailscale is installed and logged in. Private Serve sharing was not enabled; explicit permission to share this camera/state with the tailnet is pending. No iPhone hardware test was performed.

## Small latency experiment

Four distinct saved camera JPEGs (1024x288) were used by both engines, verified by matching SHA-256 hashes. The prompt asks for one short description, temperature 0, output cap 64 tokens. All numbers are client wall time. No competing Ollama/vLLM model occupied the GPU during the other engine's run.

| Profile | First request | Subsequent three requests | Subsequent median |
| --- | --- | --- | --- |
| Ollama Q4_K_M | 2706 ms | 675, 712, 840 ms | 712 ms |
| vLLM FP16, V0/XFORMERS | 13860 ms | 601, 642, 595 ms | 601 ms |

The first-request conditions differ: Ollama was explicitly unloaded first; vLLM had already loaded its service model but performed its first real image request. These are not directly comparable startup measurements. The vLLM service itself took roughly 46 seconds from process start to listening in this run.

Quantization, internal image preprocessing, generated text/token counts and backend defaults also differ. This small experiment demonstrates working profiles and useful latency ranges; it does not establish a universal framework speedup or detection accuracy. The scene was dark, and answers varied; assess model behavior with more controlled scenes before choosing a model.

Local raw results (ignored by Git):

- `logs/benchmark-ollama-sequence.json`
- `logs/benchmark-vllm-sequence.json`
- `logs/vllm-service-smoke.json`
- `logs/ollama-service-smoke.json`
- `temp/benchmark-frames/`

Use [SERVICE.md](./SERVICE.md) for repeatable commands, backend switching and the iOS API contract.
