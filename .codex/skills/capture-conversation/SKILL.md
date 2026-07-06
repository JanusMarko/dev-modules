---
name: capture-conversation
description: Capture a parley scrollback range as a durable Conversation entity in the lightweight dev-mgmt system. Writes docs/conversations/<id>.md with two-section body (curated summary + sender-attributed verbatim) and frontmatter per §6 + D22-D27. Use when the user types /capture-conversation or asks to snapshot a chat range as a durable artifact.
---

# /capture-conversation

When the user invokes `/capture-conversation`, run this flow.

## 1. Gather inputs

Required:

- **topic** — short slug for the filename (e.g., `sprint-5-brief-and-qa`).
- **title** — human-readable title (e.g., `"Sprint 5 brief and Q&A"`).
- **since-msg-id** — parley msg-id where the captured range starts. (`parley get --since` is *strictly after* this id, so it's the LAST msg before the range — the first message in the captured dump will be the one immediately following.)

Optional:

- **until-msg-id** — last msg in the range. If omitted, **D22** says the SKILL layer discovers the current chat-end at capture time (see §2). The captured `verbatim_msg_range` always has both endpoints.
- **participants** — list of `@<id>`. **D24**: auto-derived from unique `from` values in the records if omitted.
- **zone** — `sprint` | `cross-sprint` | `pre-sprint`. **D25**: auto-detected from active sprint folder if omitted (`sprint` if `docs/sprints/active/sprint-*/` exists, else `cross-sprint`).
- **sprint-id** + **stage** — required when `zone=sprint`; paired (both set or both null).
- **body** / **body-from-file** — curated summary content (precedence: `--body` > `--body-from-file` > placeholder `_curated summary pending_`).
- **linked-design-docs**, **linked-decisions**, **linked-reviews**, **linked-issues**, **linked-handoffs**, **linked-msg-ids** — comma-separated outbound cross-links (**D26** — Sprint 5 only writes outbound links; inbound mutation deferred to Sprint 7's `cross_links.py`).

If any required input is missing or ambiguous, use `AskUserQuestion` to collect.

## 2. Parley shell-out (the parley-coupling layer per D27)

The helper lib is parley-agnostic — it never imports parley or shells out to it. The SKILL layer owns the parley call and pipes the JSON-lines output into the CLI's records-json mode, which renders the verbatim section via the parley-agnostic dict-processor.

**Stream the captured range (D48 canonical pattern):**

`parley get` has **no `--until` flag** (D48 / issue `2026-05-14-06` — the earlier `--until` shape was never implemented in parley). The canonical capture is `--since <start>` through the current chat-end, with `--all` to disable the default 50-record `--limit` so the whole range lands. The dev-mgmt CLI auto-discovers the actual range endpoints from the captured records (`verbatim_msg_range` = first/last record id, **Q3** — captured range, not caller args), so no explicit range-end argument is needed.

```bash
parley get --since <since-msg-id> --all --kind chat --json --full
```

Each line is one record with fields `id`, `ts`, `from`, `raw`, plus `kind=chat`. The CLI handles the rendering — pipe stdin directly:

**Bounded mid-history sub-range (no chat-end upper bound).** `--since X --all` captures `X` through the *current chat-end* — there is no first-class way to cap the range at an arbitrary mid-history end msg-id (`parley get` has no `--until`/`--through`; tracked for a potential parley feature in issue `2026-05-15-08`). When you need a conversation that ends well before chat-end (a bounded historical slice), the canonical escape hatch is to slice the parley substrate transcript directly by msg-id line range and feed it into records-json mode (the lib is parley-agnostic and only cares about the JSON-lines shape, so this is equivalent to `parley get --json --full` but upper-bounded):

```bash
CHATLOG=~/.parley/sessions/<sid>/chat.jsonl
# FAIL LOUD if the end msg-id is absent/typo'd/from another session:
# awk's /start/,/end/ range NEVER CLOSES if <end-msg-id> is not present,
# silently emitting start-through-EOF = the exact unbounded capture this
# escape hatch exists to prevent. Guard first (msg-ids are fixed-length +
# substring-unique, so a bare grep is sufficient and is robust to
# JSON-whitespace unlike a "id":"..."-shaped match):
grep -q "<end-msg-id>" "$CHATLOG" || { echo "end msg-id not found in $CHATLOG — aborting (would silently capture through chat-end)" >&2; exit 2; }
# everything from the FIRST line containing <start-msg-id> through the
# line containing <end-msg-id>, kind==chat only, into records-json mode
awk "/<start-msg-id>/,/<end-msg-id>/" "$CHATLOG" \
  | python3 -c "import sys,json;[print(l.rstrip()) for l in sys.stdin if (json.loads(l).get('kind')=='chat')]"
```

The dev-mgmt CLI then auto-discovers `verbatim_msg_range` from the actually-captured first/last records exactly as in the chat-end case (Q3). (`<start-msg-id>`-not-found is already safe — it yields an empty slice and the post-W2.1 records-json guard fail-louds on the empty result; only `<end-msg-id>`-not-found needed the explicit guard above, since an unclosed awk range fails *silently* in the dangerous over-capture direction.) This is the workaround a future operator would otherwise rediscover cold; it is documented here deliberately, fail-loud-on-typo per the W2.1 contract this arc established.

## 3. Write the conversation

From the repo root, invoke the CLI in **records-json mode** (recommended):

```bash
parley get --since <since-msg-id> --all --kind chat --json --full \
    | .venv/bin/python3 .claude/scripts/dev-mgmt/cli.py capture-conversation \
        --title "<title>" \
        --topic "<topic>" \
        [--participants "@a,@b,@c"] \
        [--zone sprint|cross-sprint|pre-sprint] \
        [--sprint-id "<id>" --stage plan|execute|retro] \
        [--body "<curated summary>" | --body-from-file "<path>"] \
        [--linked-decisions "<csv>"] \
        [--linked-issues "<csv>"] \
        [--linked-msg-ids "<csv>"] \
        --verbatim-records-json-from-stdin
```

In records-json mode the CLI:
- reads parley JSON-lines from stdin
- calls `entities._render_parley_verbatim(records)` (parley-agnostic; just dict-processing) to produce the markdown verbatim section
- auto-fills `verbatim_msg_range` = `[first_record.id, last_record.id]` (**Q3** — captured range, not caller args)
- auto-fills `started_at` / `ended_at` from first / last record `ts`
- **D24**: auto-derives `participants` from unique `from` values if `--participants` not passed
- **D25**: auto-detects `zone` from active-sprint presence if `--zone` not passed

**Alternative modes** (when you already have rendered verbatim text):
- `--verbatim "<text>"` — inline pre-rendered verbatim section
- `--verbatim-from-file <path>` — pre-rendered verbatim section from file
- `--verbatim-from-stdin` — pre-rendered verbatim section from stdin

In non-records-json modes, you must pass `--verbatim-msg-range "msg-first,msg-last"` (or empty for `[null, null]`) and `--started-at` / `--ended-at` explicitly.

The CLI:
- auto-generates the id (`YYYY-MM-DD-NN-<slugified-topic>` per **D15**)
- validates the frontmatter against the §6 + D22/D24/D25 Conversation schema
- writes `docs/conversations/<id>.md` with the two-section body (`## Curated summary` + `## Verbatim chat (sender-attributed)`) per **D23**
- atomically re-renders `docs/conversations/INDEX.md`
- prints the written path on stdout

A `ValidationError` exits non-zero and writes nothing. Common causes:
- `--zone` outside `{sprint, cross-sprint, pre-sprint}`
- `--zone sprint` without `--sprint-id` or `--stage`
- A participant entry missing the leading `@`
- `verbatim_msg_range` not exactly 2 elements

## 4. Report back

Tell the user:

- the path to the written conversation
- the auto-generated conversation id
- a one-line summary (zone, participant count, message count, range)
- any cross-links recorded so the user knows the provenance is captured

## Notes

- **D22 + D48 (msg-range)**: `--since` (start msg-id) is the only range argument. Per **D48** (issue `2026-05-14-06`) the old `--until-msg-id` was dropped from the canonical flow — `parley get` never implemented `--until`; use `--all` to capture `--since` through chat-end. The captured `verbatim_msg_range` records the ACTUAL first/last msg-ids in the dump (not the caller args), per **Q3** — the CLI auto-discovers endpoints from the records list, so no range-end argument exists.
- **D23 (two-section body)**: `## Curated summary` (caller content) + `## Verbatim chat (sender-attributed)` (auto-rendered from records). Each verbatim record renders as `### @<from> · <msg-id> · <iso_ts>` followed by the raw body. Resolves design §12 Q2.
- **D24 (participants auto-derive)**: from unique `from` values in records; `--participants` override available.
- **D25 (zone auto-detect)**: active-sprint present → `sprint`; else `cross-sprint`. `pre-sprint` is reserved for the pre-Sprint-1 design conversation (captured in the design doc itself).
- **D26 (cross-link auto-discovery deferred)**: Sprint 5 only writes OUTBOUND links from the conversation's frontmatter. Walking other entities to update their `linked_*` arrays with this conversation's id is `cross_links.py` work (Sprint 7). Resolves design §12 Q6.
- **D27 (parley-coupling at SKILL layer)**: the helper lib stays parley-agnostic per CLAUDE.md Hard Rule 5. The parley shell-out happens in this SKILL.md flow; the CLI's records-json mode runs a pure dict-processor. Tests assert no `parley` imports or shell-outs in lib modules.
- **D15 (id convention)**: `YYYY-MM-DD-NN-<slug>` (per-day counter), content-keyed.
- **Workshop importability**: every frontmatter field maps to a Workshop entity column (per CLAUDE.md Hard Rule 6).
- **Empty-range edge case**: if `parley get` returns no records for the requested range, `verbatim_msg_range` is `[null, null]` and the verbatim section says `(no records in this range)`. Validator allows this explicit-empty form.
- **Parley-agnostic base**: although /capture-conversation is most useful in a parley session, the lib + CLI work in a solo CC session too if the caller pre-renders the verbatim section (use `--verbatim` / `--verbatim-from-file`).
