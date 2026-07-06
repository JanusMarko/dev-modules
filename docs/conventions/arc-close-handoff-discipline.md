---
name: arc-close-handoff-discipline
tier: 1
applies_when:
  - an arc (cohort, benchmark phase, land-fork, investigation) just closed or
    parked at a clean seam
  - deliverables were sent to the operator or another seat during the arc
  - a fast arc is outrunning session-boundary handoff cadence
when_not_to_apply:
  - mid-arc (externalize-at-every-fork to chat covers in-flight continuity;
    the handoff is the seam artifact, not the fork artifact)
  - trivial arcs with no deliverables and no provenance a successor would need
origin:
  date: 2026-06-10
  context: 'Crash lessons-learned pass (Kris directive msg-15dae5951227, review-lead
    wsl-plan collation msg-e25880822edd, CTO ratify msg-889211d8fe09). Natural
    experiment, same seat, two arcs: benchmark Phase-1+2 HAD an arc-close
    handoff (2026-06-08-1415 with delivery msg_ids + artifact paths + per-round
    JSON inventory) → post-crash respawn recovered provenance losslessly. The
    2026-06-09/10 model-fit arc had NO handoff → its delivery record was simply
    gone when the operator asked "which HTML files did you send me?". par-plan
    independently hit the dual failure: newest handoff predated the live arc
    entirely, so SessionStart orientation pointed the revived seat at the WRONG
    context. Merged from benchmark-lead L2 + par-plan failure 3. The gap was
    discipline, not tooling — the Handoff entity already existed.'
see_also:
  - evidence-persists-never-tmp-only
  - governance-layer-must-be-durable
  - memory-scope-curate-not-accrete
---

# Handoff at every arc close — with delivery msg_ids + artifact inventory

## Rule

Write a Handoff entity (`/handoff`) at **every arc close or park**,
not only at session boundaries or under context pressure. The
handoff body must include: (1) delivery msg_ids for anything sent to
the operator or other seats, (2) an artifact inventory (paths +
what/where), (3) the "if the next occupant picks this up" section.
Fast arcs outrun session-boundary cadence; the arc close is the
correct trigger, the session boundary is the fallback.

## Why

The 2026-06-10 crash ran the controlled experiment: the arc WITH a
handoff recovered its provenance losslessly through a respawn; the
arc WITHOUT one lost its delivery record outright. A stale newest-handoff
also actively misleads — SessionStart orientation pointed a revived
seat at the wrong context because the live arc had never written one.

## When to apply

At every arc close/park seam. The handoff complements — never
substitutes for — chat externalization at every fork, which remains
the primary in-flight continuity mechanism.

## When NOT to apply

Mid-arc (use chat externalization), or arcs with genuinely nothing a
successor would need.

## Enforcement tier (per 3-layer model — Kris ask msg-a2bd077282de)

**Shape half [E]; occurrence half [A] + [P].** The trigger enum
already carries `arc_close` (D6.A), so conditional required-fields
(arc-shape trigger ⇒ non-empty delivery msg_ids + artifact
inventory) is genuinely substrate-enforceable the moment the entity
exists — issue `2026-06-10-13` half 1. The occurrence ("an arc
closed, write one") is a semantic event the substrate can't observe;
honest backstop is the `[activity_without_handoff]` staleness
advisory (-13 half 2) + [P] pack rendering. Sprint-close is already
[E]-by-construction via /end-sprint.

## See also

[[evidence-persists-never-tmp-only]],
[[governance-layer-must-be-durable]],
[[memory-scope-curate-not-accrete]] (handoffs supersede; fold via
`cli.py aging`).
