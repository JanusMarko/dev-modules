---
name: consult
description: Persona-mediated AI consult via Gemini CLI fan-out — loads a persona from personas/<slug>.md, assembles persona + target + cross-linked context into a prompt, shells out to `gemini -p`, parses the JSON envelope, and lands a Review entity at docs/reviews/<YYYY-MM-DD-NN-slug>.md per charter §2.1. Use when the user types `/consult <persona-slug> <target>` or asks to consult a persona against an entity. v1 ships 8 default personas (devil-advocate, collaborator, security-auditor, scope-checker, risk-analyst, forward-compat-checker, ux-reviewer, prd-coach) + 3 alias skills (/devil, /collaborate, /security).
---

# /consult

When the user invokes `/consult <persona-slug> <target>`, run this flow.

The skill platform is the workshop-lite-consult-skill-platform charter at
`docs/inbox/2026-06-02-consult-skill-platform-gemini-fanout-charter.md`.
Read it once for the full design rationale; this SKILL.md describes
the operator-facing procedure.

## 1. Gather inputs

Required (positional):

- **persona-slug** — one of the 8 default personas (or any custom
  persona at `personas/<slug>.md` / `.workshop-lite/personas/<slug>.md`):
  - `devil-advocate` (evaluative — adversarial review)
  - `collaborator` (generative — joint refinement)
  - `security-auditor` (evaluative — security review)
  - `scope-checker` (evaluative — scope hygiene)
  - `risk-analyst` (evaluative — operational risk)
  - `forward-compat-checker` (evaluative — schema flexibility)
  - `ux-reviewer` (evaluative — human-side ergonomics)
  - `prd-coach` (generative — PRD authoring assistance)
- **target** — entity-id (filename stem) of the entity to consult on.
  Resolved against `docs/decisions/` / `docs/issues/` / `docs/reviews/` /
  `docs/handoffs/` / `docs/conversations/` / `docs/dispatches/` /
  `docs/wip/` / `docs/prds/` (in that order).

Optional:

- **--model** — override the persona's `default_model` frontmatter
- **--scope** — override the auto-derived scope (defaults to target's
  scope or `repo:<target-type>`)
- **--title** — override the default Review title (`/consult <p> <t>`)
- **--linked-msg-id** — repeatable; parley msg-ids carrying the call
- **--linked-decisions** — comma-separated decision ids
- **--supersedes** — old review id this Review supersedes (HR-#7
  supersede chain); call `/consult` then separately invoke
  `consult-supersede` to mark the old one
- **--include-dirs** — comma-separated dirs passed to `gemini
  --include-directories`. **v2.0 default (flag omitted):** repo root,
  filtered via `.gitignore` + `.consultignore` (see §1a). To force the
  v1 explicit-empty behavior (no files visible to gemini at all),
  pass `--include-dirs ""`.
- **--strict-context** — when an entry in the target's `linked_*`
  fields fails to resolve to a file under `docs/<kind>/`, exit
  non-zero with a clear diagnostic (default: warn-and-skip).
- **--verbose** — print the three filter stages
  (a = raw `git ls-files`, b = post-`.gitignore`, c = post-
  `.consultignore`) to stderr for debugging include-set composition.
- **--token-budget N** — token budget for the prompt + files payload
  (byte // 4 estimate; default 500_000 leaves headroom under the
  gemini Flash 1M context window).
- **--confirm-large** — silence the token-budget warning (operator
  acknowledges).
- **--fail-on-large** — exit non-zero when the token-budget estimate
  exceeds `--token-budget` (CI fail-fast).

If any required input is missing or ambiguous, use `AskUserQuestion`
to collect **before invocation**. The /consult flow itself
(between input gathering and the gemini-CLI exec call at §3) is
deterministic + non-interactive by design — no operator prompts
mid-flow. Confirm all inputs upfront so the flow runs to completion
without blocking on operator clarification. Outside the /consult
invocation flow, `AskUserQuestion` remains a legitimate tool for
other purposes (e.g. operator confirmations in the consuming
session).

(The graceful-degradation path at §4 below — gemini-unavailable /
parse-error prompts — is an explicit exception: an expected
interactive moment AFTER CLI failure, not a violation of the
deterministic-flow discipline.)

## 1a. Context model (v2.0)

The v2.0 surface assembles two distinct context channels:

1. **Files visible to gemini via `--include-directories`** — controlled
   by `--include-dirs` (or the v2.0 repo-root default). Filtered via
   `.gitignore` + `.consultignore`. This is the BACKGROUND scope:
   gemini reads files in this directory tree on-demand based on the
   prompt.
2. **Auto-computed `context_bundle`** — assembled from the target
   entity's forward `linked_*` fields (`linked_decisions`,
   `linked_issues`, `linked_reviews`, `linked_handoffs`,
   `linked_conversations`, `linked_dispatches`, `linked_prds`,
   `linked_wip`). 1-hop only. Inlined directly in the prompt body.
   This is the FOREGROUND scope: explicit forward links the operator
   chose to cross-reference.

**Filter scope clarification (PG-3 ratify):** `.gitignore` /
`.consultignore` apply to channel 1 ONLY. The `context_bundle` is
explicit forward-link resolution — the operator linked these entities
on purpose, so they go in the bundle regardless of whether their
on-disk path matches an ignore pattern. (In practice all entity
files live under `docs/*` which is tracked, so this rarely matters.)

**`linked_msg_ids` is NOT auto-resolved** in v2.0 — parley msg-ids
live in `chat.jsonl` outside workshop-lite, and the lib layer is
parley-agnostic (CLAUDE.md HR-#1). The msg-id list remains visible
to the persona via the target frontmatter section of the prompt.

### `.consultignore` format + placement

`.consultignore` is an OPTIONAL file at the **repo root** with the
same syntax as `.gitignore` (gitwildmatch via the `pathspec` library).
Layered ON TOP of `.gitignore` for consult-specific excludes
(e.g. private notes, large fixtures, charters not meant to bias
gemini's reading).

Resolution order:

1. Operator `--include-dirs <explicit>` — bypasses filters entirely
2. v2.0 default — repo root, filtered via `.gitignore` then
   `.consultignore`
3. `--include-dirs ""` — explicit empty (no files at all; v1 escape)

**v2.0 supports POSITIVE excludes ONLY.** Negation patterns
(`!path`) are stripped at parse time and a stderr diagnostic
surfaces per stripped line. (Deferred to v2.1 per the ratified
v2.0 PRD §R10; operators needing re-include semantics can use
explicit `--include-dirs` at invocation.)

Concrete `.consultignore` example (R13 insight 8):

```
# Large data dirs that would blow the token budget
data/
fixtures/large/

# Private design notes operators don't want in consult context
docs/inbox/
docs/conversations/

# Build artifacts (already in .gitignore but pinning here too is
# fine — duplicates are no-ops)
build/
dist/

# Test snapshots, generated files
**/__snapshots__/
**/*.golden

# Sensitive configuration that survived .gitignore
.env.local.example
```

### Migration note (v1 → v2.0)

- v1 callers passing `--include-dirs <explicit>` — **no change**.
- v1 callers NOT passing `--include-dirs` — **NEW BEHAVIOR**: the
  consult now defaults to repo-root with filtering. The persona sees
  real code/docs instead of fabricating from target body text. If the
  prior v1-explicit-empty behavior is required, pass
  `--include-dirs ""`.
- v1 callers receiving `(none)` for `## Cross-linked context` —
  **NEW BEHAVIOR**: if the target has any forward `linked_*` entries,
  those entities are now auto-resolved + inlined.

## 2. Determine author seat (parley-coupling lives HERE, per CLAUDE.md Hard Rule 1)

Run `parley whoami --json` to discover the calling member's id. Compose
the `author` value as `@<member-id>` (bare-id form, prefixed `@`). The
library never imports or shells out to parley.

If parley is NOT on PATH (solo CC session): fall back to
`author = "@unknown"` and INFO log to stderr.

## 3. Invoke the consult flow

From the repo root, invoke the CLI. The explicit ``.venv/bin/python3``
form is canonical (no re-exec round-trip) and is preferred in scripts.
Bare ``python3 .claude/scripts/dev-mgmt/cli.py consult …`` also works
post-workshop-lite-obs-g-part-2 LAND — ``cli.py`` auto-detects an
adjacent project ``.venv`` and re-execs under it. If no ``.venv`` is
reachable AND a project dep is missing, ``cli.py`` exits 2 with an
actionable ``python3 -m venv .venv && .venv/bin/pip install -e .``
instruction. Set ``WORKSHOP_LITE_SKIP_VENV_REEXEC=1`` to disable the
re-exec when testing CLI behavior under a specific interpreter.

```bash
.venv/bin/python3 .claude/scripts/dev-mgmt/cli.py consult \
    "<persona-slug>" \
    "<target-id>" \
    [--backend {gemini,agy,codex}] \
    [--author "@<seat>"] \
    [--model "<backend-model>"] \
    [--scope "<scope>"] \
    [--title "<title>"] \
    [--linked-msg-id "<msg-id>" ...] \
    [--linked-decisions "<csv>"] \
    [--supersedes "<old-review-id>"] \
    [--include-dirs "<csv>|''"] \
    [--strict-context] \
    [--verbose] \
    [--token-budget <int>] \
    [--confirm-large | --fail-on-large] \
    [--auto-fallback] \
    [--timeout <int>] \
    [--gemini-bin <name>] [--agy-bin <name>]
```

### Backend selection (v2.1 — cohort R / wl:2026-06-05-06)

The `--backend` flag selects which CLI binary serves the consult call.
**Default is `agy`** as of 2026-06-11 (Kris-accepted flip, CTO dispatch
msg-a0c92adfacf4 — gemini CLI shuts off 2026-06-18; flipping early
surfaces agy-default regressions while the gemini fallback still
works). NOTE on persona `default_model` frontmatter: those values are
gemini model ids and apply only on the gemini path — the agy path
resolves models exclusively via `--model` → `$WL_AGY_MODEL` →
tenant-default and ignores persona `default_model` (already correct;
no code change at the flip).

- **`gemini`** (explicit `--backend gemini`; available until the
  2026-06-18 shutoff) — shells out to `gemini --approval-mode plan -m
  <MODEL> -o json -p <PROMPT>`. Model defaults to the persona's
  `default_model` then `DEFAULT_GEMINI_MODEL` (`gemini-3.1-pro-preview`
  at HEAD).
- **`agy`** (default; Google Antigravity CLI; cohort R land) — shells out to
  `agy --print -` with the prompt fed via **stdin** (avoids OS
  `ARG_MAX` on large prompts; F1 mitigation from chunk-0 forensic).
  `--add-dir` is repeated per include-dir (differs from gemini's
  comma-sep `--include-directories`). Model resolution order:
  `--model` CLI flag → `$WL_AGY_MODEL` env-var → omit-the-flag-and-let-
  agy-pick (agy uses its built-in tenant-adapted default, e.g.
  `Gemini 3.5 Flash (Medium)` on a free-tier consumer account). For
  load-bearing /consult work where response quality matters more than
  latency, set `WL_AGY_MODEL` explicitly — recommended starting point
  is `"Gemini 3.1 Pro (High)"` (run `agy models` to list what your
  tenant exposes). Minimum agy version: `1.0.5`; set
  `WL_AGY_VERSION_OVERRIDE=1` to bypass the check.
  - **Direct-CLI quality caveat (cohort GG c6c5814)**: invoking `agy --print` directly (outside `bin/wl consult` / library) bypasses `invoke_agy`'s wrapper fixes (narration guard + R6 schema validator + persona scoping + provenance markers). Direct-CLI quality is wrapper-dependent; rows-3+6-class narration mode is observable BY DESIGN on raw `agy` per cohort GG verifier OBS-1 (`docs/reviews/2026-06-06-15-cohort-GG-verifier-mutation-matrix-and-A8-replay-verdict.md`). Use `/consult <persona> <target>` or `bin/wl consult` for production-quality persona-mediated review work; reserve direct-CLI for raw experimentation.
- **`codex`** — stub; raises `NotImplementedError` referencing
  wl:2026-06-04-03 (codex backend territory). Will land separately.

v2.1 exit codes:

- **0** — success; Review entity written
- **2** — generic input/validation error
- **11** — `GeminiUnavailable` (gemini backend; charter §2.4 Y-branch trigger)
- **12** — `GeminiResponseParseError` (gemini backend; Y-branch trigger)
- **13** — `--strict-context` + a `linked_*` entry failed to resolve
- **14** — `--fail-on-large` + token-budget estimate exceeded
- **15** — `AgyUnavailable` (agy backend; same Y-branch trigger as 11)
- **16** — `AgyResponseParseError` (agy backend; same Y-branch trigger as 12)
- **17** — codex backend NotImplementedError (stub; wl:2026-06-04-03)

### Operator note: large repos + Bash-tool timeout (wl:2026-06-05-03)

The `--token-budget` warning is advisory — on very-large repos (1M+
token estimates) the run is also likely to exceed the default Bash-tool
`--timeout` (300s), surfacing as a generic Bash timeout with no
consult-side diagnostic. When you see a token-budget WARNING:

- For ~1M token estimates: raise the Bash-tool `--timeout 420000` (≈7min).
- For ~4M+ estimates: prefer narrowing via `--include-dirs` over raising
  `--timeout` further. The auto-narrow heuristic (wl:2026-06-05-03)
  derives a narrower scope from target frontmatter automatically when
  `--include-dirs` is unset AND the estimate exceeds 2× budget; surfaces
  the chosen scope to stderr.
- The `consult` subcommand's own `--timeout` flag (default 300s) bounds
  the BACKEND subprocess — the Bash-tool `--timeout` is a separate
  wrapper-level setting that bounds the overall invocation.
- Pass `--auto-fallback` to opt in to a single narrow-scope retry when
  the backend subprocess times out (default OFF for principle-of-least-
  surprise); the retry uses the same frontmatter-derived narrow scope
  as the auto-narrow heuristic.

If the repo doesn't have a `.venv/`, fall back to `python3` (PyYAML
required).

The CLI:

- resolves the persona via repo-overlay precedence
  (`.workshop-lite/personas/<slug>.md` → `personas/<slug>.md`)
- resolves the target entity across the search-dir list
- assembles the prompt (persona body + target body + cross-linked
  context + output-schema instruction)
- shells out per `--backend`:
  - `gemini`: `gemini --approval-mode plan -m <MODEL> -o json -p <PROMPT>` (v2.0 path)
  - `agy`: `agy --print - [--model <M>] [--add-dir <D> ...]` with the
    prompt fed via stdin (v2.1)
- parses the response per backend (charter PG-4 fence-extract + JSON):
  - gemini: double-parse the `-o json` envelope (outer
    `{session_id, response, stats}` → inner `response` field → JSON
    object matching the persona's `output_schema`)
  - agy: single-parse stdout directly (no envelope; agy emits plain
    text; the fenced-JSON block from the persona prompt is
    extracted via the same shared `parse_persona_response_text`
    helper as gemini's inner-parse step)
- writes a Review entity at `docs/reviews/<YYYY-MM-DD-NN-slug>.md`
  with the persona-mediated sub-schema (charter §2.1 + PG-1(a)
  UNION/DISCRIMINATOR-BY-SOURCE on `persona_used`)
- adds a forward cross-link (`linked_<target-kind>: [<target-id>]`)
- atomically re-renders `docs/reviews/INDEX.md`
- prints the written path on stdout

## 4. Graceful degradation on backend failure (charter §2.4 + HR-#3 never-silent)

If the CLI exits with code **11** (`GeminiUnavailable`), **12**
(`GeminiResponseParseError`), **15** (`AgyUnavailable`), or **16**
(`AgyResponseParseError`), the stderr emits:

```
<backend>-unavailable: <reason>           # exit 11 or 15
<backend>-response-parse-error: <reason>  # exit 12 or 16
fallback-prompt-file: <path-to-temp-file>
(skill layer: prompt operator Y/n; ...)
```

The fallback path is identical across backends — the temp file
contains the assembled prompt; the operator falls back to local CC
just as on the gemini path. Exit 17 (codex stub) is NOT a degradation
trigger: it's an architectural "not yet implemented" diagnostic;
choose a different `--backend` value and retry.

Prompt the operator with `AskUserQuestion`:

- **Y (default)** — fall back to local CC: read the file at
  `fallback-prompt-file`, process the assembled prompt yourself
  (you are the local CC), generate a JSON response matching the
  persona's `output_schema`, write it to a sibling `.response.json`
  file, then invoke:

  ```bash
  .venv/bin/python3 .claude/scripts/dev-mgmt/cli.py consult-with-response \
      "<persona-slug>" \
      "<target-id>" \
      --response-from-file "<sibling-response.json>" \
      --author "@<seat>" \
      --model "claude-code"
  ```

  This writes the Review entity with `model=claude-code` so the
  audit trail is uniform across both branches (HR-#3).

- **n** — exit clean with the diagnostic; no Review entity written.

The fallback prompt-file persists for operator inspection; it is
NOT auto-deleted.

## 5. Supersede (HR-#7)

To replace an older persona-mediated Review with a newer one:

1. Run `/consult <persona> <target> --supersedes <old-id>` — writes
   the NEW Review with `supersedes: <old-id>` back-pointer.
2. Capture the new id from stdout.
3. Run:

   ```bash
   .venv/bin/python3 .claude/scripts/dev-mgmt/cli.py consult-supersede \
       "<old-id>" \
       "<new-id>" \
       [--by "@<seat>"] \
       [--rationale "<short>"]
   ```

   This marks the OLD review's `status=superseded` +
   `superseded_by=<new-id>` and appends a lifecycle log entry.

Supersede is **forward-only** — to back out, write yet another
Review and supersede the wrong one.

The supersede transition only applies to the **persona-mediated path**
(reviews with a `persona_used` field). The existing closed-enum path
(written by `/record-review`) has its own terminal state (`completed`)
and does not participate in HR-#7.

## 6. Report back

Tell the user:

- the path written (or the existing path on idempotent match)
- the persona used + the model that responded
- the **decision** (PROCEED / AMEND / RETHINK for evaluative;
  N/A for generative)
- a one-line summary of the top finding (evaluative) or top insight
  (generative)
- on graceful-degradation: the fallback file path + whether you
  proceeded through Y or n
- on supersede: the old and new ids + the transition timestamp

## Notes

- **Parley-agnostic at the lib layer** (CLAUDE.md Hard Rule 1): the
  `consult.py` library never imports or shells out to parley. Author
  seat derivation lives here in the skill via `parley whoami`.
- **Persona-as-data** (charter HR-#6): personas are pure markdown
  + frontmatter — no executable code, no eval, no jinja. Adding a
  new persona is dropping a new `.md` file under `personas/`.
- **Repo overlay** (charter §2.2 / AXIS-5): a repo-local persona at
  `.workshop-lite/personas/<slug>.md` takes precedence over the
  workshop-lite default; no silent fallback if neither exists.
- **Hard Rule 3 never-silent**: every fallback path (gemini-missing,
  exit-nonzero, parse-fail, timeout) emits a clear diagnostic + a Y/n
  decision point. Operator never gets a silent partial result.
- **Hard Rule 4 (HR-#5 of charter) assume-auth**: `gemini auth login`
  must already be configured; we don't auto-configure. Auth failures
  surface as a non-zero exit + a clear stderr line.
- **Forward-only cross-link** (chunk-0 PG-9 ratify): the Review
  carries `target_entity_id` + `linked_<target-kind>: [<target-id>]`.
  The target entity is NEVER mutated; reverse projection is derived
  on demand by `cross_links.derived_reverse_links`.
- **v1 scope** (charter §10): single-backend (Gemini), single-target,
  blocking JSON, no streaming, no token-cost tracking, no
  `/triangulate` 3-model fan-out. v2 follow-ons are designed in but
  not implemented.
