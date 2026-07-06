---
name: write-canonical-pointer
description: Write/update a canonical-pointer (spec §2.3; DOC1 §7) — one per named body-of-work, a mutable head pointing at the current source-of-truth so a fresh incarnation never re-anchors on a stale draft. Writes .workshop-lite/ledger/pointers/<slug>.md. Use when the user types /write-canonical-pointer or asks to set/update the canonical source-of-truth for a body-of-work.
---

# /write-canonical-pointer

A **canonical-pointer** is **one per named body-of-work**: a **mutable head** that
names the current source-of-truth (a ref or path). Unlike forward-only records, it
is **updated in place** — re-invoking with the same `names` overwrites `points_to`
and re-stamps `updated_at`, so a fresh incarnation always resolves to the live
artifact rather than a stale draft. Carries `owner_user`.

## 1. Gather inputs

Required:
- **names** — the body-of-work this pointer is the head for (becomes the slug id).
- **points-to** — ref | path of the current source-of-truth.
- **updated-by** — the calling member's `@id`.

Optional:
- **owner-user** — defaults `user/local`.

## 2. Write / update the pointer

```bash
.venv/bin/python3 .claude/scripts/dev-mgmt/cli.py write-canonical-pointer \
    --names "<body-of-work>" \
    --points-to "<ref|path>" \
    --updated-by "@<member>" \
    [--owner-user "<owner>"]
```

Same `names` ⇒ same slug ⇒ the same file is updated in place (mutable head). The
writer validates required fields, writes the file, and re-renders the INDEX.
