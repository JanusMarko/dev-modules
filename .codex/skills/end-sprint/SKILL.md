---
name: end-sprint
description: Close out a sprint — write retro.md (if absent), move the folder from docs/sprints/active/ to docs/sprints/archive/, refresh docs/sprints/INDEX.md. Non-destructive by default (preserves an existing retro.md). Use when the user types /end-sprint or asks to close/archive a sprint.
---

# /end-sprint

When the user invokes `/end-sprint`, run this flow.

## 1. Gather inputs

Required:

- **sprint-id** — identifier of the sprint to close (must match an existing `docs/sprints/active/sprint-<id>/`)
- **author** — typically the implementer wrapping up; in a parley session use the calling member's `@id`

Optional:

- **retro-title** — title for the retro; defaults to `sprint-<id> retrospective`
- **retro-body-path** — absolute path to a file whose content becomes the body of `retro.md`. Useful when the retro was drafted elsewhere. (No frontmatter stripping is done; the file should be body-only.)
- **test-results-json** — JSON object with counters, e.g. `{"passed": 12, "failed": 0, "skipped": 1, "xfailed": 0, "xpassed": 0}`
- **linked-decisions** — comma-separated decision ids made during the sprint
- **linked-reviews** — comma-separated review ids made during the sprint
- **force** — overwrite `retro.md` if one already exists (off by default — see §Non-destructive)

If any required input is missing or ambiguous, use `AskUserQuestion` to collect.

## 2. Determine author

- If in a parley session, run `parley whoami` and use the member's `id` (prefixed with `@`).

## 3. Close the sprint

From the repo root, invoke the CLI:

```bash
.venv/bin/python3 .claude/scripts/dev-mgmt/cli.py end-sprint \
    --sprint-id "<sprint-id>" \
    --author "@<member>" \
    [--retro-title "<title>"] \
    [--retro-body-path "<absolute-path>"] \
    [--test-results-json '<json>'] \
    [--linked-decisions "<csv>"] \
    [--linked-reviews "<csv>"] \
    [--force]
```

The CLI:
- writes `retro.md` (validated against the §6 Retrospective schema) **only if it does not already exist** — see §Non-destructive
- moves `docs/sprints/active/sprint-<id>/` to `docs/sprints/archive/sprint-<id>/`
- silently updates `SPRINT-BACKLOG.md` if present (sets the entry to `status=shipped`); no-op if the file is missing
- atomically re-renders `docs/sprints/INDEX.md`
- prints the path to the archived `retro.md` on stdout

A `FileNotFoundError` means no active sprint matches `--sprint-id`. A `FileExistsError` means the archive target already exists (a prior `/end-sprint` left it behind); investigate before retrying.

## Phase 3 spec.yaml gate (sub-spec §4.2)

If the sprint has a `docs/sprints/active/sprint-<id>/spec.yaml` AND its `sprint_kind` has `gate_at_end=True` (built-in: `kris-binding`; or per-repo `[sprints.kinds]` extensions), the CLI runs `validate --check sprint-specs --strict --sprint <id>` BEFORE moving any files.

- **Pass**: existing `/end-sprint` behavior proceeds (retro write + archive move + INDEX refresh).
- **Fail** (any V1/V3/V5/V6 strict warning): the CLI prints the validator output to stderr and exits non-zero. **No folder move, no retro write, no INDEX change.** The SM must either:
  1. Populate the missing `required_artifacts[*].path` (or `parley_msg_id`) in `spec.yaml`, OR
  2. Downgrade `required: false` for the artifact — but per sub-spec §4.2 this requires a Kris-call documented in a Decision entity.

For `sprint_kind: autonomous-arc`: the gate is INFO-only; missing artifacts surface as advisory warnings but `/end-sprint` proceeds. Suitable for autonomous-arc protocol where Kris-ratify happens at arc-close, not per-sprint.

For `sprint_kind: routine`: no gate; legacy `/end-sprint` behavior.

## Non-destructive default (D2)

If `retro.md` already exists in the active sprint folder (e.g. it was hand-written during the sprint, or a prior aborted `/end-sprint` left it behind), the CLI **skips the write** and only does the archive move + INDEX update. This preserves manually-authored retro content.

To intentionally overwrite an existing retro with the templated frontmatter + body, pass `--force`.

## 4. Report back

Tell the user:

- the path to the archived `retro.md`
- whether the retro was newly written or preserved (the latter when `retro.md` pre-existed and `--force` was not set)
- a one-line summary of what was closed out

## Notes

- This skill triggers `INDEX.md` re-render for `docs/sprints/INDEX.md`. The archived sprint will show `status=archived` (derived from folder location) and `stage=retro`.
- `test_results` follows §6 Retro schema: `passed`, `skipped`, `xfailed`, `xpassed`, `failed` as integers. Omit when not running pytest.
- The lightweight dev-mgmt system is markdown-only today; frontmatter maps 1:1 to Workshop entity columns for future Refinery import (see `LIGHTWEIGHT-DEV-MGMT-SYSTEM.md` §10).
