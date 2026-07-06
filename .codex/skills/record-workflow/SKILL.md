---
name: record-workflow
description: Record a workflow library entry (spec §2.3; DOC1 §6.4) — a reusable named ordering of stages. Writes .workshop-lite/ledger/workflows/<slug>.md and refreshes workflows/INDEX.md. Use when the user types /record-workflow or asks to declare a reusable workflow/stage-ordering.
---

# /record-workflow

A **workflow** is data: a declared ordered set of stages (e.g.
`design → spec → build-plan → execute → write-tests → test/fix → verify → certify`).
Each stage is realized as its own task(s) walking the full R6 lifecycle — a stage
is *not* a sub-step of one task. A reusable named ordering is a workflow
(distinct from build-step edges).

## 1. Gather inputs

Required:
- **title** — the workflow's human name (becomes the slug id).
- **stages** — ordered list; each stage is `{name, produces_artifact_kind?, parallelizable?}`.
- **author** — the calling member's `@id`.

Optional:
- **status** — `draft | active (default) | superseded | retired`.
- **library-layer** — `built-in | project | user (default)` — origin in the WL2 override stack.
- **is-default** — flag; marks this as the layer's default workflow.
- **supersedes** — id of a prior workflow this replaces.
- **linked-decisions** — comma-separated decision ids.
- **owner-user** — defaults `user/local`.

## 2. Write the workflow

```bash
.venv/bin/python3 .claude/scripts/dev-mgmt/cli.py record-workflow \
    --title "<title>" \
    --stages-json '[{"name":"design"},{"name":"build","parallelizable":true}]' \
    --author "@<member>" \
    [--status draft|active|superseded|retired] \
    [--library-layer built-in|project|user] \
    [--is-default] \
    [--supersedes "<id>"] \
    [--linked-decisions "<csv>"] \
    [--owner-user "<owner>"]
```

The writer validates (each stage requires a `name`; `library_layer` ∈ the closed
set; `is_default` is a bool), writes the file, and re-renders the INDEX. Library
layering + same-layer collision resolution across entries is governed by the
collision resolver (spec §2.3 — `user ▷ project ▷ built-in`, authority-gated).
