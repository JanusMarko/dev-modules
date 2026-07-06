---
name: start-sprint
description: Scaffold a new sprint folder at docs/sprints/active/sprint-<id>/ with plan.md (frontmatter + body) and tasks.md, then refresh docs/sprints/INDEX.md. Use when the user types /start-sprint or asks to start/scaffold a sprint.
---

# /start-sprint

When the user invokes `/start-sprint`, run this flow.

## 1. Gather inputs

Required:

- **sprint-id** — short identifier, e.g. `dev-mgmt.2` (becomes folder name `sprint-<id>/`)
- **title** — short imperative summary of what this sprint will ship
- **author** — typically the planner; in a parley session use the calling member's `@id`

Optional:

- **from-plan** — absolute path to an approved plan-mode plan file (e.g. `~/.claude/plans/<adjective>-<animal>.md`). When set, its body becomes the new `plan.md` body. Existing YAML frontmatter in the source is stripped — fresh frontmatter is generated regardless.
- **linked-design-docs** — comma-separated references (e.g. `LIGHTWEIGHT-DEV-MGMT-SYSTEM.md#7`)
- **spec** — Phase 3 (sub-spec `docs/design/2026-05-29-wl-sprint-spec-yaml.md` §8.1): when set, additionally scaffolds a `spec.yaml` sidecar with role-kind defaults. Values: `kris-binding` (all standard artifacts required), `autonomous-arc` (artifacts non-required; INFO log only at /end-sprint), `routine` (minimal spec). Omitted: legacy behavior — no spec.yaml created.
- **spec-has-user-journey** — flag: set `has_user_journey: true` in the spec.yaml. Auto-upgrades `golden_path_verifier` to `required: true` per sub-spec §3.3. No effect without `--spec`.
- **spec-charter-ref** — comma-separated charter references for `charter_ref` field; accepts local markdown paths and `parley://charters/<id>` opaque URIs (D-WL-20).
- **force** — overwrite `plan.md` if the sprint folder already exists (off by default)

If any required input is missing or ambiguous, use `AskUserQuestion` to collect.

## 2. Determine author

- If in a parley session, run `parley whoami` and use the member's `id` (prefixed with `@`).
- Otherwise default to the human operator's name as a `@id` string.

## 3. Write the sprint scaffold

From the repo root, invoke the CLI:

```bash
.venv/bin/python3 .claude/scripts/dev-mgmt/cli.py start-sprint \
    --sprint-id "<sprint-id>" \
    --title "<title>" \
    --author "@<member>" \
    [--from-plan "<absolute-path>"] \
    [--linked-design-docs "<csv>"] \
    [--spec "<kris-binding|autonomous-arc|routine>"] \
    [--spec-has-user-journey] \
    [--spec-charter-ref "<csv>"] \
    [--force]
```

If the repo doesn't have a `.venv/`, fall back to `python3` (PyYAML must be available).

The CLI:
- creates `docs/sprints/active/sprint-<sprint-id>/`
- writes `plan.md` (validated against the §6 Sprint Plan schema)
- writes `tasks.md` with a `# Tasks — sprint-<sprint-id>` heading and no frontmatter
- silently updates `SPRINT-BACKLOG.md` if present (sets the entry to `status=in_progress`); no-op if the file is missing
- atomically re-renders `docs/sprints/INDEX.md`
- prints the written `plan.md` path on stdout

A `FileExistsError` (exit non-zero) means the sprint folder already has a `plan.md` and `--force` was not set — investigate before retrying.

## 4. Report back

Tell the user:

- the path to the written `plan.md`
- the path to the empty `tasks.md` (sibling)
- a one-line summary of what was scaffolded

If a plan-mode plan was imported via `--from-plan`, mention the source path so the provenance chain is visible.

## Retroactive sprint backfill (intentionally-empty `tasks.md`)

When stamping a sprint stub for work that was already completed
out-of-band (cross-repo or pre-substrate commits), the sprint folder
emits with an intentionally-empty `tasks.md`. The canonical work record
lives in the git commit + an `external_commit_ref` field in
`plan.md`/`retro.md` frontmatter; `tasks.md` is a
convention-completeness file, not a content file.

**When to use:** retroactive cross-repo stubs (e.g. `sprint-workshop-
lite.10.4` cross-repo stub for dev-modules MODULE_AUTHOR_GUIDE.md §5)
or back-filling pre-substrate work (e.g. `sprint-maxai.1.5b.3-7` —
9 stubs for Phase 1.5b sub-stretches, each pointing to its
`maxai://commit/<sha>` via `external_commit_ref`).

**Pattern:**
1. `/start-sprint <id> "<title>"` as normal — emits the empty `tasks.md`.
2. Add `external_commit_ref: <repo-uri>://commit/<sha>` to `plan.md`
   frontmatter (or `retro.md` if backfilling fully post-hoc).
3. Leave `tasks.md` empty — do NOT populate retroactively with single-
   line `## Shipped via maxai://commit/<sha>` entries (redundant with
   retro.md's "What shipped" section + obscures the
   tasks-are-forward-looking convention).
4. If immediately closing the stub, `/end-sprint <id>` next — moves
   the folder to `archive/` + writes a templated `retro.md`. If the
   real retro lives elsewhere (a cross-repo doc), use `--retro-body-
   path` to inject the body verbatim.

Documented per issue `2026-05-15-03` (workshop-lite.17 closure).

## Notes

- `/start-sprint` only writes the skeleton. Filling out `## Context`, `## Scope`, `## Verification`, and `## Out of scope` sections of `plan.md` is the planner's job after invocation (or done implicitly when `--from-plan` is used).
- The lightweight dev-mgmt system is markdown-only today; frontmatter maps 1:1 to Workshop entity columns for future Refinery import (see `LIGHTWEIGHT-DEV-MGMT-SYSTEM.md` §10).
- This skill is parley-agnostic at its base — it works for a solo CC session in a fresh repo as long as `docs/sprints/` (or its parents) can be written.
