---
name: write-resume-ledger
description: Write a resume-ledger (spec §2.3; DOC1 §7) — the in-flight state + next actions for the NEXT incarnation of THIS worker after a restart (distinct from a handoff, which is the settled post-state for the next worker). Writes .workshop-lite/ledger/resume-ledgers/<id>.md. Use when the user types /write-resume-ledger or asks to snapshot in-flight state for self-resumption.
---

# /write-resume-ledger

A **resume-ledger** captures the in-flight state + immediate next actions for the
**next incarnation of *this* worker** after a restart. It is distinct from a
`handoff` (the settled post-state for the *next* worker). Fire it off the
observable moment; it is durable at creation. Carries `owner_user`.

## 1. Gather inputs

Required:
- **worker** — the role/seat-id this ledger resumes (e.g. `@wl-bc1`).
- **in-flight-state** — free-text snapshot of where the work stands right now.
- **next-actions** — ordered list of the immediate next actions.
- **author** — the calling member's `@id`.

Optional:
- **canonical-pointer-ref** — ref to a `canonical-pointer` for the body-of-work.
- **supersedes** — id of the prior resume-ledger this replaces.
- **owner-user** — defaults `user/local`.

## 2. Write the ledger

```bash
.venv/bin/python3 .claude/scripts/dev-mgmt/cli.py write-resume-ledger \
    --worker "@<seat>" \
    --in-flight-state "<text>" \
    --next-actions-json '["<action1>","<action2>"]' \
    --author "@<member>" \
    [--canonical-pointer-ref "<ref>"] [--supersedes "<id>"] [--owner-user "<owner>"]
```

The writer validates (`next_actions` is a list; status is `written`), writes the
file, and re-renders the INDEX.
