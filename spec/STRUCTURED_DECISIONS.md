# Structured monitoring decisions — feasibility and proposed integration

Date: 2026-09-26. Status: experimental `parallel_decision` mode implemented; opt-in, not enabled by default. The design alternatives below are historical context; see the implemented-mode section for the current contract.

## Verified upstream facts

- TypeSafe Jev accepts text/JSON state, not images, audio or video: https://docs.typesafe.ai/concepts/state
- TypeSafe RLCD means Reinforcement Learning for Calibrated Decisions. Its training and architecture must not be equated with an inference-only community implementation: https://typesafe.ai/blog/introducing-system-one-models-and-jev
- `harshatheg/Qwen-2.5-1B-RLCD` contains inference code, not a standalone new 1B vision checkpoint. Its README benchmarks Qwen2.5-1.5B-Instruct 4-bit with MLX on M4 Max. The published 5.6–7x claim is author-reported structured-text performance, not camera-to-result performance: https://huggingface.co/harshatheg/Qwen-2.5-1B-RLCD
- Current source also has PyTorch CUDA/CPU support and defaults to `Qwen/Qwen2.5-1.5B-Instruct`: https://huggingface.co/harshatheg/Qwen-2.5-1B-RLCD/blob/main/core/engine_torch.py
- Source inspection: CUDA path performs prefix prefill and batched suffix evaluation, copies/repeats the KV cache, and normalizes candidate logits with softmax. The returned `sequential_forward_passes: 1` omits the separate prefill. `has_collisions` is computed but not resolved in the displayed CUDA scoring loop; test shared-prefix/multiple-token candidates before accepting arbitrary enums. Normalized scores alone are not evidence of empirical calibration.
- Ollama supports JSON Schema via `format`, including vision models: https://docs.ollama.com/capabilities/structured-outputs
- Installed vLLM 0.9.2 documents `guided_json`; ordinary structured outputs are not the community parallel-field algorithm: https://docs.vllm.ai/en/v0.9.2/features/structured_outputs.html

## Existing local contract

`src/pipelines/inference.py` sends one frame and one criterion, requests YES/NO plus explanation, and reduces the result to a single boolean. Its confidence is currently 1.0/0.0 derived from that boolean, not a calibrated probability. Both adapters accept image bytes. The runtime engine selector chooses Ollama or vLLM and expects a vision model.

Do not add the HF repository ID as a selectable vision model. A text-only classifier needs a separate decision-stage adapter.

## Proposed modes and settings

Keep serving engine and analysis mode separate:

1. `direct`: current single-criterion vision behavior.
2. `structured_vision`: selected scenarios evaluated in a single vision request with a schema; Ollama first, then installed-version-compatible vLLM.
3. `vision_decision_experimental`: a vision stage creates scenario-aware observations, then a local PyTorch decision service evaluates finite choices. MLX is the alternative for Apple Silicon. No cloud Jev endpoint is enabled by default.

Settings: analysis mode, vision engine/model, optional decision engine/model, selected scenario IDs. Apply changes atomically after availability checks and preserve the previous configuration on failure. Runtime model switches do not imply GPU model loading is instantaneous; show loading separately.

UI cards become independent selections and result tiles in structured mode. Keep custom prompt editing. Each selected field carries its own criterion; editing criteria must invalidate cached observations if those observations were criterion-dependent. UI language is independent of stable JSON field names and inference prompt language.

## Output contract (illustration, not a measured prediction)

```json
{
  "schema_version": 1,
  "source_id": "agx-local",
  "frame_id": "example-frame",
  "mode": "structured_vision",
  "results": {
    "person": {"state": "present", "probabilities": null},
    "fire": {"state": "absent", "probabilities": null},
    "smoke": {"state": "unknown", "probabilities": null},
    "baby_distress_visual": {"state": "unknown", "probabilities": null}
  },
  "calibrated": false
}
```

- Per-field states: `present`, `absent`, `unknown`. Omitted scenarios mean not evaluated, never negative.
- Person/fire/smoke can coexist. Never normalize probabilities across different scenario cards. Only normalize competing outcomes within a field.
- Expose candidate distributions only when the backend actually supplies them. Mark uncalibrated distributions explicitly; generated confidence text is not measured confidence.
- Preserve source/frame timestamp and both model identities in the response. Measure queue, image preprocessing, vision, decision, and end-to-end time separately.
- Reject malformed/truncated responses and unexpected/missing fields. A failed request, stale image or disconnected source produces unavailable/unknown, not an all-clear result.
- Alert logic operates independently on each selected field with consecutive-frame rules. Keep technical failure separate from absent detections.
- Visual baby distress is distinct from audible crying. Audio requires its own audio event classifier; volume alone does not establish crying.

## Vision bridge

An arbitrary image embedding cannot be injected into a text-only Qwen/Jev model and expected to be understood. Direct visual-token input needs a compatible trained vision encoder and projection/alignment path. Practical bridge options:

- Existing VLM -> concise, criterion-aware textual/structured observations -> small decision model.
- Task-specific visual detectors -> observations -> deterministic rules or decision model for contextual policies.
- A vision model that already supports image inputs -> direct schema output.

A generic caption can omit small flames, smoke or facial cues. The decision stage cannot recover missing visual evidence. Embedding-similarity retrieval may be useful as a gate but requires validation on each event class; it is not a generic substitute for visual understanding.

## Performance decision

`T_total = capture + preprocess + vision + optional_decision + transport/queue`.

Replacing text decoding does not remove image understanding. VLM caption plus a second LLM may be slower and use more memory than direct VLM classification. More plausible savings come from short bounded output, one shared image evaluation for multiple criteria, reusing observations for multiple policies, and selective invocation of heavier vision inference.

Benchmark on this host before choosing a default:

- A: current single-criterion YES/NO, plus repeated requests for the same set of scenarios.
- B: one VLM request returning all selected fields via schema.
- C: VLM observations plus local parallel decision service for the same fields.
- Compare matched quality requirements, same image sizes, same frames, same selected fields, cold/warm timings, p50/p95 end-to-end latency, throughput, peak GPU memory and optional energy per analyzed frame.
- Include positive/negative/ambiguous clips, low light, occlusion, steam versus smoke, absent babies, camera loss, and multi-event scenes. Report per-class precision/recall and unknown rate separately from JSON validity. Avoid calling a single live-camera sample an accuracy benchmark.
- Validate calibration with held-out labeled data (e.g. reliability bins/Brier score) before using numeric confidence as an alert threshold.

## Implementation order

1. Add typed decision contract and schema validation beside the existing boolean mode.
2. Add structured vision calls and per-field UI/status API, keeping single-criterion behavior compatible.
3. Establish the above baseline on representative clips.
4. Add isolated PyTorch decision service, audit candidate token handling and caching, then compare C with B.
5. Enable the experimental mode as a normal option only if end-to-end quality/latency/memory results justify it.

The initial feasibility review did not execute upstream code. The subsequent implementation below downloaded official Qwen weights and validated a separate local inference path.

## Implemented experimental mode (2026-09-26, supersedes design-only status)

Implemented `parallel_decision` beside `direct`:

- `scripts/decision_server.py`: local FastAPI service on 127.0.0.1:8001, using PyTorch + Qwen2.5-1.5B-Instruct. Single-token A/B/C labels represent present/absent/unknown. One batched forward pass scores independent questions; last-token logits only limits memory. This is an RLCD-inspired bounded classifier, **not** TypeSafe's trained Jev model or a claim of reproducing its training/calibration. This version batches full prompts rather than sharing prefix KV state.
- `src/services/decisions.py`: vision observations → per-category evidence → candidate scoring. Missing or explicitly uncertain evidence abstains with `probabilities: null`; no fabricated 100% unknown scores. Candidate distributions are uncalibrated and are conditional on the vision observation, not measured image-classification accuracy.
- `GET/POST /api/settings/decisions`: runtime mode and scenario list; availability checks, analysis lock and atomic persistence in `temp/decision-settings.json`.
- `/api/status` and socket status events include `decision_settings` and `decision_result`; result metadata includes source/frame/epoch, model IDs and vision/decision/total timings. Changing source/settings invalidates old results.
- Five preset cards become independent selections. Custom freeform criteria remain in direct mode for this first release.
- Per the user's clarification, the UI now uses **one category distribution chart**, not temporal curves: X = scenario names, Y = presence candidate score (0–100%). Full present/absent/unknown distributions are in a collapsed table. Missing evidence shows a dash, never a zero score. Host and mobile client use the same component, with four UI languages.
- Experimental vision decisions never call the legacy notification hook. No continuous monitoring is enabled by selecting the mode.

### Run locally

On this machine the existing `.venv-vllm` already contains the tested PyTorch/Transformers runtime; this does **not** start a vLLM engine. The launcher prefers `.venv-decision`, then falls back to `.venv-vllm`. `DECISION_PYTHON` can point to another prepared interpreter. For a fresh install, create a Python 3.10+ environment, install PyTorch compatible with the host GPU, then `pip install -r requirements-decision.txt`. ARM/Jetson needs its platform-compatible PyTorch; it has not been tested here.

```sh
./run.sh decision-up
# Wait for Settings → Analysis mode → Check service to report ready.
# Select Multi-scenario (applies immediately), then Monitor → Analyze once.
./run.sh decision-down
ollama stop qwen2.5vl:3b
```

The setup menu also exposes start/stop classifier actions. Model files are cached under `temp/huggingface` by default. First start downloads official Qwen weights; no remote custom model code is executed. An unavailable decision service preserves the previous settings and reports an error. An inference failure cannot become a negative classification.

### Validation and resource cleanup

- 2026-09-26 local CUDA, RTX 2080 Ti: successful five-field camera request took **1,128 ms** (vision **856 ms**, classifier **238 ms**, remainder orchestration/transport). This is a single functional sample, not an accuracy benchmark, p95 result, or evidence of a speedup over direct vision.
- Earlier experiment found high candidate scores even when observations said UNKNOWN; added explicit abstention and isolated per-field observations before proceeding.
- Tested invalid distributions, missing fields, duplicate scenarios, busy/unavailable settings, stale-result rejection, no notification dispatch and unknown evidence behavior.
- After the test: continuous monitoring OFF, classifier service stopped/disabled, Ollama vision model unloaded. GPU total usage returned to about 0.9 GiB including the user's desktop/browser; no test inference model remains resident.
- Latest test result retained in ignored `temp/decision-validation.json`. Accuracy on smoke/fire/baby distress, calibration, multi-camera throughput and a matched baseline performance comparison remain unvalidated.

## Idle GPU and unavailable services

- Start/one-shot requests check classifier readiness before vision inference. A missing classifier returns HTTP 503 without loading the vision model.
- Inference errors stop continuous analysis to prevent repeated failed GPU work.
- Pausing monitoring or completing a one-shot analysis requests unloading the current Ollama model and the experimental classifier. The classifier process can reload its weights on the next request; this adds cold-start latency. vLLM residency remains managed by its service.
- Analysis mode changes apply immediately from Settings. Failed changes restore the selected mode and show the reason. Single-scenario mode selects one card; parallel mode allows multiple cards.
- System GPU usage includes desktop and browser rendering, even when no AI model is loaded.
