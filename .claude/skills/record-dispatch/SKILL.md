---
name: record-dispatch
description: Record a standing_dispatch entity in the workshop-lite dev-mgmt system — declares a load-bearing dispatch (charter, brief, governance directive, routing decision) that must remain front-of-mind across seat replacements until satisfied. Writes docs/dispatches/<id>.md, refreshes dispatches/INDEX.md, surfaces on SessionStart for named recipients, and supports satisfy / supersede transitions. Use when the user types /record-dispatch, /record-dispatch satisfy, /record-dispatch supersede, or asks to file/satisfy/supersede a standing dispatch.
---

# /record-dispatch

When the user invokes `/record-dispatch`, run one of three flows depending on the subcommand:

- `/record-dispatch <slug> --purpose <kind> --recipients <fqid,...> --expected "<short>" [...]`
- `/record-dispatch satisfy <id> [--by <fqid>] [--rationale "<short>"]`
- `/record-dispatch supersede <new-id> <old-id>`

The standing-dispatch entity codifies "this load-bearing dispatch (charter / brief / governance / routing) must remain front-of-mind across seat replacements until its recipients act on it." Closes charter §4 failure #5 (no standing-dispatch entity).

Read the binding sub-spec at `docs/design/2026-05-29-wl-standing-dispatch-spec.md` before running this skill — every field semantic + lifecycle decision + cross-arc contract is documented there.

## 1. Determine the author seat (parley-coupling lives HERE, per CLAUDE.md Hard Rule 1)

Run `parley whoami --json` to discover the calling member's id. Compose the `created_by` value as `@<member-id>` (bare member-id form, prefixed `@`). The skill layer derives this; the library never imports or shells out to parley.

If parley is NOT on PATH (solo CC session): fall back to `created_by = "@unknown"` and INFO log to stderr.

## 2. /record-dispatch (create a new dispatch)

### Gather inputs

Required:

- **slug** — short identifier for the dispatch (combined with date + per-day NN counter for the filename id)
- **purpose** — one of `charter | brief | governance | routing | other`
- **recipients** — comma-separated FQID list (per D-RA-4); multi-recipient by construction per D-WL-19 element 1. Each entry composes with one parley primitive #1 state machine
- **expected_outcome** — short free-text describing what counts as "satisfied"
- **scope** — one of `arc:<id>` / `sprint:<id>` / `repo:<area>` / `design:<doc>` / `decision:<id>`

Optional:

- **deadline** — ISO timestamp (process signal; INFO-only validator surface; missing it is not a structural drift)
- **expires-at** — ISO timestamp (structural; WARN past 24h grace per sub-spec §5.1)
- **linked-msg-id** — repeatable; the parley msg-ids carrying this dispatch (durable provenance)
- **linked-decisions** / **linked-handoffs** / **linked-reviews** — comma-separated entity ids
- **supersedes** — id of a prior dispatch this replaces (bidirectional `superseded_by`/`supersedes` refs auto-added; prior is flipped to `status: superseded`)
- **satisfy-quorum** — integer N; when N recipients ack, validator fires V5-QUORUM (sub-spec Q-SD-3)
- **sprint-id** + **stage** — paired (both set or both null); set when scope=sprint:<id>
- **title** — optional human-readable title (default derives from purpose + slug)
- **owner-user** — per D-RA-4; defaults `user/local`

If any required input is missing or ambiguous, use `AskUserQuestion` to collect.

### Write the dispatch

From the repo root, invoke the CLI:

```bash
.venv/bin/python3 .claude/scripts/dev-mgmt/cli.py record-dispatch \
    --slug "<slug>" \
    --purpose <charter|brief|governance|routing|other> \
    --recipients "<csv-fqids>" \
    --expected "<short outcome>" \
    --scope "<scope>" \
    [--deadline "<iso-ts>"] \
    [--expires-at "<iso-ts>"] \
    [--linked-msg-id "<msg-id>" ...] \
    [--linked-decisions "<csv>"] \
    [--linked-handoffs "<csv>"] \
    [--linked-reviews "<csv>"] \
    [--supersedes "<old-id>"] \
    [--satisfy-quorum N] \
    [--sprint-id "<id>" --stage plan|execute|retro] \
    [--created-by "@<seat>"] \
    [--owner-user "<user-id>"] \
    [--title "<human-readable>"]
```

If the repo doesn't have a `.venv/`, fall back to `python3` (PyYAML must be available).

The CLI:
- auto-generates the id (`<YYYY-MM-DD>-<NN>-<slug>` per sub-spec §3, matching Decision convention)
- auto-populates `parley_external_ref: workshop-lite-dispatch://<id>` per D-WL-19 element 2 (pre-confirmed cross-arc URI scheme — parley DecisionRecord.external_decision_refs may reference this dispatch via the URI)
- validates the frontmatter against the schema (`status` / `purpose` enums, `recipients` non-empty, scope prefix taxonomy)
- writes `docs/dispatches/<id>.md`
- atomically re-renders `docs/dispatches/INDEX.md` (sub-spec §8 layout: Standing / Satisfied (trailing Nd) / Superseded / Expired)
- prints the written path on stdout

**Idempotency** (sub-spec §9): if a `standing` dispatch already exists with the same scope + same exact recipients set + same purpose, the CLI returns the existing path without writing a new file. INFO to the user; no error.

A `ValidationError` exits non-zero and writes nothing.

### Optional: supersede an existing dispatch in one shot

Pass `--supersedes <old-id>` to the create call. The CLI:
- writes the new dispatch
- flips the prior to `status: superseded` with `superseded_by: <new-id>` in its frontmatter
- adds a `supersedes: <old-id>` ref to the new dispatch's frontmatter
- appends a "superseded" line to the old dispatch's body Lifecycle section

## 3. /record-dispatch satisfy <id>

Mark an existing standing dispatch as `satisfied` — typically because all named recipients have acted on it.

### Gather inputs

- **id** — the dispatch id (filename stem under `docs/dispatches/`)
- **by** (optional) — the seat FQID claiming satisfaction (captured in frontmatter `satisfied_by`)
- **rationale** (optional) — short free-form string captured in the lifecycle log

### Invoke

```bash
.venv/bin/python3 .claude/scripts/dev-mgmt/cli.py record-dispatch-satisfy \
    "<id>" \
    [--by "@<seat>"] \
    [--rationale "<short>"]
```

The CLI flips `status` from `standing` to `satisfied`, stamps `satisfied_at`, appends a transition log entry, and re-renders the INDEX. Idempotent: if the dispatch is already terminal (`satisfied` / `superseded` / `expired`), the CLI is a no-op and returns the existing path.

## 4. /record-dispatch supersede <new-id> <old-id>

Explicit supersede when the new dispatch was filed independently (not via `--supersedes` on create). Adds bidirectional `superseded_by`/`supersedes` refs.

### Invoke

```bash
.venv/bin/python3 .claude/scripts/dev-mgmt/cli.py record-dispatch-supersede \
    "<new-id>" "<old-id>"
```

Both ids must already exist under `docs/dispatches/`. The CLI:
- flips `<old-id>` to `status: superseded` with `superseded_by: <new-id>`
- adds `supersedes: <old-id>` to `<new-id>`'s frontmatter (if not already set)
- appends a "superseded" line to `<old-id>`'s body Lifecycle section
- re-renders the INDEX

Idempotent: if `<old-id>` is already terminal, the supersede is a no-op flip.

## 5. Composition with parley primitive #1 (sub-spec §10)

The standing-dispatch entity carries the metadata; parley primitive #1 tracks per-(sender, recipient, msg-id) delivery state. The composition is one-way READ — WL reads primitive #1 state; parley does NOT mutate WL entities.

### V5 ALL-RECIPIENTS-ACKED + SessionStart annotation — parley query API adapter (sub-spec §10.1 step 3, D-WL-20 element 1)

When the SessionStart hook or the validator runs V5 ALL-RECIPIENTS-ACKED, it needs per-recipient delivery state from parley primitive #1. **The query API call shape lives at this skill / hook layer** — per CLAUDE.md Hard Rule 1 the library never reaches for parley.

Per D-WL-20 element 1 (resolving xreq-ca7cd0c97551): primitive #1's query interface IS in scope for Phase-1 parley PR; final flag shape pinned during the primitive #1 standalone sub-spec round. Build against the assumed shape with a 1-line adapter at the call site.

**Brief-mandated call shape** (post parley/main `88b4c9e`):

```bash
parley delivery state <msg-id>
```

This is the **adapter site** (sub-spec §10.1 step 3). If the final parley shape diverges, only THIS skill changes — not the lib, not the spec.

For each (msg-id, recipient) pair the hook / skill needs:

```bash
# Adapter: parley delivery state <msg-id> [--member <fqid>] [--json]
# Output shape (assumed; pin during integration):
#   For --json: a JSON object/array keyed by recipient FQID, value = state string
#   For text: one line per recipient with the state
parley delivery state <msg-id> --json
```

Parse the result and build the `delivery_state` mapping `(msg_id, recipient_fqid) -> state_string` (states per primitive #1 sub-spec §2.1: `pending | delivered | acted_on | aborted`). Pass it to `state_digest.render_digest(..., delivery_state=mapping)` to annotate the SessionStart surface, or to `dispatch_checks.run_standing_dispatch_checks(..., delivery_state=mapping)` to drive V5.

If parley is not on PATH, OR `parley delivery state` is unavailable, OR the query errors: the adapter returns `None` and V5 + the SessionStart state annotation degrade gracefully — no warning surfaced, no annotation, entity-only display preserved.

### URI cross-reference (D-WL-19 element 2)

The library auto-populates `parley_external_ref: workshop-lite-dispatch://<id>` on every dispatch. Parley `DecisionRecord.external_decision_refs` may reference this dispatch via the URI for bidirectional cross-arc traceability. This is a pure cross-reference — no shared state.

## 6. Report back

Tell the user:

- the path written (or the existing path on idempotent match)
- the auto-generated dispatch id
- a one-line summary (purpose; scope; N recipients; deadline or none)
- when applicable: the `parley_external_ref` URI (so parley-side ratifies can be filed against it)
- when applicable: any V4 SUPERSEDES-CANDIDATE INFO surfaced by the validator (so the user can decide whether to explicitly supersede)

## Notes

- **Parley-agnostic at the lib layer** (CLAUDE.md Hard Rule 1): the `dispatch.py` library never imports or shells out to parley. The author seat + recipient FQIDs are derived by THIS skill (via `parley whoami` / `parley roster`) and handed to the lib.
- **Workshop-importability** (Hard Rule 2): frontmatter maps 1:1 to a future Workshop `StandingDispatch` entity. Until the Workshop schema extends, file-import lands frontmatter into `metadata_` JSONB; WL-specific fields (purpose, recipients, expected_outcome, deadline, expires_at, linked_msg_ids, parley_external_ref, satisfy_quorum) land in `metadata_` JSONB.
- **Workshop-lite config prefix** (Hard Rule 3): per-repo config knobs live in `<repo>/.claude/workshop-lite-config.toml` under the `[dispatches]` section (`hide_satisfied_after_days`, `visual_budget`).
- **Skill installs flat** (Hard Rule 4): no `/dev-` or `/lite-` prefix on the skill name.
- **Hooks never block** (Hard Rule 5 / D33): the SessionStart hook surfaces standing dispatches for the current seat but never blocks; parley query failures degrade to entity-only display.
- **Advisory validator** (Hard Rule 6 / D43): V1-V6 rules in `dispatch_checks.py` surface via `python3 -m dev_mgmt.validate`; `--strict` promotes V1 + V2 + V6 to ERROR. V3 + V4 + V5 stay INFO regardless.
- **NOT a judgment component** (Hard Rule 7 / sub-spec §3.2 + §7.1): the entity is declarative metadata + a deterministic 4-state lifecycle. V1-V6 are binary structural checks. SessionStart surfacing is `created_at ASC` deterministic — no prioritization, elision, or relevance-scoring; pagination (not truncation) past visual budget.
- **Cross-arc contract pinned** (D-WL-19 + D-WL-20): multi-recipient by construction, URI prefix `workshop-lite-dispatch://<id>`, parley primitive #1 query API in-scope with 1-line adapter at sub-spec §10.1 step 3.
- **Lifecycle state machine** (sub-spec §4): `standing` (default new) → `satisfied` (recipient explicitly closes; default all-recipients OR per-quorum) | `superseded` (newer dispatch replaces this scope) | `expired` (past expires_at without satisfaction; validator advisory only — never mutates).
