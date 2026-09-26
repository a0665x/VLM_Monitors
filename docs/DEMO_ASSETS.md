# Documentation screenshots and generated scenarios

Captured 2026-09-26. These assets explain the product, not its measured accuracy.

## Provenance

- Camera scenes: generated using the built-in **imagegen** tool; fictional people and rooms, no live camera capture.
- Screenshots: actual repository HTML/CSS/JavaScript served by `scripts/docs_preview.py`, captured through the Codex browser tool.
- Mobile images: responsive browser viewport **430 × 932**, full-page captures. This is not a physical iPhone/Safari test or a native iOS app.
- Desktop: normal browser viewport, full-page host capture; cropped score panels. Screenshot sizes can differ from CSS viewport dimensions due to scrolling/device scale.
- The preview has isolated HTTP fixture routes, a dummy socket adapter, and static image frames. It imports no production camera, model or Tailscale services. Sharing does not request camera permission in this preview.
- The demo QR encodes `https://example.com/vlm-monitor-demo`. It intentionally grants no access to a real host.

## Assets

| File in `assets/` | Purpose |
| --- | --- |
| `host-dashboard.jpg` | Host dashboard, two sources, cards and scores |
| `qr-join.jpg` | Host QR and phone connection instructions |
| `phone-watch.jpg` | Mobile gallery after opening the QR entry page |
| `phone-share.jpg` | Mobile camera sharing form, synthetic preview |
| `scores-person-pet.jpg` | Presence bars for a person and pet fixture |
| `scores-fire-smoke.jpg` | Presence bars for a fire and smoke fixture |
| `scenario-person-pet.png` | Generated living-room frame |
| `scenario-fire-smoke.png` | Generated kitchen frame |

## Illustrative values

No model evaluated these generated pictures for these screenshots. Hand-authored fixture scores keep UI documentation deterministic. Each scenario has its own present/absent/unknown distribution, not one softmax across all scenarios.

| Fixture | Person | Baby distress | Fire | Smoke | Pets |
| --- | ---: | ---: | ---: | ---: | ---: |
| Host / living room | 97% | 1% | 1% | 2% | 93% |
| Phone / kitchen | 1% | 1% | 94% | 88% | 2% |

Unknown is 1% per field in these fixtures; absent is the remainder. Zero timing values are fixture placeholders, not measured speed. Actual inference scores are uncalibrated; uncertain evidence can yield no numeric distribution.

## Reproduce

```bash
.venv/bin/python scripts/docs_preview.py
```

1. Open `http://127.0.0.1:5055/#monitor` for the host, `#connect` for the QR guide, or `/join` for the phone.
2. The default selected fixture is the living room. Use a camera's Monitor button to switch the isolated fixture, or POST `{"source_id":"phone-kitchen"}` to the preview's `/api/sources/select` endpoint.
3. Capture desktop full page and the Scenario scores panel; use a 430 × 932 viewport for mobile gallery/sharing captures. Keep the demo disclosure visible or preserve the fixture label in cropped charts.
4. Close the preview server when finished. The production service on port 5000 is unaffected.

Only mode bootstrap and selection of the two fixture sources are supported POST actions. Other changes return 403. These demo routes are not mounted by the production server.

## Generation prompts (verbatim)

### Person and pet

> Generate one photorealistic wide 16:9 synthetic home security camera example photograph for an open source monitoring software README. Fixed elevated corner camera viewpoint, bright modern living room, adult parent in casual clothing entering through doorway on the left, a golden retriever sitting near couch on the right, realistic natural afternoon light, entire room visible, uncluttered, ordinary lived-in home. No fire, no smoke, no children, no distress. No words, no logos, no overlays, no UI. This is a fictional staged scenario to demonstrate person and pet detection; no real person likeness. High photographic fidelity, surveillance wide-angle but no heavy distortion.

### Fire and smoke

> Create a single photorealistic 16:9 fictional camera frame for a software documentation demo of fire and smoke detection. Wide fixed smartphone camera view of an empty residential kitchen in daylight. A small pan on the stove has clearly visible orange flames and a visible modest plume of gray smoke rising toward the extractor hood. No people, no pets, no children, no injuries, no ruined building. Clearly staged synthetic incident scenario, realistic photographic materials and light, flames and smoke readily visible at thumbnail size. Kitchen mostly undamaged, panoramic view includes countertop and cabinets. No text, no logos, no security camera overlays, no UI.
