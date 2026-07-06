---
name: auto-decision-doc
description: v1-AUTO — auto-file a workshop-lite Decision entity from a parley message body containing a "CTO RATIFY" (or equivalent) trigger and a decision-shape (numbered options + chosen option + rationale). v1-AUTO (cohort C D2) adds a `decision_shape` classifier (go-no-go | select-from-n | ratify-direction | deferral | ambiguous) auto-populated into §6 frontmatter. Wraps `/record-decision`'s dual-recording funnel; writes own cwd only (Hard Rule 2). Use when the user types `/auto-decision-doc` or asks to file a CTO ratification from chat.
---

# /auto-decision-doc

When the user invokes `/auto-decision-doc`, run this flow.

## Scope — v1-AUTO categorization (operator-invoked)

Per @plan ratification msg-1c6f11784c82 (charter: `docs/inbox/2026-05-23-stop-stopping-priority-backlog.md` item 1) + cohort C D2 maturation (par-plan PG-2 ratify msg-6a1d48fbe0a7 / D2 Shape (β) ratify msg-35dfa0551a29):

- **Operator-invoked**: caller (the member whose work was ratified) invokes this skill manually with a parley msg-id whose body contains the CTO ratification. Hook auto-trigger remains deferred — "v1-AUTO" names the SHAPE-categorization maturation, NOT a hook.
- **v1-AUTO categorization** (D2): the detector auto-classifies a `decision_shape` ∈ {go-no-go, select-from-n, ratify-direction, deferral, ambiguous} per the body's option-count + chosen-marker resolution + deferral-keyword presence (see `detect.classify_decision_shape`). The classified shape is written into the §6 entity's `decision_shape` frontmatter field (§6 schema spec: `docs/design/LIGHTWEIGHT-DEV-MGMT-SYSTEM.md` §6 Decision).
- **Hard Rule 2**: the skill writes ONLY the member's own cwd. The CTO does not file; a member running in a non-target cwd does not file. The member whose work was ratified files in own repo.

### Fast-path on confidence=high (D2 SKILL.md amend)

When the detector's `confidence == "high"` AND the classified `decision_shape` is in the non-`ambiguous` set, the operator-facing flow biases toward direct auto-file:

- **Skip** the `--dry-run` preview round-trip (the detection is high-confidence; the shape is unambiguous; title + rationale + options + shape are all auto-resolved).
- **Skip** the `AskUserQuestion` gather step for the optional fields (`--title-override` / `--rationale-override` / `--decision-shape-override`).
- File directly via `cli.py` with `--min-confidence high` and no overrides.

Use `--decision-shape-override <value>` only when the operator has REASON to disagree with the classifier (rare; the detector is grounded in the body shape).

Fall back to the manual-interactive flow (next sections) when:
- `confidence` is `low` / `medium` (the detector is unsure),
- `decision_shape` resolves to `ambiguous` (shape unresolvable from the body),
- `status` returns `no_trigger` (no ratification pattern at all),
- the operator explicitly wants a preview pass.

## 1. Gather inputs

Required:

- **msg-id** — the parley `msg-XXXX` whose body carries the ratify (used as provenance + idempotency key)
- **body** — the ratify message text (read via `--from-file` or piped through `--stdin`; ALWAYS prefer file/pipe — never paste body into a shell arg, the backtick-corruption footgun applies)
- **scope** — one of: `design:<doc>`, `sprint:<id>`, `repo:<area>` (heuristic detection is unreliable; require explicit scope for v1)
- **author** — calling member's id (run `parley whoami` and use the `id` prefixed with `@`)

Optional:

- **authored-with** — comma-separated co-author @ids (typically `@plan` if the CTO ratified)
- **title-override** — pass when detection's heuristic title is wrong (RECOMMENDED for non-fast-path — detection is best-effort)
- **rationale-override** — pass when the auto-extracted rationale is thin
- **decision-shape-override** — cohort C D2 v1-AUTO: override the auto-classified shape (default: use the detector's classification). Choices: `go-no-go` | `select-from-n` | `ratify-direction` | `deferral` | `ambiguous`
- **dry-run** — parse + report; do NOT write (skipped by default on fast-path)
- **min-confidence** — `low` | `medium` | `high` (default `medium`)

If any required input is missing or ambiguous, use `AskUserQuestion` to collect. On the fast-path (confidence=high + non-ambiguous shape), skip this gather step.

## 2. Fetch the body if needed

If you have the msg-id but not the body, fetch it via `parley get`:

```bash
parley get --full --since <prior-msg-id> | grep -A 100 <msg-id>
```

Or pull the message directly from `chat.jsonl`. Then pipe into the CLI via `--stdin`.

## 3. Dry-run first

Strongly recommended: preview before filing.

```bash
.venv/bin/python3 .claude/skills/auto-decision-doc/cli.py \
    --msg-id "<msg-XXXX>" \
    --scope "<scope>" \
    --author "@<member>" \
    --authored-with "@plan" \
    --from-file /tmp/ratify-body.md \
    --dry-run
```

The output is JSON. Inspect:

- `status` — `dry_run` (preview only), `no_trigger`, `low_confidence`, `already_filed`
- `detection.confidence` — `low` | `medium` | `high`
- `detection.title` — sanity-check; override via `--title-override` if wrong
- `detection.options` — verify the options list + chosen marker
- `detection.rationale` — verify; override if thin

If detection mis-parses anything, override with explicit `--title-override` / `--rationale-override`.

## 4. File

Re-run without `--dry-run` and with any overrides:

```bash
.venv/bin/python3 .claude/skills/auto-decision-doc/cli.py \
    --msg-id "<msg-XXXX>" \
    --scope "<scope>" \
    --author "@<member>" \
    --authored-with "@plan" \
    --from-file /tmp/ratify-body.md \
    --title-override "<corrected title if needed>"
```

`status: filed` indicates:

- §6 Decision entity written to `docs/decisions/<YYYY-MM-DD-NN-slug>.md`
- canonical-projection artifact at `docs/decisions/<id>.canonical.md`
- parley `Kind.DECISION` store emitted IFF parley is present (`mode: both`); otherwise `mode: standalone-wl`
- idempotency ledger appended at `docs/decisions/.auto-filed-msgs.jsonl`
- `INDEX.md` refreshed

If you re-run with the same `--msg-id`, you'll see `status: already_filed` and the prior decision-id (no double-file).

## 5. Report back

Tell the user:

- the written entity path + auto-generated decision id
- the funnel `mode` (`both` vs `standalone-wl`)
- the parley msg-id (if `mode: both`) so the §6 provenance bidirection is visible
- a one-line summary of what was filed

If the user is in the parley dev-mgmt session, consider also posting a brief `parley say` to @plan confirming the filing — this closes the loop on the original ratification.

## Detection contract (regex + shape)

**Triggers** (`detect.TRIGGER_PATTERNS`, case-insensitive):

- `CTO RATIFY` / `CTO RATIFIED` / `CTO RATIFICATION`
- `RATIFIED`
- `GREENLIGHT` / `GREEN-LIGHT` / `GREENLIGHTED`
- `APPROVED`

**Options** (lines):

- `^\s*(?:Option\s+)?N[:.)\]\-—]\s+...$` where N is `1`, `A`, `a`, `(a)`, etc.

**Chosen marker** — one of:

- Inline tag on an option line: `(chosen)`, `[chosen]`, `**chosen**`, `→ chosen`, `selected`, etc.
- Directive elsewhere in the body: `Chosen: N`, `RATIFY option N`, `Go with N`, `Pick: N` — cross-referenced against parsed option markers

**Rationale**:

- Paragraph following `Rationale:` / `Reasoning:` / `Why:` / `Because:` / `Justification:`
- Fallback: first non-option, non-trigger prose paragraph

**Confidence ladder**:

- `none`   — no trigger matched
- `low`    — trigger only (no parseable options or no resolvable chosen marker)
- `medium` — trigger + ≥1 option + chosen identifiable
- `high`   — trigger + ≥2 options + chosen + rationale

`--min-confidence medium` is the default. Set `--min-confidence low` to file thin-shape decisions (you'll likely need `--title-override` + `--rationale-override`).

## Idempotency

The ledger `docs/decisions/.auto-filed-msgs.jsonl` carries one JSONL record per filed msg-id:

```json
{"msg_id": "msg-abc", "decision_id": "2026-05-23-NN-slug", "entity_path": "docs/decisions/...md", "filed_at": "2026-...Z", "confidence": "high", "mode": "both"}
```

A second invocation with the same `--msg-id` returns `status: already_filed` without writing.

## Notes

- **Parley-coupling is at the skill layer only** — the dev-mgmt lib (`.claude/scripts/dev-mgmt/`) stays parley-agnostic per Hard Rule 1. The funnel + this skill are the only places parley calls are permitted.
- **Cross-repo write seam** (per @plan callout): the skill is deliberately a NO-OP for cross-cwd routing. Each member runs the skill in their own cwd; cross-repo decisions require the appropriate member to file in their own repo. Future hook variant may add a polite nudge to the target member.
- **Detection is heuristic** — always sanity-check the dry-run output before filing. Override fields liberally when human judgment beats regex.
