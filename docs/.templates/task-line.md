---
id: null
type: task
status: pending
description: null
sprint_id: null
assignee: null
linked_issues: []
linked_decisions: []
---

# Task line format (D20.A)

Tasks are **inline list items** in a sprint's `tasks.md` file — they are not standalone entity files. The frontmatter above represents the parsed shape that `validate_task_line` returns for a single line; the on-disk source of truth is the line itself.

## Line shape

```
- [<checkbox>] **<task-id>** — <description>[ (<metadata-block>)]
```

- `[<checkbox>]` — `[ ]` for any non-completed status; `[x]` ONLY for completed (canonical-only per Q2a).
- `<task-id>` — `task-<sprint-id>.<NN>` per **D19** (per-sprint counter, globally unique via sprint-id prefix).
- `<description>` — free-form text, may contain parentheses (parser anchors on FINAL `(...)` at end-of-line per Q1a).
- `<metadata-block>` — optional `(key: value; key: value; key: [item, item])` at end-of-line.

## Metadata keys

| Key | Type | Notes |
|----|------|-------|
| `assignee` | `@<member-id>` | optional |
| `status` | `pending` \| `in_progress` \| `blocked` | omit for pending (default); completed encoded by `[x]` only |
| `linked_issues` | list of issue ids | `[id1, id2]` square-bracket form |
| `linked_decisions` | list of decision ids | same |
| `reason` / `blocker` | free-form string | recommended when `status: blocked` (warning, not rejection, if absent) |

**Forbidden chars in values** (per Q1b): literal `;`, `)`, `]`, `,`. These are delimiter chars; values containing them are rejected by `validate_task_line` with a specific error pointing at the offending char.

## Examples

```markdown
- [ ] **task-dev-mgmt.5.1** — Plain task description
- [ ] **task-dev-mgmt.5.2** — Description with (free parens) (assignee: @work)
- [x] **task-dev-mgmt.5.3** — Completed task (linked_issues: [2026-05-14-05])
- [ ] **task-dev-mgmt.5.4** — In-progress task (status: in_progress; assignee: @work)
- [ ] **task-dev-mgmt.5.5** — Blocked task (status: blocked; reason: waiting on review)
```

## Mutation semantics (D21 + Q2a canonical-only)

Status transitions happen via direct edit of the task line in `tasks.md`. Validator REJECTS multi-representation drift — e.g., `[ ] **task-X** — Desc (status: completed)` is invalid because the completed state has a single canonical encoding (`[x]` with no `(status:)` entry).

Status flow: `pending → in_progress → completed` (terminal). `blocked` is transient — can move back to `pending` or forward to `completed`.

## Workshop import

Each line round-trips through `validate_task_line` into a structured dict matching the Workshop Item entity columns: `id`, `status`, `description`, `assignee`, `linked_issues`, `linked_decisions`. The `[x]` ↔ `status: completed` mapping is handled at the parser level so the Item table sees the single canonical enum.
