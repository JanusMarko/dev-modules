---
name: memory-audit-and-promote-pattern
tier: 1
applies_when:
  - seat-class boots with substantial local memory (`~/.claude/projects/<slug>/memory/`)
  - operator suspects silent divergence between two seats' applied rules
  - a Kris-binding rule was added to one seat's memory and the operator wants it cross-seat universal
  - periodic substrate-governance hygiene (recommended ~monthly per active seat-class)
when_not_to_apply:
  - seat with only project-local context (no Kris-binding rules; memory IS local)
  - a single isolated seat that does not coordinate with peers (no divergence risk)
  - in the middle of a load-bearing arc (promotion is forward-only and a substrate-touch — wait for clean seam)
origin:
  date: 2026-06-05
  context: 'Cohort U (wl:2026-06-04-02 memory-audit-and-promote-pattern) — surfaced by @plan (dev-mgmt CTO) 2026-06-04 after conversation with Kris. Source issue identifies a silent-divergence class: per-CC-project auto-memory is local-to-the-seat; cross-seat-applicable Kris-binding rules siloed in one seat`s memory don`t reach the peer seat. par-plan had begun a partial migration via `[PROMOTED → <target>]` stub tags; this convention generalizes that pattern as Tier-1 workshop-lite substrate.'
see_also:
  - dev-mgmt:plan memory header (architectural model precedent)
  - parley/docs/conventions/INDEX.md (cross-substrate target)
source_issue: 2026-06-04-02-memory-audit-and-promote-pattern-cross-seat-applicable-rules-belong-in-conventions-first-pass-on-dev-mgmt-plan-memory
---

# Memory-audit-and-promote pattern

## Rule (the pattern)

Per-CC-project auto-memory is local to one seat. When a Kris-binding rule
is cross-seat applicable, **it does not belong in local memory** — it belongs
in a Tier-1 convention doc in the appropriate substrate, where every peer
seat discovers it through substrate inheritance.

The pattern: **inventory → classify → promote → reconcile**.

1. **Inventory** — enumerate every entry in the seat's local
   `MEMORY.md` + every `feedback_*.md` / `project_*.md` / `reference_*.md`
   file under `~/.claude/projects/<slug>/memory/`.

2. **Classify** each entry into one of FOUR bins (the user-pref bin is
   the v1.1 amendment per devil-advocate review 2026-06-05-15, finding
   HIGH-2):

   - **Universal substrate convention** — a coordination / substrate
     / engineering rule that applies to ANY seat doing similar work,
     cross-cwd. Examples: "CTO is structurally responsible for
     unblocking its members" (kris-never-the-relay); "silence
     directives MUST distinguish IDLE from BLOCKED"; HARD-HALT
     context threshold; cross-substrate parley footguns. → **Promote**
     to the Tier-1 convention substrate of the substrate that
     originated the rule (`workshop-lite/docs/conventions/` for
     workshop-lite-class rules; `parley/docs/conventions/` for
     parley-class rules).
   - **User-scoped operator preference** — a personal-discipline
     rule of the operator (Kris) that any seat working with them
     should know, but is NOT a substrate-technical convention.
     Examples: question-format-pattern (positional ranking with
     (a)=Recommended), telegram-html-night-mode-default,
     pm-translator-plain-english. → **Promote** to the user-scoped
     preference store (workshop-lite ships this at
     `.claude/preferences.toml` via the
     `.claude/scripts/dev-mgmt/preferences.py` Storage interface
     shipped Sprint wl.15) — OR, for parley-side preferences, to
     `~/.claude/projects/-home-krisd-code-parley/memory/_rules.yaml`
     per par-plan's doctrine layout. **Don't put operator preferences
     in substrate conventions** — workshop-lite is portable; one
     operator's preferences shouldn't ride along with the tool.
   - **Cross-cwd project-class-scoped** — applies to all seats of a
     project class (e.g. "all parley-substrate-fix seats"; "all
     workshop-lite-builder seats") but not universally. → **Promote**
     to that project's convention substrate.
   - **Genuinely local** — this seat's specific posture choices,
     project context, ongoing-arc state. → **Keep** in local memory.

3. **Promote** — write the convention doc at the chosen target. Then
   replace the local memory file with a stub pointer:

   ```markdown
   [PROMOTED → <target>]
   ```

   In `MEMORY.md`, prepend `[PROMOTED → <target>]` to the entry's
   description line. The body of the file becomes a one-line pointer:
   `Promoted to <substrate>/docs/conventions/<slug>.md on <date>.`

4. **Reconcile** — at the next fresh-seat boot, the seat inherits all
   universal conventions through substrate (workshop-lite installs the
   workshop-lite conventions; parley sessions inherit parley
   conventions). Local memory is now read only for seat-specific
   context (posture, project state, active-arc anchors).

## Discoverability — how promoted rules reach a fresh seat

Important amendment per devil-advocate review 2026-06-05-15 (finding
HIGH-1, context-window-eviction-via-promotion):

**CC project memory is auto-injected into the agent's system context.
Convention docs are NOT.** Moving a rule from `~/.claude/projects/<slug>/memory/`
to `<substrate>/docs/conventions/<slug>.md` is a deliberate shift from
auto-injected-always to on-demand-discoverable. Discoverability is
preserved by THREE mechanisms working together:

1. **Stub pointer in source memory (per-seat retention).** When you
   stub the source memory file with `[PROMOTED → <target>]`, the
   pointer line **stays in the seat's auto-injected MEMORY.md
   context**. The agent still sees "there's a rule about <topic>;
   see <target>" — they spend ONE `Read` tool call to fetch the
   convention body when the rule fires. This is by design: per-seat
   memory cost falls (the stub is one line vs. multi-paragraph body);
   shared substrate cost rises (one Read per fire). Net win when
   the rule is cross-seat-applicable AND fires infrequently.

2. **CLAUDE.md cross-link to `docs/conventions/INDEX.md`** at the
   substrate root. Every workshop-lite consumer's CLAUDE.md should
   reference the conventions index in its "Mandatory first reads"
   or equivalent section, so fresh seats discover the substrate
   surface even without any local memory pointer. (See `CLAUDE.md`
   in this repo for the pattern.)

3. **Per-skill `## See also` cross-links + soft `[[name]]` linker
   syntax.** Conventions reference each other; an agent invoking one
   skill / reading one convention finds adjacent rules by following
   links. This is the same shape parley `docs/conventions/INDEX.md`
   uses (organized by section heading: orchestration / idle / PM
   ritual / substrate / etc.).

**The cost trade-off is deliberate.** A rule in local memory is
"free" to retrieve (auto-injected) but per-seat (silent divergence
risk). A rule in a convention costs one Read on fire but is
single-source-of-truth (no divergence). When a rule fires often AND
is cross-seat, promotion is net-positive. When it fires rarely OR
is genuinely local, leave it in memory.

**Special case: stub-less fresh-substrate-install seats.** A fresh
seat that has never had local memory entries (e.g. first boot of a
new seat-class after workshop-lite install) has no stub pointers at
all. For such seats, discovery is via CLAUDE.md → conventions/INDEX
only. The convention-doc authors should write `applies_when` /
`when_not_to_apply` frontmatter carefully so an agent grepping the
INDEX for "do I have a rule about <topic>?" finds the right doc.

## Why

Per-CC-project auto-memory is local to the seat. dev-mgmt:plan's memory
lives at `~/.claude/projects/-home-krisd-code-dev-mgmt-session/memory/`;
par-plan's lives at `~/.claude/projects/-home-krisd-code-parley/memory/`;
each cohort builder seat in workshop-lite has its own slug. Different
files, different sets, different judgment overlays.

This creates a **silent divergence risk** for any cross-seat Kris-binding
rule that the operator believed was universal but in fact lives only in
one seat's local memory. Two seats can apply different judgment to the
same situation without anyone noticing — until the gap surfaces as a
coordination breakdown.

Concrete examples surfaced 2026-06-04 between the operator and dev-mgmt:plan:

- dev-mgmt:plan has `feedback_cto_not_sm_role_discipline` —
  role-boundary rule — but par-plan probably does not.
- par-plan has `feedback_auto_action_bridge_authorized` — autonomy
  boundary — but dev-mgmt:plan probably does not.

Several of these are clearly cross-seat Kris-binding rules that should
apply to BOTH seats — and currently don't, because they live in one
seat's local memory only.

par-plan already has a partial architectural answer documented in their
`MEMORY.md` header (post-par-p0-cleanup9 doctrine-YAML migration,
2026-06-01):

> Rule-shaped doctrine lives in TWO stores: substrate-portable
> conventions → `parley/docs/conventions/*.md` (Tier-1, ships with
> parley install); per-machine Kris-discipline rules →
> `~/.claude/projects/-home-krisd-code-parley/memory/_rules.yaml`
> (NOT shipped with parley).

The model: rules that need to apply across seats / cwds / repos belong
in **Tier-1 conventions** (substrate-portable, ship-with-install,
discoverable by any agent reading the substrate). Memory should only
carry genuinely-local seat preferences + project context.

This convention generalizes that par-plan precedent as the workshop-lite
substrate pattern any seat-class can apply.

## When to apply

- **At seat-class boot** when the seat has substantial accumulated
  local memory (≥10 feedback files). Run the audit, surface promotion
  candidates, then proceed with the active work.
- **When the operator surfaces a divergence** ("should rule X be
  universal?"). The audit's classification table forces the explicit
  decision.
- **Periodically** — ~monthly for active seat-classes — as
  substrate-governance hygiene. Memory entries accumulate; new ones
  may have been added since the last audit.
- **When promoting a single rule on-demand** — the audit doesn't have
  to be exhaustive. If a single memory entry is clearly universal,
  promote it inline (steps 3+4 only).

## When NOT to apply

- **Seat with only project-local context.** Many builder seats only
  accumulate project-state memory (active sprint, in-flight arc,
  ratify cycle) — there are no Kris-binding rules to promote. Audit
  would return all-Local.
- **A single isolated seat with no peers.** No divergence risk.
- **Mid-arc.** Promotion is forward-only and a substrate-touch.
  Wait for a clean seam (post-LAND, pre-next-dispatch). Mid-arc
  substrate writes risk colliding with active charter work.

## Procedure (step-by-step for an agent running the audit)

### Step 1 — Inventory

```bash
ls ~/.claude/projects/<your-project-slug>/memory/
```

Read `MEMORY.md` for one-line summaries; read individual files for
content needed to classify.

### Step 2 — Classify

For each entry, decide: **Universal / Cross-cwd-scoped / Local**.

Heuristics:

| Signal | Bin |
|--------|-----|
| Rule references a coordination / substrate / engineering doctrine that applies across cwds (kris-never-the-relay, HARD-HALT threshold, governance-must-be-durable) | Universal substrate convention |
| Rule references how the **operator** likes to be communicated with / formats they prefer / personal-discipline preferences (question-format-pattern with (a)=Recommended; telegram-dark-mode; PM-translator plain-English) | User-scoped operator preference (route to `.claude/preferences.toml` or parley `_rules.yaml`) |
| Rule cites a parley/workshop-lite substrate behavior agnostic of project | Universal substrate convention or Cross-cwd-scoped |
| Rule cites a cohort/sprint/seat-class (e.g. "FULL-3-leg for substrate-fix arc") | Cross-cwd-scoped (to that seat-class) |
| Rule cites a specific arc/project state ("pre-net re-review directive 2026-05-15") | Local |
| Rule is posture / methodology / judgment ("how I personally surface decisions") | User-scoped operator preference (if Kris-binding) OR Local (if seat-specific posture only) |
| Rule is a workaround for a substrate bug already filed | Cross-cwd-scoped (to substrate consumers) UNTIL the bug LANDs; then archive |

**Disambiguating Universal substrate convention vs. User-scoped operator
preference:** ask "if a different operator adopted workshop-lite, would
this rule still apply unchanged?". If yes → substrate convention. If no
(it's about Kris's specific preferences) → user-pref. Examples:
"silence directives must distinguish IDLE from BLOCKED" is substrate
(any operator's coordinator wants this). "(a) is always the recommended
option" is user-pref (Kris's specific scanning preference).

Produce a table — markdown or CSV — with columns:
`file` | `one-line summary` | `bin` | `target if promoting` | `rationale`.

### Step 3 — Surface for ratify

**Promotion is not unilateral.** Cross-seat Kris-binding rules
require seat-class CTO / plan ratify before landing as conventions.
Surface the table (or the top candidates) via the seat-class's
ratify-routing convention:

- **dev-mgmt:plan seat** → surface to `@plan` (dev-mgmt CTO) via
  parley say.
- **workshop-lite cohort builder seat** → surface to `@wsl-plan`
  (workshop-lite scrum-master) who forwards to `@plan` for
  substrate-governance scope.
- **parley-side promotion target** → surface via `@plan-relay` to
  `@par-plan` (parley CTO) per workshop-lite Hard Rule #1
  (parley-agnostic at base — workshop-lite never directly writes
  to parley repo).

### Step 4 — Promote ratified candidates

For each ratified candidate:

1. Write the convention doc at the target substrate's
   `docs/conventions/<slug>.md` with the canonical frontmatter
   (`name`, `tier`, `applies_when`, `when_not_to_apply`, `origin`,
   `see_also`, `source_memory`).
2. Update the target substrate's `docs/conventions/INDEX.md` with a
   one-line entry in the appropriate section.
3. Stub the source memory file:

   ```markdown
   [PROMOTED → <substrate>/docs/conventions/<slug>.md]

   Promoted on <date>. See target for canonical rule.
   ```

4. Update the source `MEMORY.md` index line:

   ```markdown
   - [PROMOTED → <substrate>/docs/conventions/<slug>.md](feedback_<original>.md) — <one-line original summary>
   ```

5. Commit + push. For cross-substrate promotions (e.g. workshop-lite
   memory → parley convention), the parley-side write is performed
   by @par-plan or their delegate; workshop-lite never directly
   writes to the parley repo.

### Step 5 — Reconcile

At the next fresh-seat boot:

- Substrate-portable conventions are inherited via install (no
  per-seat action).
- Local memory is read for posture / project state only.
- Stubbed files still appear in MEMORY.md but with `[PROMOTED → …]`
  prefix — they are pointers, not rules.

## Forward-only discipline

**Promotion is forward-only.** Do not delete the source memory file;
stub it. Two reasons:

1. **Audit trail.** The source memory may have additional context
   (the "why this was learned" anecdote, the originating msg-id)
   that doesn't fit cleanly in the convention doc but is valuable
   for future debugging.
2. **No orphan window.** During the cross-substrate promotion (e.g.
   memory → parley/docs/conventions/), the source memory remains the
   canonical source until the convention PR merges. Stubbing
   post-merge means there is never a window where the rule lives
   nowhere.

## Cross-substrate touch rules

- **Workshop-lite is parley-agnostic at base** (Hard Rule #1).
  Workshop-lite never writes to parley repo. Cross-substrate
  promotions go through @par-plan via @plan-relay.
- **User-scoped preferences route to per-machine stores, not
  substrate conventions.** Workshop-lite's user-scoped preference
  system at `.claude/scripts/dev-mgmt/preferences.py` (Sprint wl.15)
  + `.claude/preferences.toml` is the canonical workshop-lite
  user-pref store; parley's `_rules.yaml` at
  `~/.claude/projects/-home-krisd-code-parley/memory/_rules.yaml`
  is the canonical parley-side user-pref store. Substrate
  conventions are reserved for cross-operator-portable rules.

## Anti-patterns

### Auto-sync memory across seats

Tempting but wrong. Sync invites accidental coupling (one seat's
posture-choice pollutes another's). The classification step forces
explicit "is this universal?" judgment, which prevents the wrong
rules from spreading.

### Delete-not-stub the source

Loses audit trail; creates an orphan window. Always stub.

### Promote without ratify

The classification table is the agent's draft. The CTO/plan ratify
is what makes a rule load-bearing across seats. Unilateral promotion
risks shipping a rule that isn't actually universal — and now lives
in two places (memory + convention) drifting in opposite directions.

### Promote arc-specific state

"Pre-net re-review directive" and similar one-arc state should NOT
be promoted. It's project state, not a rule. Even though it's
durability-bearing, it stays in memory or moves to a sprint /
runbook / dispatches entry.

### Promote workarounds for filed bugs

If memory entry is a workaround for a substrate bug already filed,
promoting it ossifies the workaround. Instead: link the memory entry
to the substrate issue in `linked_issues`; archive once the bug LANDs.

## Examples

### Good — Universal Kris-binding promote

dev-mgmt:plan memory has `feedback_hard_halt_threshold_40_free.md`
("HARD-HALT is 60%-used / 40%-free"). This is a Kris-binding rule
that applies to every parley member operator. Promote to
`parley/docs/conventions/member-hard-halt-threshold-40-free.md`
(already done by par-plan 2026-06-01). Stub the source memory.

### Good — Cross-cwd scoped promote

dev-mgmt:plan memory has `feedback_full_3leg_default_substrate_fix_arc.md`
("FULL-3-leg builder+tester+verifier is standing for parley
substrate-fix arc"). This applies to all parley-substrate-fix
cohorts but not universally. Promote to
`parley/docs/conventions/full-3leg-default-substrate-fix-arc.md`.
Workshop-lite-only seats don't need this rule.

### Good — Genuinely local, keep

dev-mgmt:plan memory has
`project_autonomous_arc_2026_05_15.md` (specific arc state from
2026-05-15). Active project context, not a rule. Keep in local
memory.

### Bad — Mis-classification of arc state as universal

Promoting `project_prenet_rereview_directive_and_state.md` (specific
arc state) to a convention would ossify project state as a rule. Keep
it as project memory or move to a runbook / sprint entry.

## See also

- **par-plan precedent** — `~/.claude/projects/-home-krisd-code-parley/memory/MEMORY.md`
  header (post-par-p0-cleanup9 doctrine-YAML migration); 7 promoted entries
  with `[PROMOTED → <target>]` tags as of 2026-06-01.
- **Source issue** — `wl:2026-06-04-02` (substrate-governance MEDIUM);
  cohort U built this convention against it.
- **CLAUDE.md Hard Rule #1** — parley-agnostic at base. Governs
  cross-substrate promotion direction (workshop-lite never writes
  directly to parley).
- **`/audit-memory` skill (optional)** — scaffolded for future
  seat-classes; walks an agent through inventory + classify + surface.
  See `.claude/skills/audit-memory/SKILL.md` if shipped.
