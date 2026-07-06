---
name: runbooks-consult-before-reinventing
tier: 1
applies_when:
  - about-to-author-a-status-report-respawn-orientation-wind-down-or-other-operational-procedure
  - dispatching-a-new-worker-seat-or-cohort-charter
  - configuring-a-sidecar-rolling-restart-or-cross-session-sweep
  - building-a-LOAD-LAND-BROADCAST-platform-mitigation
when_not_to_apply:
  - no runbook exists for the case (then file a substrate-fix candidate for the gap; do not memorize the gap)
  - a new operational procedure is being designed from scratch with substrate-approval
origin:
  date: 2026-05-31
  context: 'Operator-direct correction ~16:10Z: "these runbooks do not matter if you do not use them, how do we fix that?" Several load-bearing operational procedures + prompt templates live as runbooks at `parley/docs/runbooks/` (10 top-level operator runbooks + 8 prompt templates + 5 scripts), but agents were reinventing from scratch instead of reaching for them. The fix is 3-layer: CLAUDE.md ## Runbooks section (ambient discovery; auto-loaded); a meta-pointer memory entry (does not store runbook content); selective skill promotion (auto-invoke on intent match; `/epic` first; more as patterns emerge).'
see_also:
  - memory-audit-and-promote-pattern
  - governance-layer-must-be-durable
source_memory: feedback_runbooks_consult_before_reinventing.md (dev-mgmt:plan; promoted cohort U 2026-06-05)
---

# Consult the runbook before reinventing the procedure

## Rule

Before authoring any of the following from scratch, **consult the
relevant `## Runbooks` section first** (in CLAUDE.md, or directly
at `<substrate>/docs/runbooks/`):

- Status report over a time window
- Resurrected / respawned seat orientation
- End-of-day wind-down packet
- Dual-independent adversarial cross-check spawn charter
- New-worker charter template
- Cross-session compact verify
- Operator-facing planner cadence digest
- Boundary-commit git discipline
- Sidecar rolling restart
- Cross-session substrate dashboard
- LAND + LOAD + BROADCAST platform-mitigation doctrine

Runbooks carry load-bearing phrasing notes that pure-generation will
miss (e.g., epic-status-report's "non-technical terms" + "worried
about / proud of" pair). Memory is not the answer — substrate
enforcement (runbook discovery via CLAUDE.md `## Runbooks` section)
is.

If the runbook is missing for your case, that's a substrate-fix
candidate — file an issue with the gap description, don't memorize
the gap or work around it.

## Why

Operator-direct correction 2026-05-31: "these runbooks do not matter
if you do not use them, how do we fix that?" Several load-bearing
operational procedures had been built as runbooks, but agents were
reinventing them from scratch because they didn't know to reach for
the runbook. The fix is structural:

1. **CLAUDE.md ## Runbooks** section provides ambient discovery
   (auto-loaded into every session's context). The convention here
   is that consumer-repo CLAUDE.md files reference the runbooks
   table in the appropriate substrate.
2. **This convention doc** is the meta-pointer (says "go to the
   runbook"; does not replicate runbook content). Memory is not
   the answer; substrate is.
3. **Selective skill promotion** (auto-invoke on intent match) for
   the highest-frequency runbooks — start with one or two (e.g.
   `/epic` for the status-report pattern), expand as patterns emerge.

Operator-binding rule (2026-05-31 ~15:30Z): "Memory is not the
answer!!!!! We made session hooks even to handle that." Substrate
enforcement > memory band-aids. This convention IS the meta-pointer
exception (it points to substrate; it does not replicate runbook
content).

## When to apply

- About to author a status report, respawn orientation, wind-down
  packet, adversarial cross-check spawn charter, sidecar rolling
  restart, or cross-session dashboard view? STOP. Check the runbook
  index first.
- Dispatching a new worker / cohort charter? STOP. The charter
  template runbook captures the canonical shape.
- Configuring LAND + LOAD + BROADCAST for a platform mitigation?
  STOP. The doctrine runbook covers the three-step.

## When NOT to apply

- No runbook exists for the case. File a substrate-fix Issue with
  the gap description (`scope: design:*` or `scope: repo:*`
  depending on where the runbook should live). Do NOT memorize the
  gap or work around it — that creates a per-seat shadow runbook.
- New operational procedure being designed from scratch under
  substrate approval — author the runbook as part of the
  substrate-fix, then this convention applies on second use.

## How to discover the right runbook

1. **CLAUDE.md ## Runbooks** section — every consumer-repo
   CLAUDE.md should have one. Highest-frequency runbooks listed
   with one-line summaries + paths.
2. **`<substrate>/docs/runbooks/INDEX.md`** — full per-substrate
   inventory. parley/docs/runbooks/ is the canonical home for
   most cross-session runbooks; workshop-lite/docs/runbooks/
   captures workshop-lite-specific ones (sprint lifecycle, entity
   templates).
3. **Skill registry** — runbooks that have been skill-promoted
   appear as user-invocable verbs (e.g. `/epic` for the
   status-report pattern). Auto-invoke on intent match.

## Anti-pattern

### Reinventing the status-report on every cycle

```
Coordinator: "Time for end-of-day wind-down. Let me draft a
template…"

Produces a passable status report missing the load-bearing
"worried about / proud of" framing pair, and missing the
non-technical-terms discipline. Operator: "this isn't the format
I asked for."

Fix: consult `parley/docs/runbooks/prompts/end-of-day-wind-down.md`
first. The template has the framing baked in.
```

### Memorizing the runbook content into a memory file

```
Agent: "I'll save the end-of-day-wind-down template into my memory
so I don't have to look it up next time."

Substrate enforcement principle violated. The runbook is the
canonical source; per-seat memory copy will drift. When the
runbook is updated, the memory copy lies.

Fix: keep the meta-pointer (this convention) in memory only;
always go to the runbook for content.
```

## See also

- [[memory-audit-and-promote-pattern]] — the broader pattern of
  moving cross-seat-applicable rules out of per-seat memory into
  substrate; this convention is the runbook-specific application
  of that principle.
- [[governance-layer-must-be-durable]] — runbooks ARE one of the
  three accepted reboot-durable mechanisms (committed doc); a
  runbook update is governance-durable by construction.
