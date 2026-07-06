---
name: record-review
description: Record a Review entity in the lightweight dev-mgmt system. Captures review_type, title, status, scope, author, findings list and provenance into docs/reviews/<id>.md and refreshes reviews/INDEX.md. Use when the user types /record-review or asks to log a review (adversarial, collaborative, synthesis, research).
---

# /record-review

When the user invokes `/record-review`, run this flow.

## 1. Gather inputs

Required:

- **title** — short imperative summary of what was reviewed (e.g., `Adversarial review of Alembic drift gate plan`)
- **review-type** — one of:
  - `adversarial` — finds problems
  - `collaborative` — joint refinement
  - `synthesis` — combines / reconciles multiple inputs
  - `research` — exploratory; may have no severity-tagged findings
- **scope** — one of:
  - `sprint:<sprint-id>` — review of a single sprint's work
  - `repo:<area>` — review of codebase-wide concern
  - `design:<doc-name>` — review of a design doc
- **author** — typically the calling member's `@id` in parley; the human operator otherwise

Optional:

- **status** — `completed` (default) | `in_progress`
- **sprint_id** + **stage** — must be paired (both set or both null). `stage` ∈ `plan | execute | retro`. Only set when `scope=sprint:<id>`.
- **findings** — **D16** — list of structured finding-dicts. Each finding REQUIRES `severity` (`high` | `medium` | `low`) and `summary` (non-empty string). Extra keys are PERMITTED (e.g., `status`, `resolution`, `location`). Empty list is valid (a research-type review may have no severity-tagged findings).
- **body** — inline markdown body. Takes precedence over `--body-from-file`.
- **body-from-file** — path to a file whose content becomes the review body. Frontmatter in the source file is stripped.
- **linked-decisions** — comma-separated decision ids the review references or produced.
- **linked-msg-ids** — parley msg-IDs of the review conversation (durable provenance).

If any required input is missing or ambiguous, use `AskUserQuestion` to collect.

**Body default (Q3a + Q2a)**: when neither `--body` nor `--body-from-file` is given, the on-disk template (`docs/.templates/review.md`) body is written, with the `{findings_block}` placeholder substituted with an auto-rendered bullet list of the structured `findings` frontmatter data. Frontmatter is the SoT; the body's Findings section is derived (same shape as `/record-decision`'s options-block auto-render). This differs from `/handoff`'s D7.A auto-body; reviews are content-keyed and the template scaffold is the right starting point. **Known limitation**: post-write manual body edits drift from frontmatter — owned by the future `/update-review` skill, not Sprint 4.

## 2. Determine author + parley context

If in a parley session:

1. Run `parley whoami` to discover the calling member's id. Use `@<id>` for `--author`.
2. Capture relevant `--linked-msg-ids` (parley msg-IDs of the review conversation) for the durable provenance chain.

If NOT in a parley session, `--author` is whoever is recording the review.

## 3. Write the review

From the repo root, invoke the CLI:

```bash
.venv/bin/python3 .claude/scripts/dev-mgmt/cli.py record-review \
    --title "<title>" \
    --review-type adversarial|collaborative|synthesis|research \
    --scope "<scope>" \
    --author "@<member>" \
    [--status in_progress|completed] \
    [--sprint-id "<id>" --stage plan|execute|retro] \
    [--findings-json '[{"severity":"high","summary":"..."}, ...]'] \
    [--body "<inline body>" | --body-from-file "<path>"] \
    [--linked-decisions "<csv>"] \
    [--linked-msg-ids "<csv>"]
```

`--findings-json` defaults to `"[]"` (empty list valid). Each finding-dict MUST have `severity` ∈ {high, medium, low} and a non-empty `summary` string. Extra keys (e.g., `status`, `resolution`, `location`) are passed through unchanged and rendered as indented sub-bullets in the auto-rendered Findings section.

If the repo doesn't have a `.venv/`, fall back to `python3` (PyYAML must be available).

The CLI:
- auto-generates the id (`YYYY-MM-DD-NN-<slugified-title>` — per-day counter, content-keyed per **D15**)
- validates the frontmatter against the D14+D16 Review schema (including each finding-dict's required-keys shape)
- writes `docs/reviews/<id>.md`
- atomically re-renders `docs/reviews/INDEX.md` (Findings column shows the count)
- prints the written path on stdout

A `ValidationError` exits non-zero and writes nothing. Common causes:
- `--review-type` outside {adversarial, collaborative, synthesis, research}
- `--scope` without one of the required prefixes
- A finding-dict missing `severity` or `summary`, or `severity` outside the enum
- `--sprint-id` without `--stage`

## 4. Report back

Tell the user:

- the path to the written review
- the auto-generated review id
- a one-line summary (review_type, scope, finding count)

## Notes

- **D14 (Review schema)**: §6 verbatim plus a `linked_decisions: []` field for `linked_*` family consistency.
- **D15 (id convention)**: `YYYY-MM-DD-NN-<slug>` (per-day counter), content-keyed.
- **D16 (findings list)**: required-but-may-be-empty; required keys per finding are `severity` (enum) and `summary` (non-empty string); extra keys are permitted and rendered into the body.
- **Cross-link semantics**: `linked_*` arrays are opaque string lists in Sprint 4 — content validation deferred to Sprint 7's `cross_links.py`.
- **Workshop importability**: every field maps to a Workshop entity column (per CLAUDE.md Hard Rule 6).
- **Parley-agnostic base**: works in a solo CC session in a fresh repo too, as long as `docs/reviews/` (or its parents) can be written.
