---
name: translate
description: |
  Translate between PM register and engineering register inside a
  parley session. `/translate --up <body>` rewrites technical signals
  (commit SHAs, Kind.LAND, PR-READY, Kind.RATIFY_OR_CORRECT, test
  verdicts) into plain language for a non-technical Product Manager.
  `/translate --down <body>` rewrites PM intent (goals, acceptance
  criteria, success measures) into structured engineering requests.
  Output is wrapped in a machine-parseable ```pm-translation``` markdown
  block so the bridge cannot paraphrase around it. Repo-specific
  overlay loads from `$REPO/docs/conventions/translate-overlay.md` if
  present.
---

# /translate — the PM-bridge translation skill

This skill is the discipline behind the `product_manager` role_kind
(parley substrate). It is invoked by a PM-bridge member to rewrite a
message between the engineering register and the PM register without
losing the load-bearing signal. The output is wrapped in a markdown
code block so the bridge member cannot accidentally paraphrase around
it; the receiving party (the PM, or the engineering peer) parses the
block as the canonical translated body.

## When to invoke

- Before relaying any inbound technical signal to the human PM
  (`--up`).
- Before posting any PM intent / scope / acceptance criterion into the
  technical session (`--down`).
- Before consolidating a multi-source status report for the PM
  (`--up` per source then assemble).

Skip the skill only when the message is already plain-language (e.g.
the PM asking "is feature X done yet") AND the answer is also plain-
language (e.g. "yes, shipped last Friday"). Any message containing a
commit SHA, a parley `Kind.*` constant, a technical class name, or a
PR-state phrase ("PR-READY", "PASS-WITH-AMEND", etc.) goes through the
skill.

## Output discipline

ALL output of this skill is wrapped in a fenced markdown block with
the language tag `pm-translation`:

````
```pm-translation
<translated body>
```
````

The opener / closer is the skill's contract. A receiving PM looks for
the block; a receiving engineering peer parses around it. Output
outside the block is a translation-discipline violation.

## --up — engineering → PM

Rewrite an engineering-register signal into PM-register plain language.
Patterns:

| Engineering signal                       | PM translation                                |
|------------------------------------------|-----------------------------------------------|
| commit SHA `abc1234`                     | the change shipped                            |
| `Kind.LAND` / "LANDed"                   | shipped                                       |
| `PR-READY`                               | ready for review                              |
| `Kind.RATIFY_OR_CORRECT`                 | needs your decision                           |
| `Kind.PREMISE_GAP`                       | we found something that changes the plan     |
| `PASS-WITH-AMEND` (non-blocking)         | shipping with minor follow-ups noted          |
| `PASS-WITH-OBS-LOW`                      | shipped; small observations to address later  |
| `RED` / `RED-without`                    | found a failing test (the proof we wanted)    |
| `GREEN` / `GREEN-with`                   | tests pass                                    |
| `cohort` / `3-leg cohort`                | parallel work stream (3 people working on it) |
| `cert` / `verdict` / `verifier`          | independent review                            |
| `chunk-0 forensics`                      | initial investigation                         |
| `force_wake` / `idle-by-design`          | (internal scheduling — usually omit)          |
| `standing pre-auth`                      | pre-approved to proceed                       |
| `worktree` / `branch off origin/main`    | working copy on a separate branch             |
| `merge into main` / `LAND`               | merged into the main release line             |
| `defect-NN`                              | issue NN (use the issue title if known)       |
| `substrate` / `substrate fix`            | the underlying system (usually omit detail)   |
| `HR-#N`                                  | rule N (use the rule name if known)           |

Worked example:

Input:

> par-p0-defect-55 PR-READY at 7a3f12c on par-p0-defect-55-impl —
> 11-axis cert envelope GREEN, HR-#1/4/5/6/7/8 sweep clean, §2.2
> open-Q DEFER concurred by par-plan.

Output:

````
```pm-translation
The PM-bridge feature is ready for review. All 11 acceptance criteria
pass and no rules were violated. The one open design question (whether
to add a self-review mode) has been deferred to v2 by the planner.
```
````

## --down — PM → engineering

Rewrite a PM-register intent into a structured engineering request.
The output should resolve the canonical engineering ambiguities:
**WHAT** (the deliverable), **WHY** (the user-visible value), **DONE
WHEN** (acceptance criteria), **OPEN** (anything the PM hasn't
decided).

Patterns:

| PM intent                                  | Engineering rewrite                            |
|--------------------------------------------|------------------------------------------------|
| "we need X by Friday"                      | scope + acceptance criteria + deadline         |
| "make X easier to use"                     | concrete UX changes + measure of "easier"      |
| "support Y customers"                      | numeric concurrency / load target              |
| "looks good to ship"                       | RATIFY (with caveats if any)                   |
| "I want to see what we have"               | demo / status report request                   |
| "this doesn't feel right"                  | reject + ask for the specific concern          |
| "can we also do Z?"                        | new scope item — surface separately, do not    |
|                                            | bundle silently into the in-flight work        |

Worked example:

Input (PM):

> The login screen feels slow on mobile. Can we make it snappier? I
> think we should ship this in the next release.

Output:

````
```pm-translation
WHAT: improve perceived login latency on mobile.
WHY: PM reports the current login flow feels slow on mobile devices.
DONE WHEN:
  - login-screen Largest Contentful Paint < 2.5s on a mid-range Android
    over 4G (concrete measure for "snappier"; confirm with PM)
  - included in the next release cut
OPEN:
  - exact target devices + network class (mid-range vs. low-end?)
  - whether to also address the slow-on-desktop case
  - whether to fold this into the in-flight auth refactor or ship it
    standalone
```
````

The `OPEN` section is load-bearing — it surfaces back to the PM as
"questions I still need answered" via `--up` on the next cycle.

## Repo-specific overlay

If `$REPO/docs/conventions/translate-overlay.md` exists, its
patterns extend the canonical pattern tables above. The overlay file
documents repo-specific jargon that the canonical patterns don't
cover (product names, internal acronyms, customer-segment labels,
etc.). When the overlay is absent, the skill operates on canonical
patterns only.

The overlay file format mirrors this skill's pattern tables —
markdown tables with `| <engineering signal> | <PM translation> |`
rows. The skill appends the overlay rows to the canonical rows
in-place; no merge logic, no precedence rules beyond "overlay wins
on duplicate keys".

## Escalation — when not to translate

If the inbound message contains a technical detail the bridge cannot
plain-language without inventing (a specific architecture choice, a
specific performance number, a specific dependency name), surface
it as an open question rather than guess:

````
```pm-translation
The engineering team has reported a development that may affect the
plan. They mentioned: "<raw technical phrase>". I'm escalating this
to the appropriate technical lead for plain-language clarification
before passing it on.
```
````

The `OPEN QUESTIONS:` line in the report format is the routine
surface for this; this escalation form is for the case where a
single phrase is the load-bearing signal.

## Anti-patterns

- Do **not** drop the `pm-translation` block fence — receiving parties
  parse around it.
- Do **not** invent a technical detail the source message did not
  contain. If unknown, surface as `OPEN`.
- Do **not** translate `--up` and `--down` in the same invocation —
  the directions are opposite; chain calls if needed.
- Do **not** include parley substrate jargon (`force_wake`, `idle-by-
  design`, `standing pre-auth`, `chunk-N`) in `--up` output unless
  the PM has explicitly asked about the substrate. The "(internal
  scheduling — usually omit)" guidance in the pattern table applies.
- Do **not** echo a raw commit SHA in `--up` output unless the PM has
  asked for a release identifier. "the change shipped" or "the fix
  shipped on $DATE" is the canonical surface.
