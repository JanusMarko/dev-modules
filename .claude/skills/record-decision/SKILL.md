---
name: record-decision
description: Record a Decision entity in the lightweight dev-mgmt system. Captures title, rationale, options, scope, author and provenance into docs/decisions/<id>.md and refreshes decisions/INDEX.md. Use when the user types /record-decision or asks to log a decision.
---

# /record-decision

When the user invokes `/record-decision`, run this flow.

## 1. Gather inputs

Required:

- **title** — short imperative summary of what was decided
- **rationale** — why this option was chosen (becomes the body)
- **options** — each option needs `label`, `chosen` (bool), `reasoning` (string; may be empty)
- **scope** — one of:
  - `design:<doc-name>` — design-level decision
  - `sprint:<sprint-id>` — sprint-internal decision
  - `repo:<area>` — codebase-wide decision

Optional:

- **status** — `accepted` (default) | `rejected` | `superseded` | `open`
- **sprint_id** — set if scope=sprint
- **stage** — `plan` | `execute` | `retro` (only when scope=sprint)
- **supersedes** — id of a prior decision being overridden
- **linked_msg_ids** — parley msg-IDs that produced this decision (durable provenance)
- **authored_with** — comma-separated co-author @ids

If any required input is missing or ambiguous, use `AskUserQuestion` to collect.

## 2. Determine author

- If in a parley session, run `parley whoami` and use the member's `id` (prefixed with `@`).
- The `--author` field is the calling member; co-deciders go in `--authored-with`.
- If the decision was made over a parley conversation, capture the relevant message IDs in `--linked-msg-ids`.

## 3. Write the decision

From the repo root, invoke the CLI:

```bash
.venv/bin/python3 .claude/scripts/dev-mgmt/cli.py record-decision \
    --title "<title>" \
    --rationale "<rationale>" \
    --scope "<scope>" \
    --options-json '<json array>' \
    --author "@<member>" \
    [--authored-with "@a,@b"] \
    [--linked-msg-ids "msg-x,msg-y"] \
    [--sprint-id "<sprint-id>"] \
    [--stage plan|execute|retro] \
    [--supersedes <decision-id>] \
    [--status accepted|rejected|superseded|open]
```

If the repo doesn't have a `.venv/`, fall back to `python3` (PyYAML must be available).

The CLI:
- auto-generates the id (`YYYY-MM-DD-NN-<slug>` with per-day counter)
- validates the frontmatter against the §6 Decision schema
- writes `docs/decisions/<id>.md`
- atomically re-renders `docs/decisions/INDEX.md`
- prints the written path on stdout

A ValidationError exits non-zero and writes nothing.

## 3a. Dual-recording (4.6i) — the funnel

When the decision must land in BOTH stores (the parley `Kind.DECISION`
store AND the wl markdown), use the dual-recording funnel instead of the
raw CLI:

```python
import sys; sys.path.insert(0, ".claude/skills/record-decision")
from funnel import record_decision_dual
out = record_decision_dual(title=..., rationale=..., options=[...],
                           scope=..., author="@<member>", ...)
# out = {mode, entity_path, canonical_path, parley_msg_id}
```

The funnel is the **skill layer** (parley-coupling lives here only, per
CLAUDE.md Hard Rule 1 + D27 — never in the lib). It:

- writes the rich §6 WL decision entity via the lib **unchanged** (the
  WL-native, Workshop-importable superset);
- extracts the **one canonical record** (the deterministic §6 embedding,
  `canonical_decision.extract_canonical`);
- always materialises the **canonical-projection artifact**
  (`<id>.canonical.md`) via the lib's byte-identical
  `project_decision_markdown` (conformance-locked to parley's projection
  at a recorded pinned rev — see
  `tests/test_canonical_decision_conformance.py`);
- emits the **parley `Kind.DECISION` store IFF parley is present**
  (presence-aware / independently-degrading: parley absence silently
  skips it with zero degradation to the wl artifacts, and vice-versa);
- on parley-present, records the parley msg-id into the §6 entity's
  `linked_msg_ids` (the §6 provenance bidirection backref) and passes
  `dev-mgmt://<slug>` for the parley side's `external_decision_refs`.

Hard Rule 2: the funnel only *calls* the parley decision verb and writes
wl-cwd itself — parley never writes wl-cwd; the funnel never writes
parley-cwd.

## 4. Report back

Tell the user:

- the path written
- the auto-generated decision id
- a one-line summary of what was recorded

If `scope` starts with `sprint:`, you MAY also offer to cross-link from the sprint's `plan.md` — but this is deferred for Sprint dev-mgmt.1 and may be skipped silently.

## Notes

- The lightweight dev-mgmt system is markdown-only today; frontmatter maps 1:1 to Workshop entity columns for future Refinery import (see `LIGHTWEIGHT-DEV-MGMT-SYSTEM.md` §10).
- This skill is parley-agnostic at its base — it works for a solo CC session in a fresh repo too, as long as a `docs/decisions/` write target exists.
