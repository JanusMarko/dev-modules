---
name: memory-scope-curate-not-accrete
tier: 1
applies_when:
  - writing-handoffs-or-other-durable-entities-across-a-long-session
  - reviewing-the-docs-entity-corpus-for-drift-or-bloat
  - deciding-whether-to-add-a-new-index-row-or-fold-an-old-one
  - onboarding-a-seat-that-will-accrete-pre-compact-handoff-stubs
when_not_to_apply:
  - the repo is not workshop-lite-installed (no docs/<kind>/ entity corpus)
  - a host-harness auto-memory system (e.g. Claude Code per-project
    ~/.claude/projects/.../memory/) is in scope — that is NOT WL's surface;
    WL curates only its own durable entity corpus + user-scoped preferences
origin:
  date: 2026-06-10
  context: 'WL-side fold of ledger rec #14 (memory_scope=curate +
    curator/librarian; tier E; wsl-plan + par-plan; Wave-3). Names the
    curate discipline already implicit in the substrate (handoff_aging
    supersession folding + INDEX-per-folder coherence + pending_views)
    rather than inventing a new mechanism. Design:
    docs/design/2026-06-10-wl-layer-c-prompt-pack-render-seam.md §7.'
see_also:
  - governance-layer-must-be-durable
  - runbooks-consult-before-reinventing
  - worktree-branch-hygiene
source_msg_ids:
  - msg-a4b2ef914b26  # rec #14 ledger source
linked_issues:
  - 2026-06-10-04-rec-14-memory-scope-wl-side-curate-policy-convention-doc-validator-coherence-extension
linked_decisions:
  - dev-mgmt:D7
---

# Memory scope: curate, don't accrete

## Rule

WL's durable "memory" is its **entity corpus** — the
`docs/{decisions,reviews,issues,handoffs,conversations}/` tree plus the
user-scoped preferences at `.claude/preferences.toml`. That corpus is
**curated, not append-only accreted**. Three concrete disciplines:

1. **Handoffs supersede rather than accrete.** Empty pre-compact handoff
   stubs are aging noise, not durable record. Fold them via
   `python3 .claude/scripts/dev-mgmt/cli.py aging` (the
   `handoff_aging.py` supersession chain: archive / merge-into-prev /
   delete strategies, non-destructive by default). The most-recent
   stub stays full-form as the actionable resume cursor; the rest fold.
2. **The INDEX is the curated view — the librarian surface.** Each
   entity folder's `INDEX.md` is the source of truth for what exists,
   not the raw `ls` of the directory. Keep INDEX rows in sync with the
   filesystem (the validator's `index_coherence` check flags drift in
   both directions); when an entity is superseded, the INDEX reflects
   its current status, not its birth status.
3. **Cross-links resolve.** A `linked_<kind>` pointer to a slug that no
   longer exists is un-curated accretion; the validator's
   `cross_link` check surfaces orphans.

## Why

Append-only memory grows without bound and buries the signal: a session
that writes a pre-compact stub every compaction leaves dozens of
near-identical boilerplate handoffs, and a reader (human or freshly
respawned seat) can no longer tell which record is load-bearing.
Curation keeps the corpus's signal-to-noise high so the substrate stays
a reliable orientation surface across reseats. This is the **librarian**
discipline: the INDEX-per-folder convention already shipped — name it
and use it, don't reinvent a parallel memory system.

## When to apply

- Any long-running seat that accretes pre-compact handoff stubs: fold
  periodically (or let the aging policy run) rather than letting stubs
  pile up.
- Before treating `ls docs/handoffs/` as the handoff history — read the
  INDEX instead.
- When the validator surfaces `memory_scope_uncurated_handoff`,
  `index_coherence`, or `cross_link` advisories — these are the audit
  surface for un-curated accretion. They are **advisory** (HR-5/D33
  hooks never block; D43 `--strict` is the only non-zero path); curate
  at a clean seam, not mid-task.

## When NOT to apply

- Do not fold the most-recent pre-compact stub — it is the actionable
  resume cursor (the aging policy keeps the N most-recent by design).
- Do not delete substantive hand-authored handoffs; the stub detector
  is binary + structural (`is_empty_pre_compact_stub`) and never folds
  a handoff carrying real content.
- This convention governs WL's **own** corpus only. It does not reach
  into a host adapter's auto-memory (HR-1: WL is adapter-agnostic at
  base).

## Examples

- A 1M-token session has written 40 pre-compact stubs. Running
  `cli.py aging` archives 37, keeps the 3 most-recent, and refreshes
  both the main and archive INDEX — the corpus is curated, the resume
  cursor preserved.
- A Decision is superseded by a newer one. The curated INDEX row shows
  `status: superseded`; the raw file still exists for provenance, but
  the INDEX (the librarian view) tells a reader it is no longer live.

## See also

- [[governance-layer-must-be-durable]] — what MUST be durable; this
  convention is the complement (what durable record should be curated).
- [[runbooks-consult-before-reinventing]] — the librarian surface
  already exists; consult it rather than building a new memory system.
- Render half: the Layer-C pack `memory_scope` section
  (`workshop_lite_pack.build_memory_scope_section`) surfaces this policy
  into the spawn-time prompt pack.
- Audit half: `validate._check_memory_curation` +
  `handoff_aging.detect_stubs`.
