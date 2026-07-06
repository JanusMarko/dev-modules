---
name: push-early-unconditional
tier: 1
applies_when:
  - a land-* / wip/* / cohort branch was just created with unique commits
  - work exists as commits on a local-only branch in any repo
  - a land-gate is HELD but the branch carrying the candidate commits is unpushed
when_not_to_apply:
  - secrets or credentials in the commits (fix the commit first; never push secrets)
  - the remote itself is the thing being repaired (e.g. force-push recovery in progress)
origin:
  date: 2026-06-10
  context: 'Crash lessons-learned pass (Kris directive msg-15dae5951227, review-lead
    wsl-plan collation msg-e25880822edd, CTO ratify msg-889211d8fe09). At the
    2026-06-10 18:00:15Z host crash, land-RR-chunk-2''s 2 unique commits existed
    only on local disk (the audit''s #1 host risk); the 4-repo crash-audit found
    uncommitted/unpushed single-copy work in all 4 repos. par-plan proved the
    doctrine safe in the same arc: branch-push ≠ land — the gate stayed closed
    and origin/main stayed untouched until ratified. Merged from CTO lesson (b)
    + par-plan proposal B + ma-plan lesson 2 fix-path.'
see_also:
  - governance-layer-must-be-durable
  - evidence-persists-never-tmp-only
  - lead-seat-sweep-duty
  - worktree-branch-hygiene
---

# Push-early is unconditional: every land-*/wip branch pushes at creation

## Rule

Every branch carrying unique commits (`land-*`, `wip/*`, cohort
branches) is pushed to origin **at creation** — and re-pushed as
commits accrue. "Merge held" ≠ "push held": a held land-gate
constrains *ratification into main*, never *replication of the
branch*. Local-only commits are single-copy work and a standing host
risk.

## Why

The 2026-06-10 host crash made this empirical: unique commits that
existed only on local disk survived by filesystem luck, and the
crash-audit found the same exposure in all four repos
simultaneously. The same arc proved the practice safe — a pushed
candidate branch leaked nothing into main; the gate did its job at
merge time, not at replication time.

## When to apply

Immediately at branch creation, then at every commit boundary.
Applies to all seat classes in any workshop-lite-installed repo.

## When NOT to apply

Commits containing secrets (repair first), or when the remote itself
is mid-recovery.

## Enforcement tier (per 3-layer model — Kris ask msg-a2bd077282de)

**[A] audit-tier detector + [P] prompt-pack; [E] honestly not
achievable.** Substrate-enforcing the push would require auto-push
from a hook: violates hooks-never-block (HR-5; pushes hang offline),
risks wrong-remote/secrets without judgment, and WL doesn't own
consumer git hooks. Detector half: `[unpushed_branch]` advisory —
issue `2026-06-10-11`. Commit-side sibling: issue `2026-06-10-10`.
[P] half rides the Layer-C pack when the -07 render seam unblocks.

## See also

[[governance-layer-must-be-durable]] (the doctrine's governance-layer
sibling), [[evidence-persists-never-tmp-only]] (the run-evidence
sibling), [[lead-seat-sweep-duty]] (the unowned-delta sibling),
[[worktree-branch-hygiene]] (branch naming + lifecycle).
