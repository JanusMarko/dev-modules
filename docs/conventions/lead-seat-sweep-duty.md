---
name: lead-seat-sweep-duty
tier: 1
applies_when:
  - you are a planner / lead / PM seat with custody of a shared working tree
  - a tree delta (modified or untracked files) is older than ~1 day with no WIP
    claim, no dispatch, and no handoff reference
when_not_to_apply:
  - the delta carries a live WIP claim (docs/wip/) or a named owner mid-arc
  - single-seat worktrees (worktree-per-worker isolates by construction; the
    duty is for SHARED trees)
origin:
  date: 2026-06-10
  context: 'Crash lessons-learned pass (Kris directive msg-15dae5951227, review-lead
    wsl-plan collation msg-e25880822edd, CTO ratify msg-889211d8fe09). At the
    crash the maxai shared tree held a 2-day-old uncommitted substrate-sync
    delta (30 files, +2911/-227) with NO WIP claim, no dispatch, no handoff ref.
    Shared-tree multi-seat discipline makes every seat correctly refuse to
    commit unowned mods ("not mine") — individually right, globally a standing
    loss exposure. The companion finding: maxai HAD /record-wip (4h-expiry WIP
    claim entity) purpose-built for exactly this; it went unused — mechanism ≠
    habit; shipping the skill is the easy half. Merged from ma-plan lessons 2 +
    3. The WL-side mechanism half is the validator git-cleanliness advisory
    (workshop-lite issue filed same pass).'
see_also:
  - push-early-unconditional
  - detached-index-protective-snapshot
  - worktree-branch-hygiene
---

# Lead-seat sweep duty: no unowned tree delta older than a day

## Rule

The planner/lead seat with custody of a shared tree sweeps it on a
~daily cadence: any delta older than ~1 day carrying **no WIP claim
and no owner** gets either (a) a protective commit to a `wip/*`
branch (pushed, per [[push-early-unconditional]]; use
[[detached-index-protective-snapshot]] on live shared trees), or
(b) an assigned owner with a WIP claim. This converts the
unowned-delta state from indefinite to bounded.

## Why

Multi-seat discipline makes every individual seat refuse to commit
work that isn't theirs — correct locally, but globally it means
nobody protects orphaned work, ever. The 2026-06-10 crash found a
30-file, 2-day-old unowned delta that survived on filesystem luck
alone. The sweep duty assigns the global responsibility the local
rule structurally leaves vacant — and supplies the habit half for
WIP-claim mechanisms that otherwise sit unused.

## When to apply

Daily-ish on shared trees you have custody of; immediately after any
host disruption (the sweep is step one of the recovery audit).

## When NOT to apply

Claimed deltas mid-arc; isolated per-seat worktrees.

## See also

[[push-early-unconditional]], [[detached-index-protective-snapshot]],
[[worktree-branch-hygiene]].
