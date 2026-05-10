---
name: project-spec-onboarding
description: Fast project understanding and initialization for any codebase through a progressive-disclosure ./spec documentation structure. Use when the user asks Codex to understand a new project, read project architecture from ./spec, initialize project context, organize existing Markdown project docs, create PROJECT_MAP.md, or set up ./spec so future agents can quickly onboard before making changes.
---

# Project Spec Onboarding

Use this skill to understand a project through `./spec` first, then fall back to helping the user establish `./spec` only after consent.

## Core Rule

Start at the current project root. Check whether `./spec` exists at the first level.

- If `./spec` exists: use it as the primary onboarding entrypoint before reading broad source files.
- If `./spec` does not exist: do not create files immediately. Reply in a friendly way that this project has not yet established progressive-disclosure project docs, and ask whether the user wants help understanding the project and creating `./spec`.
- If the user agrees: inspect the project, organize existing Markdown docs, and create a progressive-disclosure `./spec` structure.

## Existing `./spec` Workflow

1. Read `./spec/PROJECT_MAP.md` first when present.
2. Read only the linked level-2 documents relevant to the user task.
3. Read deeper references only when a task needs implementation details, edge cases, protocols, schemas, or historical decisions.
4. Prefer `./spec` over ad hoc repository-wide exploration, but verify against source code before editing behavior.
5. If `./spec` is stale or incomplete, note the gap and update it when the current task materially improves project understanding.

## Missing `./spec` Response

When `./spec` is absent, answer in the user's language. Keep it brief and friendly:

```text
我看起來還沒有找到第一層的 ./spec，所以這個專案可能還沒建立「漸進式披露」的理解文件。
需要我幫你進一步理解這個專案，並整理出 ./spec/PROJECT_MAP.md 與分層 spec 文件，方便之後快速調用嗎？
```

Do not scan and document the full project until the user agrees, unless the user already explicitly asked to create the docs.

## Creating `./spec`

When consent is given, read `references/spec-authoring.md` before writing project docs.

Use `scripts/spec_inventory.sh <project-root>` to get a first-pass inventory of:

- existing `./spec` files
- Markdown files outside ignored directories
- top-level project files and directories

Then inspect the actual files needed to understand the architecture. Build `./spec` with progressive disclosure:

- Level 1: `./spec/PROJECT_MAP.md` with name, description, major domains, and links.
- Level 2: focused concept files such as `ARCHITECTURE.md`, `MODULES.md`, `DATA_MODEL.md`, `RUNTIME.md`, `API.md`, `UI.md`, `TESTING.md`, or `OPERATIONS.md`.
- Level 3: `./spec/references/` and `./spec/scripts/` only for deeper details or repeatable project-specific discovery commands.

Keep files focused. Do not collapse the whole project into one giant Markdown file.

## Markdown Organization

If the project already has many `.md` files, classify them before moving or rewriting anything:

- user-facing docs: keep in place unless the project convention says otherwise
- developer onboarding docs: link from `PROJECT_MAP.md`
- architecture or implementation notes: migrate or summarize into Level 2 spec docs
- historical notes, decisions, or long references: place under `./spec/references/`

Preserve existing intent and avoid deleting original docs unless the user asks. Prefer adding links and summaries over moving files when ownership is unclear.
