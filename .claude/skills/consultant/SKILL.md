---
name: consultant
description: Spawn a multi-turn ephemeral LLM consultant via the parley substrate — wraps `parley member spawn --role-kind consultant` with first-turn / continuation / departure forms. The consultant runs in an ephemeral worktree (auto-cleanup on depart per parley cohort HH chunk-3), with a per-turn /context envelope (chunk-4 HARD-HALT at the configured threshold), persisting growing-body turns into a Review entity (chunk-6 schema extension). Use when the user types `/consultant <agent-type> "<charter>"`, `/consultant --continue <id> "<followup>"`, or `/consultant --depart <id> "<final-note>"`. v1 supports agent-type ∈ {claude_code, codex}; gemini reserved (Phase 5); antigravity scaffolded for re-target per cohort HH chunk-0 G-2 deferral.
---

# /consultant

When the user invokes one of the three forms below, run the matching flow.

**Sub-area**: Cohort HH par:2026-06-04-03 Shape E — workshop-lite-side SKILL composing the parley consultant primitive (chunks 1-4 substrate; chunk-6 Review-entity convention).

## 0. Invocation forms

| Form | Trigger | Effect |
|------|---------|--------|
| First-turn | `/consultant <agent-type> "<charter>"` | Spawns a fresh consultant member; captures first response; opens a `status: open_consult` Review entity. |
| Continuation | `/consultant --continue <consultant-id> "<followup>"` | Sends followup to live consultant; captures response; appends `## Turn N` to the Review entity; increments `turns`. |
| Departure | `/consultant --depart <consultant-id> "<final-note>"` | Sends `[depart]` signal; chunk-3 worktree cleanup fires; Review entity is sealed (`status: closed_consult` + `## Closing summary`). |

## 1. First-turn flow — `/consultant <agent-type> "<charter>"`

### 1.1 Inputs

Required positional:

- **agent-type** — `claude_code` (alias: `claude`) or `codex`. Reject others with a clear diagnostic (gemini Phase 5 / antigravity scaffolded).
- **charter** — free-text charter prompt (multi-paragraph OK; use `--charter-stdin` for piped input).

Optional:

- `--cwd PATH` — consultant's working dir (default: current repo root via `git rev-parse --show-toplevel`).
- `--review-slug TEXT` — explicit slug for the Review entity filename (default: derived from charter first sentence; kebab-cased).
- `--linked-msg-id MSG-ID` — repeatable; parley msg-ids carrying the call context.
- `--linked-decisions IDS` — comma-separated decision ids.
- `--token-budget INT` — per-turn `/context` envelope budget in tokens (overrides chunk-4 default).
- `--max-turns INT` — hard cap on turn count (default 10; exceeded = auto-depart with `closing_reason: max_turns`).
- `--instructions TEXT` — extra instructions appended to the spawn-time charter (default empty).

### 1.2 Steps

1. **Validate inputs**: agent-type ∈ {claude_code, codex}; charter non-empty.
2. **Resolve sid**: `parley whoami` → parse `.session.sid` from the JSON output. The skill must be invoked from a parley member pane (a window registered in an active session).
3. **Compose member-id**: `consultant-<YYYY-MM-DD>-<NN>-<slug>` where NN auto-increments via a scan of `docs/reviews/INDEX.md` for entries with the same `YYYY-MM-DD` prefix + `consultant-` infix; slug derived from `--review-slug` or the kebab-cased charter first sentence (truncated 40 chars).
4. **Spawn consultant member**:
   ```sh
   parley member spawn "$MEMBER_ID" \
     --agent-type "$AGENT_TYPE" \
     --role-kind consultant \
     --tier trusted \
     --cwd "$CWD" \
     --ephemeral \
     --ephemeral-ttl-h 2 \
     --instructions "$(printf 'You are a consultant on the following charter:\n\n%s\n\n%s\n\nWhen the charter is complete, post a final response and emit `[depart]` to close.' "$CHARTER" "$EXTRA_INSTRUCTIONS")"
   ```
   The `--ephemeral` flag composes with the chunk-3 worktree lifecycle (`spawn_worktree_for_consultation` runs implicitly via session.spawn_member when role_kind=consultant; cleanup_worktree_on_depart fires on depart). Chunk-4 envelope tracking auto-attaches for role_kind=consultant members.
5. **Wait for first-turn response**: poll `parley read --member @$MEMBER_ID --since cursor --kind chat --bodies full --limit 50` at 5s intervals until either:
   - first non-system chat record from `@$MEMBER_ID` is captured, OR
   - 90s timeout, OR
   - a `Kind.CONSULTANT_ENVELOPE_EXCEEDED` event fires for this member-id (treat as turn-1 truncation; proceed to step 6 with partial capture).
6. **Open Review entity** at `docs/reviews/<YYYY-MM-DD-NN-consultant-<slug>>.md` with frontmatter:
   ```yaml
   ---
   id: <YYYY-MM-DD-NN-consultant-<slug>>
   type: review
   review_type: consultant
   title: "Consultant <slug>: <one-line charter summary>"
   status: open_consult            # chunk-6 schema extension
   turns: 1                         # chunk-6 schema extension
   consultant_id: "@$MEMBER_ID"     # chunk-6 schema extension
   consultant_agent_type: "$AGENT_TYPE"  # chunk-6 schema extension
   linked_msg_ids: [...]            # from --linked-msg-id
   linked_decisions: [...]
   created_at: "<iso-8601>"
   author: "<caller-member-id from parley whoami>"
   ---

   ## Turn 1 — <iso-8601-utc>

   **Charter prompt**:

   <CHARTER>

   **Consultant response**:

   <CAPTURED_TEXT>
   ```
7. **Refresh `docs/reviews/INDEX.md`** with the new entry (status=open_consult; consultant_id; turns=1).
8. **Output to operator**:
   - `consultant_id: @$MEMBER_ID`
   - `review_path: docs/reviews/<id>.md`
   - First-turn response (first 2000 chars; truncate with continuation hint).
   - Continuation invocation hint: `/consultant --continue @$MEMBER_ID "<your followup>"`.

## 2. Continuation flow — `/consultant --continue <id> "<followup>"`

### 2.1 Inputs

- **id** — the consultant_id from a prior `/consultant` invocation (with or without leading `@`).
- **followup** — followup prompt body.

### 2.2 Steps

1. **Validate**: Review entity exists at `docs/reviews/<id-derived-from-consultant-id>.md`; frontmatter `status: open_consult`; consultant member alive (`parley members | grep <id>`); current `turns` < `--max-turns` cap.
2. **Send followup**: `parley say --member @<id> "<followup>"` (single-positional form, body via `--stdin` if it contains `@` or backticks).
3. **Wait for response**: same polling pattern as §1.2 step 5 (5s interval, 90s timeout, `CONSULTANT_ENVELOPE_EXCEEDED` watch).
4. **Append to Review entity**: `## Turn N — <iso-8601-utc>` section with `**Followup**:` + `**Consultant response**:` subsections. Increment frontmatter `turns: N`.
5. **Refresh INDEX**: bump `turns` count.
6. **Output**: turn-N response + new turn count + continuation hint.

## 3. Departure flow — `/consultant --depart <id> "<final-note>"`

### 3.1 Inputs

- **id** — consultant_id.
- **final-note** — closing note appended to `## Closing summary` (free-text; optional rationale or thanks).

### 3.2 Steps

1. **Validate**: consultant alive; Review status=open_consult.
2. **Send depart signal**: `parley say --member @<id> "[depart] <final-note>"`. The consultant_base ABC `handle_consultation_done` triggers on `[depart]` marker (chunk-1 substrate).
3. **Wait for chunk-3 cleanup**: poll `parley events --kind consultant_worktree_cleaned --member @<id>` until the cleanup audit record appears (max 30s).
4. **Synthesize closing summary**: read all `## Turn N` sections from the Review entity; compose a `## Closing summary` section. v1: simple turn-aggregator (concatenate response bodies with section markers + final-note as the trailing paragraph). LLM-class summary deferred to chunk-6 wsl-plan design.
5. **Seal Review entity**: flip frontmatter `status: closed_consult`; append `## Closing summary` + `## Departure metadata` (final-note, consultant_id at depart, total turns).
6. **Refresh INDEX**: status=closed_consult; final turns count.
7. **Output**: "Consultant @<id> departed; Review sealed at <path>; <N> turns; final-note: <note>".

## 4. HR-#1 boundary discipline

This SKILL.md is workshop-lite-side. It NEVER imports parley as a Python module. All parley invocations are subprocess shells via the `parley` CLI binary on `PATH`.

Verification (run from workshop-lite repo root — targeted source dirs only, mirroring parley HR-#1's `parley/ tests/` targeting; `.venv/` and `*.egg-info/` are vendor/install artifacts and OUT of scope):

```sh
grep -rEn --exclude-dir=__pycache__ --exclude='*.pyc' \
    '^\s*(import|from)\s+parley' \
    bin/ tests/ .claude/ personas/ docs/
echo "exit=$?"
```

Expected: `exit=1` (zero matches across the workshop-lite source dirs; the architectural seam — workshop-lite module-level code never imports parley — is the HR-#1 dual).

This recipe mirrors the parley HR-#1 ccweb-clean canonical form (refined cohort C D3 from substring to line-anchored Python-import-only) to protect against doc-comment false-positives + binary-bytecode hits. Targeting specific source dirs (rather than the full repo tree) follows parley HR-#1's own pattern (which targets `parley/ tests/` only, NOT `.` or `.venv/`).

## 5. Envelope discipline (chunk-4)

The chunk-4 `/context` envelope auto-fires:

- `Kind.CONSULTANT_ENVELOPE_WARNING` at `pct_warn` threshold (default 0.50).
- `Kind.CONSULTANT_ENVELOPE_EXCEEDED` at `pct_halt` threshold (default 0.60) — HARD-HALT-depart (triggers chunk-3 `cleanup_worktree_on_depart`).

The skill does NOT need to handle envelope-exceeded explicitly; it gets a normal depart audit trail. The polling loops in §1.2/§2.2/§3.2 SHOULD watch for these Kinds and surface them to the operator via stderr.

## 6. Cross-substrate dependencies

Hard pre-conditions:

- **Parley chunks 1-4 LANDed on main** (cohort HH par:2026-06-04-03 ship-epic). Without this the `parley member spawn --role-kind consultant` invocation returns "Invalid value for '--role-kind': 'consultant' is not one of …" because the canonical install's `RoleKind` Literal doesn't include `consultant`.
- **Chunk-6 Review-entity schema extension LANDed on workshop-lite** (cohort HH chunk-6 wsl-side land). Without this, workshop-lite's review schema validator rejects the new frontmatter keys (`status: open_consult`, `turns`, `consultant_id`, `consultant_agent_type`).

Both dependencies are tracked via cross-substrate xrequest entries; this SKILL.md is a no-op until both LAND.

## 7. Errors / edge cases

- **agent-type=gemini** — reject with diagnostic citing Phase 5 + cohort HH chunk-0 G-2 deferral. Suggest `antigravity` retry once that adapter is_ready.
- **Member-id collision** (NN already used) — retry with NN+1; log the auto-bump.
- **Spawn failure** (e.g. CC cold-start timeout) — clean up partial Review entity by flipping status to `spawn_failed`; surface to operator with retry hint.
- **Worktree creation failure** (chunk-3 `spawn_worktree_for_consultation` raises) — surface + abort; do NOT register member; no Review entity opened.
- **Envelope-exceeded mid-turn** — respect chunk-4 HARD-HALT; final response capture via `parley read --since cursor --kind chat --member @<id>` after the HALT event; seal Review with `closing_reason: envelope_exceeded` in `## Departure metadata`.
- **Operator-initiated kill** (`parley member remove @<id>`) — chunk-3 cleanup fires; Review entity should be flipped to `status: closed_consult_aborted` by a manual `/consultant --depart` invocation (or by a depart-audit hook in a later cohort).
- **Max-turns hit** — auto-depart with `closing_reason: max_turns`; surface to operator.

## 8. References

- Parley cohort HH charter: `parley/docs/inbox/2026-06-06-cohort-HH-par-04-03-consultant-skill-primitive-charter.md`
- Parley HR-#1 canonical recipe: `parley/CLAUDE.md` §"Hard rules — do not violate" #1
- Parley adapter ABCs (chunk-1): `parley/adapters/base.py` `start_consultation_turn` / `await_response` / `handle_consultation_done`
- Parley `role_kind=consultant` (chunk-2): `parley/sidecar/roster.py:272` + `parley/substrate/visibility_defaults.py:358`
- Parley worktree lifecycle (chunk-3): `parley/sidecar/consultant_lifecycle.py`
- Parley envelope (chunk-4): `parley/sidecar/consultation_envelope.py`
- Workshop-lite `/consult` (sibling skill): `workshop-lite/.claude/skills/consult/SKILL.md`
- Workshop-lite Review schema (chunk-6 extension): TBD chunk-6 LAND
