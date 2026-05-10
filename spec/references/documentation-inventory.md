# Documentation Inventory

## Purpose

This file classifies existing Markdown documents so agents know what to read, link, or update without moving user-facing docs unexpectedly.

## Canonical Progressive-Disclosure Entry

- `spec/PROJECT_MAP.md`: Level 1 onboarding map.
- `spec/ARCHITECTURE.md`: Level 2 system architecture.
- `spec/MODULES.md`: Level 2 source ownership map.
- `spec/RUNTIME.md`: Level 2 runtime and operations reference.
- `spec/API.md`: Level 2 backend interface map.
- `troubleshooting.md`: operational field notes and bug reminders.
- `ToDoList.md`: pending engineering and optimization work.
- `spec/TESTING.md`: Level 2 verification guidance.

## Existing Root Docs

- `README.md`: user-facing Chinese quick start and feature summary. Keep concise and aligned with current port `5000`.
- `PROJECT_OVERVIEW.md`: broad technical reference. Useful for architecture context, but some details can drift from source; verify against code.
- `DOCUMENTATION_INDEX.md`: human-facing doc index. Keep links relative and avoid references to missing files.
- `PRD.md`: product requirements and intent.
- `User_Manual.md`: end-user operation guidance.
- `CLEANUP_SUMMARY.md`: historical cleanup notes.

## Existing `specs/`

- `specs/FAQ.md`: critical troubleshooting and lessons learned. Keep in place for now because existing docs reference it. Link from `spec/PROJECT_MAP.md`.

## Missing Or Stale References Found During Spec Setup

- `AGENTS.md` was referenced by older docs but was not present in the project root.
- `README_FLASK.md` was referenced by older docs but was not present in the project root.
- Some older docs referenced Streamlit port `8501`; the current Docker runtime serves Flask on `5000`.

## Update Rules

- Keep user-facing documents in their current locations.
- Add architecture and agent-onboarding summaries under `spec/`.
- Update `spec/PROJECT_MAP.md` whenever adding, renaming, or deprecating spec files.
- Before changing MediaMTX/HLS/camera behavior, read `specs/FAQ.md`.
