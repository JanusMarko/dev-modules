---
name: record-issue
description: Record an Issue entity in the lightweight dev-mgmt system. Captures title, severity, status, scope, reporter and provenance into docs/issues/<id>.md and refreshes issues/INDEX.md. Use when the user types /record-issue or asks to file a bug/issue.
---

# /record-issue

When the user invokes `/record-issue`, run this flow.

## 1. Gather inputs

Required:

- **title** — short imperative summary of the problem (e.g., `Test cleanup pending pollution causes flake`)
- **severity** — `high` | `medium` | `low`
- **scope** — one of:
  - `sprint:<sprint-id>` — issue is specific to a single sprint's work
  - `repo:<area>` — codebase-wide issue (cross-sprint)
  - `design:<doc-name>` — design-doc level issue (specification gap)
- **reporter** — typically the calling member's `@id` in parley; the human operator otherwise

Optional:

- **status** — `open` (default) | `investigating` | `resolved` | `wontfix`
- **sprint_id** + **stage** — must be paired (both set or both null). `stage` ∈ `plan | execute | retro`. Only set when `scope=sprint:<id>`.
- **class** — **D12** — optional free-form string (default null). Per-repo can use it for their own taxonomy (e.g., MaxAI's flake-debt taxonomy). NOT a fixed enum at the base level.
- **body** — inline markdown body. Takes precedence over `--body-from-file`.
- **body-from-file** — path to a file whose content becomes the issue body. Frontmatter in the source file is stripped.
- **linked-decisions** — comma-separated decision ids (the §6 spec called this `related_decisions`; **D12** renames it to `linked_decisions` for `linked_*` family consistency).
- **linked-reviews** — comma-separated review ids (which reviews surfaced or referenced this issue).
- **linked-msg-ids** — parley msg-IDs that produced this issue (durable provenance).

If any required input is missing or ambiguous, use `AskUserQuestion` to collect.

**Body default (Q3a)**: when neither `--body` nor `--body-from-file` is given, the on-disk template (`docs/.templates/issue.md`) body is written verbatim — a section-header skeleton (Reproduction / Root cause / Fix path / Notes) for the human/agent to fill in later. This differs from `/handoff`'s D7.A auto-body (which composes from sprint state); issues are content-keyed, so an auto-generated body would feel hollow.

## 2. Determine reporter + parley context

If in a parley session:

1. Run `parley whoami` to discover the calling member's id. Use `@<id>` for `--reporter`.
2. Capture relevant `--linked-msg-ids` (parley msg-IDs from the conversation that surfaced the issue) for the durable provenance chain.

If NOT in a parley session, `--reporter` is whoever is filing the issue (typically the human operator).

## 3. Write the issue

From the repo root, invoke the CLI:

```bash
.venv/bin/python3 .claude/scripts/dev-mgmt/cli.py record-issue \
    --title "<title>" \
    --severity high|medium|low \
    --scope "<scope>" \
    --reporter "@<member>" \
    [--status open|investigating|resolved|wontfix] \
    [--sprint-id "<id>" --stage plan|execute|retro] \
    [--class "<free-form-tag>"] \
    [--body "<inline body>" | --body-from-file "<path>"] \
    [--linked-decisions "<csv>"] \
    [--linked-reviews "<csv>"] \
    [--linked-msg-ids "<csv>"]
```

If the repo doesn't have a `.venv/`, fall back to `python3` (PyYAML must be available).

The CLI:
- auto-generates the id (`YYYY-MM-DD-NN-<slugified-title>` — per-day counter, content-keyed per **D15**, NOT time-keyed like handoffs)
- validates the frontmatter against the D12+D13 Issue schema
- writes `docs/issues/<id>.md`
- atomically re-renders `docs/issues/INDEX.md`
- prints the written path on stdout

A `ValidationError` exits non-zero and writes nothing. Common causes:
- `--severity` outside {high, medium, low}
- `--scope` without one of the required prefixes (`sprint:`, `repo:`, `design:`)
- `--sprint-id` without `--stage` (they must be paired)

## 4. Report back

Tell the user:

- the path to the written issue
- the auto-generated issue id (so future cross-links can reference it)
- a one-line summary (severity, scope, status)

## Notes

- **D12 (`class` is optional free-form)**: the §6 example's `class: 2` (integer for MaxAI's flake-debt taxonomy) is replaced by an optional free-form string. The base schema is parley-agnostic and repo-agnostic; per-repo taxonomies layer on top via this field.
- **D13 (scope taxonomy)**: same prefix-taxonomy as `/record-decision` — `sprint:`, `repo:`, `design:`.
- **D15 (id convention)**: `YYYY-MM-DD-NN-<slug>` (per-day counter), NOT `YYYY-MM-DD-HHMM-<slug>` (handoff convention). Issues are content-keyed.
- **Cross-link semantics**: `linked_*` arrays are opaque string lists in Sprint 4 — content validation against existing entity ids is deferred to Sprint 7's `cross_links.py`.
- **Workshop importability**: every field maps to a Workshop entity column (per CLAUDE.md Hard Rule 6).
- **Parley-agnostic base**: this skill works in a solo CC session in a fresh repo too, as long as `docs/issues/` (or its parents) can be written.
