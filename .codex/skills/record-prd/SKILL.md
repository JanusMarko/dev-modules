---
name: record-prd
description: Record a PRD entity in the workshop-lite dev-mgmt system — captures the cross-repo PM-bridge product-requirements artifact with a 5-state forward-only lifecycle (draft → ratified → converting → technical_plan_ready → shipped). Writes docs/prds/<id>.md, refreshes docs/prds/INDEX.md, and supports state transitions via dedicated subcommands. Use when the user types /record-prd, /record-prd ratify, /record-prd convert, /record-prd technical-plan-ready, /record-prd ship, or asks to file/transition a PRD.
---

# /record-prd

When the user invokes `/record-prd`, run one of five flows depending on the subcommand:

- `/record-prd <slug> --title "<short>" --scope <scope> [...]`
- `/record-prd ratify <id> --by <fqid> [--rationale "<short>"]`
- `/record-prd convert <id> [--by <fqid>] [--rationale "<short>"]`
- `/record-prd technical-plan-ready <id> --technical-plan-url <url> [--by <fqid>] [--rationale "<short>"]`
- `/record-prd ship <id> --sha <SHA> [--by <fqid>] [--rationale "<short>"]`

The PRD entity codifies "this product-requirements artifact owns the lifecycle from PM-authored draft to shipped technical work" — the cross-repo PM-bridge supporting substrate per `docs/inbox/2026-06-02-prd-entity-cross-repo-pm-bridge-charter.md`. The parley-side PM-bridge (par-p0-defect-55 `product_manager` role_kind + `/translate` skill) bridges status UP to PM-readable form; this PRD's `## PM Summary` body section is the belt-and-suspenders structural marker the bridge echoes verbatim.

Read the binding charter before running this skill — every field semantic + lifecycle decision + cross-arc contract is documented there.

## 1. Determine the author seat (parley-coupling lives HERE, per CLAUDE.md Hard Rule 1)

Run `parley whoami --json` to discover the calling member's id. Compose the `author` value as `@<member-id>` (bare member-id form, prefixed `@`). The skill layer derives this; the library never imports or shells out to parley.

If parley is NOT on PATH (solo CC session): fall back to `author = "@unknown"` and INFO log to stderr.

## 2. /record-prd (create a new draft PRD)

### Gather inputs

Required:

- **slug** — short identifier (combined with date + per-day NN counter for the filename id)
- **title** — human-readable PRD title
- **scope** — one of `arc:<id>` / `sprint:<id>` / `repo:<area>` / `design:<doc>` / `decision:<id>`

Optional:

- **pm-summary** — initial body text for the REQUIRED `## PM Summary` section (charter AXIS-12). If omitted the template placeholder is used; the validator only requires the SECTION to exist, not the prose within it.
- **linked-msg-id** — repeatable; the parley msg-ids carrying the PM-authored requirement
- **linked-decisions** — comma-separated decision ids
- **cross-repo-prds** — comma-separated `<repo>:<id>` refs per charter AXIS-13 + par-p0-defect-56 multi-repo coordination convention (URI grammar canonically lives in that convention; this entity carries the literal reference list)
- **owner-user** — per D-RA-4; defaults `user/local`

If any required input is missing or ambiguous, use `AskUserQuestion` to collect.

### Write the PRD

From the repo root, invoke the CLI:

```bash
.venv/bin/python3 .claude/scripts/dev-mgmt/cli.py record-prd \
    --slug "<slug>" \
    --title "<title>" \
    --scope "<scope>" \
    [--pm-summary "<initial body text>"] \
    [--linked-msg-id "<msg-id>" ...] \
    [--linked-decisions "<csv>"] \
    [--cross-repo-prds "<csv>"] \
    [--author "@<seat>"] \
    [--owner-user "<user-id>"]
```

If the repo doesn't have a `.venv/`, fall back to `python3` (PyYAML must be available).

The CLI:
- auto-generates the id (`<YYYY-MM-DD>-<NN>-<slug>` per the date-keyed entity-id convention, matching Decision / Dispatch shape)
- auto-populates `parley_external_ref: workshop-lite-prd://<id>` per chunk-0 open-Q ratify (mirrors D-WL-19 grammar — parley DecisionRecord.external_decision_refs may reference this PRD via the URI)
- validates the frontmatter against the schema (state enum + scope-prefix taxonomy + cross_repo_prds `<repo>:<id>` shape)
- validates the body contains a `## PM Summary` section per charter AXIS-12
- writes `docs/prds/<id>.md`
- atomically re-renders `docs/prds/INDEX.md`
- prints the written path on stdout

A `ValidationError` exits non-zero and writes nothing.

## 3. /record-prd ratify <id>

Transition state `draft → ratified`. Stamps `ratified_at` + `ratified_by` per charter §2.2 required-fields-per-state.

### Gather inputs

- **id** — the PRD id (filename stem under `docs/prds/`)
- **by** (required) — the FQID of the seat ratifying (CTO / scrum-master per charter §2.2)
- **rationale** (optional) — short free-form string captured in the lifecycle log

### Invoke

```bash
.venv/bin/python3 .claude/scripts/dev-mgmt/cli.py record-prd-ratify \
    "<id>" \
    --by "@<seat>" \
    [--rationale "<short>"]
```

Idempotent: if the PRD is already at-or-past `ratified` in the chain, the CLI is a no-op forward-only return.

## 4. /record-prd convert <id>

Transition state `ratified → converting` (signals technical-plan dispatch fired). The technical-plan artifact itself is a SEPARATE entity (a dispatch or decision) referenced via `linked_decisions`; this transition just signals "scrum-master picked this up".

### Invoke

```bash
.venv/bin/python3 .claude/scripts/dev-mgmt/cli.py record-prd-convert \
    "<id>" \
    [--by "@<seat>"] \
    [--rationale "<short>"]
```

## 5. /record-prd technical-plan-ready <id>

Transition state `converting → technical_plan_ready`. Stamps `technical_plan_url` per charter §2.2 required-fields-per-state.

### Gather inputs

- **id** — the PRD id
- **technical-plan-url** (required) — URL to the technical plan artifact (e.g. a sprint plan, design doc, or external link)
- **by** (optional)
- **rationale** (optional)

### Invoke

```bash
.venv/bin/python3 .claude/scripts/dev-mgmt/cli.py record-prd-technical-plan-ready \
    "<id>" \
    --technical-plan-url "<url>" \
    [--by "@<seat>"] \
    [--rationale "<short>"]
```

## 6. /record-prd ship <id>

Transition state `technical_plan_ready → shipped` (terminal). Stamps `shipped_sha` per charter §2.2 required-fields-per-state.

### Gather inputs

- **id** — the PRD id
- **sha** (required) — the LAND commit SHA shipping the PRD
- **by** (optional)
- **rationale** (optional)

### Invoke

```bash
.venv/bin/python3 .claude/scripts/dev-mgmt/cli.py record-prd-ship \
    "<id>" \
    --sha "<SHA>" \
    [--by "@<seat>"] \
    [--rationale "<short>"]
```

## 7. Report back

Tell the user:

- the path written (or the existing path on idempotent match)
- the auto-generated PRD id (on create)
- a one-line summary (title; scope; current state)
- when applicable: the `parley_external_ref` URI (so parley-side ratifies can be filed against it)
- on terminal `shipped` transitions: the shipped SHA + a hint to fold into the next handoff / retro

## Notes

- **Parley-agnostic at the lib layer** (CLAUDE.md Hard Rule 1): the `prd.py` library never imports or shells out to parley. The author seat is derived by THIS skill (via `parley whoami`) and handed to the lib.
- **Workshop-importability** (Hard Rule 2): frontmatter maps 1:1 to a future Workshop `PRD` entity. Until the Workshop schema extends, file-import lands frontmatter into `metadata_` JSONB; WL-specific fields (state, ratified_at/by, technical_plan_url, shipped_sha, cross_repo_prds, parley_external_ref) land in `metadata_` JSONB (same pattern as standing-dispatch).
- **Skill installs flat** (Hard Rule 4): no `/dev-` or `/lite-` prefix on the skill name.
- **Hooks never block** (Hard Rule 5 / D33): no PRD-specific hook is added; INDEX-coherence advisories surface via the existing `validate-state.sh` Stop hook.
- **Forward-only linear chain** (chunk-0 PG-4 ratify): the 5-state lifecycle (draft → ratified → converting → technical_plan_ready → shipped) has exactly one allowed forward edge per state. No back-transitions. Bidirectional supersede is DEFERRED to v2 iff real PM workflow surfaces the need.
- **`## PM Summary` body section** (charter AXIS-12 + chunk-0 PG-3 ratify): the validator (`validate_prd_body`) enforces this section's presence. Template-default scaffolds it; the rule fires on hand-stripped bodies.
- **`cross_repo_prds` field** (charter AXIS-13 + chunk-0 PG-5 ratify): the `<repo>:<id>` URI grammar canonically lives in par-p0-defect-56's multi-repo coordination convention. The PRD validator enforces the literal shape; it does NOT participate in same-repo `linked_*` cross-link discovery (cross_links.py).
- **Per-state required fields** (charter §2.2 + chunk-0 PG-2 ratify): `ratified` requires `ratified_at` + `ratified_by`; `technical_plan_ready` adds `technical_plan_url`; `shipped` adds `shipped_sha`. Writer-driven transition functions stamp these at transition-time; hand-edited bad-state fails by design (validator-strict gate, AXIS-7+8 intent).
