---
name: add-task
description: Append a Task line to a sprint's tasks.md in the lightweight dev-mgmt system. Captures sprint_id, description, status, assignee, and optional linked_* arrays into a single D20.A-format line. Use when the user types /add-task or asks to file a task/todo against a sprint.
---

# /add-task

When the user invokes `/add-task`, run this flow.

## 1. Gather inputs

Required:

- **sprint-id** — the sprint to file the task against (e.g., `dev-mgmt.5`). The sprint must already exist as `docs/sprints/active/sprint-<id>/` or `docs/sprints/archive/sprint-<id>/`.
- **description** — free-form task description (must be non-empty). May contain free parentheses; the parser anchors the metadata block on the FINAL `(...)` at end-of-line (per **Q1a**).

Optional:

- **assignee** — `@<member-id>` for the responsible party.
- **status** — the **R6 six-state** (spec §2.3 / §11): `created` (default) | `picked-up` | `in-progress` | `verified` | `done` | `cleaned-up`. Legacy v1 values (`pending`/`in_progress`/`completed`/`blocked`) are still accepted and mapped on the way in; `blocked` is no longer a task status (raise a block-signal, then set the underlying R6 status). Run `migrate-tasks` to canonicalize existing files.
- **linked-issues** — comma-separated issue ids the task addresses.
- **linked-decisions** — comma-separated decision ids the task implements.

If any required input is missing or ambiguous, use `AskUserQuestion` to collect.

**No `body` argument**: tasks are inline list items, not file-level entities. Use `/record-issue` if you need a multi-section repro/root-cause/fix-path document.

## 2. Determine assignee + parley context

If in a parley session:

1. Run `parley whoami` if the caller didn't specify an assignee — defaulting to the calling member's `@<id>` is reasonable for self-assigned work.
2. Tasks do NOT carry `linked_msg_ids` in their inline line format (cross-link provenance lives at the Issue / Decision / Conversation level; tasks are operational, not durable artifacts).

If NOT in a parley session, `--assignee` is the human operator unless explicitly specified.

## 3. Write the task

From the repo root, invoke the CLI:

```bash
.venv/bin/python3 .claude/scripts/dev-mgmt/cli.py add-task \
    --sprint-id "<id>" \
    --description "<desc>" \
    [--assignee "@<member>"] \
    [--status created|picked-up|in-progress|verified|done|cleaned-up] \
    [--linked-issues "<csv>"] \
    [--linked-decisions "<csv>"]
```

If the repo doesn't have a `.venv/`, fall back to `python3` (PyYAML must be available).

The CLI:
- looks up the sprint folder (`active/` or `archive/`)
- initializes `tasks.md` with the standard heading if absent
- parses existing task lines to find max-NN for the sprint, computes the next `task-<sprint-id>.<NN>` id (**D19**)
- **idempotency check (Q5)**: if a task with the same description AND same metadata identity already exists, returns that task's id without appending. Different metadata → new task (Q5b pure-append).
- renders the D20.A canonical line (R6):
  - checkbox is a coarse visual derived from the R6 status bucket: `[ ]`=created/picked-up · `[~]`=in-progress/verified · `[x]`=done/cleaned-up · `[!]`=block-signal overlay (§9, not an R6 status). The explicit `status:` field is authoritative; it is OMITTED for the bucket default (created/in-progress/done) and stamped for the non-default (picked-up/verified/cleaned-up).
  - bold task-id, em-dash, description
  - optional `(key: value; key: value; key: [a, b])` metadata block at end-of-line
- validates the rendered line round-trips through `validate_task_line`
- appends the line to `tasks.md`
- prints `<tasks_md_path>\t<task_id>` on stdout

A `ValidationError` exits non-zero and writes nothing. Common causes:
- `--status` outside the R6 set `{created, picked-up, in-progress, verified, done, cleaned-up}`
- Metadata value contains a forbidden char `; ) ] ,` (**Q1b**)
- Description is empty after trim

## 4. Report back

Tell the user:

- the path to `tasks.md` (where the line was appended)
- the auto-generated task id (e.g., `task-dev-mgmt.5.7`)
- the rendered line (so the user can verify the canonical form)

## Notes

- **D19 (id convention)**: `task-<sprint-id>.<NN>` (per-sprint counter). Different shape from `/record-decision`'s `YYYY-MM-DD-NN-<slug>` because tasks belong to a sprint, not a date.
- **D20.A (line format)**: single line per task; markdown checkbox + bold ID + em-dash + description + optional `(metadata)`. Reference doc: `docs/.templates/task-line.md`.
- **R6 status state machine** (spec §2.3 / §11): `created → picked-up → in-progress → verified → done → cleaned-up` (with a `verified → in-progress` rework back-edge). `blocked` is NOT an R6 status — it becomes a block-signal overlay (`[!]`, §9) laid atop the unchanged underlying R6 status.
- **Q1a (final-paren anchor)**: descriptions may contain free `(...)`; only the FINAL `(...)` at end-of-line is metadata.
- **Q1b (forbidden chars)**: metadata values reject literal `; ) ] ,` — these are delimiter chars in the D20.A grammar.
- **Canonical-only mutation (R6)**: the explicit `status:` field is authoritative; it is omitted for the checkbox bucket default and stamped for the non-default. The validator rejects a redundant default (`[ ] ... (status: created)`) and a bucket mismatch (`[x] ... (status: in-progress)`). This keeps Workshop import deterministic.
- **Block-overlay advisory**: a `[!]` overlay without a `reason` or `blocker` key emits a non-blocking warning. The underlying R6 status is unchanged beneath the block.
- **Migration (BC1.5 / §C.6)**: `migrate-tasks [--sprint-id <id>]` rewrites legacy v1 4-state lines to canonical R6 in place; idempotent, non-task lines preserved.
- **Q5 (idempotency)**: same description + same metadata returns existing task_id; different metadata → new task (pure-append).
- **Updates**: status transitions happen via direct file edit of the task line in `tasks.md` (no `/update-task` skill yet — deferred). After edit, re-validate via `validate_task_line` to catch drift.
- **Workshop importability**: each line round-trips through `validate_task_line` into a structured dict matching the Workshop Item entity columns (`id`, `status`, `description`, `assignee`, `linked_issues`, `linked_decisions`).
- **Parley-agnostic base**: this skill works in a solo CC session in a fresh repo too, as long as a sprint folder exists.
