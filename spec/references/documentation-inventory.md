# Documentation Inventory

## Purpose

This file classifies current Markdown documents so agents know what to read, link, or update without scattering project knowledge again.

## Canonical Progressive-Disclosure Entry

- `spec/PROJECT_MAP.md`: Level 1 onboarding map.
- `spec/ARCHITECTURE.md`: Level 2 system architecture.
- `spec/MODULES.md`: Level 2 source ownership map.
- `spec/RUNTIME.md`: Level 2 runtime and operations reference.
- `spec/API.md`: Level 2 backend interface map.
- `spec/TROUBLESHOOTING.md`: operational field notes and bug reminders.
- `spec/TODO.md`: pending engineering and optimization work.
- `spec/TESTING.md`: Level 2 verification guidance.

## Existing Root Docs

- `README.md`: user-facing Chinese quick start and feature summary. Keep concise and aligned with current port `5000`.

## Spec Supplemental Docs

- `spec/PROJECT_OVERVIEW.md`: broad technical reference. Useful for architecture context, but some details can drift from source; verify against code.
- `spec/DOCUMENTATION_INDEX.md`: human-facing doc index.
- `spec/PRD.md`: product requirements and intent.
- `spec/USER_MANUAL.md`: end-user operation guidance.
- `spec/references/CLEANUP_SUMMARY.md`: historical cleanup notes.

## Existing `specs/`

- `specs/FAQ.md`: critical troubleshooting and lessons learned. Keep in place for now because existing docs reference it. Link from `spec/PROJECT_MAP.md`.

## Missing Or Stale References Found During Spec Setup

- `AGENTS.md` was referenced by older docs but was not present in the project root.
- `README_FLASK.md` was referenced by older docs but was not present in the project root.
- Some older docs referenced Streamlit port `8501`; the current Docker runtime serves Flask on `5000`.

## Update Rules

- Keep the public GitHub landing document at the project root as `README.md`.
- Add architecture and agent-onboarding summaries under `spec/`.
- Update `spec/PROJECT_MAP.md` whenever adding, renaming, or deprecating spec files.
- Before changing MediaMTX/HLS/camera behavior, read `specs/FAQ.md`.
