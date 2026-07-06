---
name: record-wip
description: Record a WIP-claim entity in the workshop-lite dev-mgmt system — declares the seat is mid-work on a set of paths under a declared scope, with an expiry. Writes docs/wip/<id>.md, refreshes wip/INDEX.md, and supports release / extend transitions. Use when the user types /record-wip, /record-wip release, /record-wip extend, or asks to claim/release/extend WIP scope.
---

# /record-wip

When the user invokes `/record-wip`, run one of three flows depending on the subcommand:

- `/record-wip <slug> --paths PATH... [--scope SCOPE] [--expires DURATION] [--linked-msg-id MSG-ID...]`
- `/record-wip release <id> [--by FQID] [--rationale "<short>"]`
- `/record-wip extend <id> <duration>`

The WIP-claim entity codifies "this seat is mid-work on these paths, with this declared scope, until this expiry." Closes the empirical pain at maxai (charter §4 failure #2 / MAI-PM xreq-f21116ddb9fb finding #2): N-file uncommitted working tree with no per-seat ownership record.

Read the binding sub-spec at `docs/design/2026-05-29-wl-wip-claim-spec.md` before running this skill — every field semantics + lifecycle decision is documented there.

## 1. Determine seat (parley-coupling lives HERE, per CLAUDE.md Hard Rule 1)

Run `parley whoami` to discover the calling member's id. Compose the seat FQID:

```bash
parley whoami --json
```

Parse the JSON output for `session.sid` and `member_id` (or `id`). Compose `seat = "<sid>:<member-id>"` (e.g. `wl-rearch:wl-plan`). When the claim is filed inside the seat's own session AND the member-id is unambiguous, the bare `member-id` is also legal — but the FQID form is the safe default.

If parley is NOT on PATH (solo CC session): fall back to `seat = "local:cwd:unknown"` and INFO log to stderr. The library accepts any string for `seat`; the validator V1 ORPHANED check is skipped when no roster is available.

## 2. /record-wip (create a new claim)

### Gather inputs

Required:

- **slug** — short identifier for the claim (combined with date + seat for the filename)
- **paths** — comma-separated list of repo-relative paths the seat is mid-work on (non-empty per sub-spec §3)

Optional:

- **scope** — one of:
  - `arc:<id>` — multi-sprint arc-level scope
  - `sprint:<id>` — sprint-internal scope (auto-detect via `sprint_state.find_active_sprint` if not supplied AND an active sprint exists)
  - `repo:<area>` — repo-area-level scope
- **expires** — duration from now; default `4h` per Q-WL-3 resolution (matches typical CC session length). Format: `<int>h`, `<int>m`, or `<int>h<int>m`.
- **sprint_id** + **stage** — paired (both set or both null); set when scope=sprint:<id>
- **linked-msg-id** — comma-separated parley msg-IDs that authorized the work (durable provenance)
- **linked-decisions** — comma-separated decision ids
- **linked-sprints** — comma-separated sprint ids
- **title** — optional human-readable title (default derives from seat + slug)
- **owner-user** — per D-RA-4; defaults `user/local`

If any required input is missing or ambiguous, use `AskUserQuestion` to collect.

### Write the claim

From the repo root, invoke the CLI:

```bash
.venv/bin/python3 .claude/scripts/dev-mgmt/cli.py record-wip \
    --slug "<slug>" \
    --seat "<fqid-seat>" \
    --paths "<csv-paths>" \
    --scope "<scope>" \
    [--expires "<duration>"] \
    [--sprint-id "<id>" --stage plan|execute|retro] \
    [--linked-msg-ids "<csv>"] \
    [--linked-decisions "<csv>"] \
    [--linked-sprints "<csv>"] \
    [--title "<human-readable>"] \
    [--owner-user "<user-id>"]
```

If the repo doesn't have a `.venv/`, fall back to `python3` (PyYAML must be available).

The CLI:
- auto-generates the id (`YYYY-MM-DD-HHMM-<seat-flattened>-<slug>` per sub-spec §3)
- validates the frontmatter against the WIP-claim schema (`status` / `token_state` enum, `paths` non-empty, scope prefix taxonomy)
- writes `docs/wip/<id>.md`
- atomically re-renders `docs/wip/INDEX.md` (sub-spec §8 layout: Active / Closed-trailing-Nd with rolling-collapse)
- prints the written path on stdout

**Idempotency** (sub-spec §6): if a `claimed` claim already exists with the same seat + exact-paths-set + scope, the CLI returns the existing path without writing a new file. INFO to the user; no error.

A `ValidationError` exits non-zero and writes nothing. Common causes:
- `--paths` empty
- `--scope` without a recognized prefix (`arc:`, `sprint:`, `repo:`, `design:`, `decision:`)
- `--sprint-id` without `--stage` (they must be paired)

## 3. /record-wip release <id>

Voluntarily drop an existing claim — typically because the work was cancelled, scope was handed off, or the seat is closing out cleanly.

### Gather inputs

- **id** — the claim id (filename stem under `docs/wip/`)
- **rationale** (optional) — short free-form string captured in the claim's lifecycle log

### Invoke

```bash
.venv/bin/python3 .claude/scripts/dev-mgmt/cli.py record-wip-release \
    "<id>" \
    [--rationale "<short>"]
```

The CLI transitions `status` + `token_state` from `claimed` to `released`, appends a transition log entry to the body, and re-renders the INDEX. Idempotent: if the claim is already terminal (`released` / `committed` / `abandoned`), the CLI is a no-op and returns the existing path.

## 4. /record-wip extend <id> <duration>

Extend the claim's `expires_at` by a duration. Idempotent: INFO + no-op if the claim is already terminal.

### Invoke

```bash
.venv/bin/python3 .claude/scripts/dev-mgmt/cli.py record-wip-extend \
    "<id>" \
    "<duration>"
```

Duration format: `<int>h`, `<int>m`, or `<int>h<int>m` (e.g. `2h`, `30m`, `1h30m`).

## 5. Report back

Tell the user:

- the path written (or the existing path on idempotent match)
- the auto-generated claim id
- a one-line summary (seat, scope, expires-at)
- when applicable: any V3 path-collision warning surfaced by the validator (so the user can coordinate before editing)

## Notes

- **Parley-agnostic at the lib layer** (CLAUDE.md Hard Rule 1): the `wip_claim.py` library never imports or shells out to parley. The seat FQID is derived by THIS skill (via `parley whoami`) and handed to the lib.
- **Workshop-importability** (Hard Rule 2): frontmatter maps 1:1 to a future Workshop `WipClaim` entity. Until the Workshop schema extends, file-import lands frontmatter into `metadata_` JSONB on the parent Sprint or Decision (sub-spec §3 mapping).
- **`status` / `token_state` isomorphism** (composite-audit HIGH #1, sub-spec §3 amendment): both fields use the same enum `{claimed, committed, released, abandoned}` and stay 1:1 by name. `claimed` is the active-state name — NOT `active`.
- **Hooks never block** (Hard Rule 5 / D33): the SessionStart hook surfaces active claims for the current seat and visible path-collisions (sub-spec §7), but never blocks; failures degrade to a stderr log.
- **Advisory validator** (Hard Rule 6 / D43): V1-V5 rules in `wip_claim_checks.py` surface via `python3 -m dev_mgmt.validate`; `--strict` promotes V1-V4 to ERROR. V5 PATH-NONEXISTENT stays INFO regardless.
- **Lifecycle state machine** (sub-spec §4): `claimed` is the active state; `released` (voluntary) and `committed` (work landed) are terminal; `abandoned` is the validator-detected degraded form (seat-absent OR past-expiry — the validator surfaces an INFO-recommend; the seat does the file mutation, NOT the validator).
