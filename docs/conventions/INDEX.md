# Workshop-lite Conventions — Tier 1

Workshop-lite substrate-portable Tier-1 conventions. Each doc captures a
cross-seat-applicable rule discoverable by any agent reading the
workshop-lite substrate (after `parley adopt-workshop-lite` or direct
install).

**Tier 1 = portable**: load-bearing across any workshop-lite consumer
(any seat-class that runs in a workshop-lite-installed repo). These
docs describe workshop-lite-substrate-level discipline, not
project-specific patterns.

**Doc shape**: each doc has frontmatter (`name`, `tier`, `applies_when`,
`when_not_to_apply`, `origin`, `see_also`, `source_memory` if promoted
from per-seat memory) + body (Rule / Why / When to apply / When NOT to
apply / Examples / See also). Cross-links use `[[name]]` (soft links —
broken links don't fail; this INDEX is the source of truth).

---

## Substrate governance

- [memory-audit-and-promote-pattern](memory-audit-and-promote-pattern.md) — the inventory → classify → promote → reconcile pattern for moving cross-seat-applicable operator-binding rules out of per-seat local memory into Tier-1 conventions; established 2026-06-05 via cohort U (wl:2026-06-04-02)
- [governance-layer-must-be-durable](governance-layer-must-be-durable.md) — operator directives + design inputs + backlog defects MUST be reboot-durable the moment received (memory file / Kind.DECISION / committed doc); promoted cohort U 2026-06-05 from dev-mgmt:plan memory
- [shared-term-registry](shared-term-registry.md) — local Workshop-Lite shared-term registry instance for C3b naming checks; pins collision-prone WL senses and tombstone-points shared terms to the org shared tier; established 2026-07-05 from shared-term-registry standard @f10e8ec

## Coordinator / CTO discipline

- [kris-never-the-relay](kris-never-the-relay.md) — the operator must never be the relay to wake a coordinator to do its own job; coordinators own their members' unblock path; operator-escalation is last-resort only and framed as "coordinator unresponsive"; promoted cohort U 2026-06-05 from dev-mgmt:plan memory
- [silence-policy-never-binary](silence-policy-never-binary.md) — silence directives MUST distinguish IDLE-BY-DESIGN from BLOCKED/STALLED + enumerate stall-detection; conflating the two creates invisibility; promoted cohort U 2026-06-05 from dev-mgmt:plan memory

## Crash durability (2026-06-10 lessons-learned pass — Kris directive msg-15dae5951227, ratify msg-889211d8fe09)

- [push-early-unconditional](push-early-unconditional.md) — every land-*/wip branch pushed at creation; merge-held ≠ push-held; local-only commits are single-copy host risk; merged from CTO-b + par-plan-B + ma-plan-2
- [evidence-persists-never-tmp-only](evidence-persists-never-tmp-only.md) — gate-critical run output persists to repo/$HOME at capture time; /tmp is a proven reboot loss vector (6 bench rounds + full-suite logs lost 2026-06-10); merged from CTO-c + bench-L1 + par-plan-A
- [arc-close-handoff-discipline](arc-close-handoff-discipline.md) — handoff at every arc close (not only session boundary) incl. delivery msg_ids + artifact inventory; fast arcs outrun session-boundary cadence; natural-experiment-proven (bench-L2 + par-plan-failure-3)
- [lead-seat-sweep-duty](lead-seat-sweep-duty.md) — planner seat with shared-tree custody sweeps ~daily: unowned delta >1d gets protective wip/ commit or assigned owner; supplies the habit half for WIP-claim mechanisms (ma-plan-2 + ma-plan-3)
- [detached-index-protective-snapshot](detached-index-protective-snapshot.md) — GIT_INDEX_FILE detached-index recipe = THE way to protect single-copy work on live shared trees; zero disturbance to shared HEAD/index/tree; proven in anger (ma-plan-4)

## Substrate hygiene

- [runbooks-consult-before-reinventing](runbooks-consult-before-reinventing.md) — consult the runbook before authoring status reports / respawn orientation / wind-down / charter templates / LAND+LOAD+BROADCAST from scratch; memory is not the answer, substrate is; promoted cohort U 2026-06-05 from dev-mgmt:plan memory
- [worktree-branch-hygiene](worktree-branch-hygiene.md) — branch-per-cohort + worktree-per-seat + merge-to-main + post-LAND-prune model; codifies when to create worktrees / canonical branch naming patterns (cohort-id / sprint-id / issue-id; avoid platform-named + auto-spawn-hash) / cleanup triggers (post-LAND + 7d stability window; 90d idle; charter abandonment) / verifier-finding-absorption disposition / HR-style enforcement candidates + advisory validator hooks; informed by Q3 archeology empirical inventory (~115 artifacts); originated 2026-06-08 from @plan dispatch msg-6087e6eec91d
- [memory-scope-curate-not-accrete](memory-scope-curate-not-accrete.md) — WL's durable entity corpus (docs/<kind>/ + preferences) is curated, not append-only accreted; handoffs supersede (fold via cli.py aging), INDEX-per-folder is the librarian/curated view (not raw ls), cross-links resolve; the validator's memory_scope_uncurated_handoff / index_coherence / cross_link advisories are the audit surface; WL-side fold of ledger rec #14, originated 2026-06-10

## Cohort discipline

- [cohort-shape-variant-pre-declaration](cohort-shape-variant-pre-declaration.md) — every cohort charter §3 MUST explicitly pre-declare the variant (FULL-3-leg / LIGHT-3-leg / builder-own-cert-only) with rationale citing scope class + HR constraints + precedent; mid-flight variant shifts require pre-LAND ratify via [VARIANT-SHIFT-PROPOSAL] surface; silent collapse forbidden even when cert + full-suite pass; originated 2026-06-08 from WL.29 LAND incident per @plan process note msg-226f572bc002 + dispatch msg-cba8d37afd49

---

## Cross-tier references

Some entries here cross-link to other tiers' conventions (in other
repos). Soft links — broken `[[name]]` references don't fail.

- **Parley Tier-1** — `parley/docs/conventions/` — parley-substrate
  discipline (HARD-HALT thresholds, parley-say footguns, cohort
  policy). Cross-substrate promotion source / target.

When a doctrine applies across all repos using workshop-lite, it
lives here at Tier-1. When it's specific to one consumer repo, it
lives at that repo's Tier-2 conventions or higher.

## Promotion provenance

See `docs/issues/2026-06-04-02-memory-audit-and-promote-pattern-...`
for the source issue defining the audit pattern + the dev-mgmt:plan
first-pass audit. Per-seat audit tables live alongside the audit run
that produced them (typically a sibling issue or sprint folder).
