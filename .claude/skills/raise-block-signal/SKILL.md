---
name: raise-block-signal
description: Raise a block-signal (spec §2.3; DOC1 §6.3) — the runtime block. Two classes only — HALT (human-cleared, may wait indefinitely) and wait_for (bounded, TTL required). Writes .workshop-lite/ledger/block-signals/<id>.md. Use when the user types /raise-block-signal or asks to record a runtime block on a work-item.
---

# /raise-block-signal

A **block-signal** is the runtime block (distinct from a `gate`, which is a
cross-session hold). Two classes only (§11.5):

- **HALT** — "genuinely stuck," cleared only by a **human** `unblock`; the *only*
  block that may wait indefinitely (held safe by a loud standing surface). A
  top-level `HALT.md` is the reference instance of this class. **No `ttl`.**
- **wait_for** — awaiting an event/dependency; `release`d on arrival; bounded by
  a **required `ttl`** → `expired` on timeout. Indefinite wait is forbidden.

block-signal does NOT carry `owner_user` (transient runtime signal; `created_by` only).

## 1. Gather inputs

Required:
- **blocked-subject** — ref to the blocked work-item.
- **waits-on** — the ref | event | condition the block awaits.
- **class** — `HALT` | `wait_for`.
- **created-by** — the calling member's `@id`.

Conditional / optional:
- **ttl** — **REQUIRED for `wait_for`**, **must be ABSENT for `HALT`**.
- **deadline**, **inferred-by**, **status** (`raised` default | `resolved` | `expired`).

## 2. Raise the signal

```bash
.venv/bin/python3 .claude/scripts/dev-mgmt/cli.py raise-block-signal \
    --blocked-subject "<ref>" \
    --waits-on "<ref|event|condition>" \
    --class HALT|wait_for \
    --created-by "@<member>" \
    [--ttl "<duration>"]   # required iff class=wait_for \
    [--deadline "<ts>"] [--inferred-by "<text>"] [--status raised|resolved|expired]
```

The validator enforces the class/ttl invariant (wait_for needs a ttl; HALT must
not have one) and rejects any `owner_user`.
