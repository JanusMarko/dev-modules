---
name: silence-policy-never-binary
tier: 1
applies_when:
  - coordinator-class-seat-about-to-issue-a-silence-directive
  - retracting-or-adjusting-a-keepalive-or-cadence-convention
  - reviewing-an-existing-silence-policy-for-failure-modes
when_not_to_apply:
  - the directive is genuinely two-mode by construction (e.g. "silent only when charter-CLOSED AND auto-prune handles") — but verify the construction holds
  - non-coordinator-class seats (they consume silence directives, they don't issue them)
origin:
  date: 2026-05-31
  context: 'Operator-direct correction ~20:30Z: "If you were a human, I would fire you right now." Triggered by 5+ stalled cohorts (verifier 6hr stale with unratified HOLD-PENDING-RATIFY, tester rejoin didn''t restart cert authoring, another tester held stationary, two builders stuck) hidden behind a silence directive a coordinator issued at 18:55Z that retracted the charter-closed-keepalive-cycle convention. The directive conflated IDLE-BY-DESIGN (correct silence) with BLOCKED / STALLED / AWAITING-CLARIFICATION (invisibility) under one "silent unless material" rule. Net result: ~6 hours of zero LAND throughput while the system appeared healthy.'
see_also:
  - kris-never-the-relay
  - governance-layer-must-be-durable
source_memory: feedback_silence_policy_never_binary.md (dev-mgmt:plan; promoted cohort U 2026-06-05)
---

# Silence directives MUST distinguish IDLE-BY-DESIGN from BLOCKED, and must enumerate stall-detection

## Rule

Any silence directive ("silent unless material", "no keepalive",
"hold quiet until I dispatch") MUST distinguish two cases:

- **IDLE-BY-DESIGN** (charter-CLOSED, post-LAND, awaiting auto-prune
  or natural reseat): silence is correct; auto-prune / monitor
  handles.
- **BLOCKED / STALLED / AWAITING-CLARIFICATION**: silence is
  **INVISIBILITY**. Stalls produce no signal under "silent unless
  material", so the SM doesn't see them, the CTO cron doesn't see
  them, and the operator becomes the only failure detector.

Before issuing any silence directive, write down the failure modes
**explicitly**:

1. What does a stalled seat look like under this policy? (silent)
2. How will the SM / CTO detect a stalled seat? (must be explicit)
3. How will I detect a SM that failed to detect a stall? (must be explicit)

If both answers to (2) and (3) are "they'll surface when they have
material" — you've built invisibility.

## Why

Operator-direct correction 2026-05-31 ~20:30Z. A coordinator issued
a silence directive at 18:55Z that retracted a per-wake keepalive
convention. Cohorts that became blocked or stalled in the next 6
hours had no signal to surface — they were silent, by policy. The
CTO interrogation cron only checked the SM heartbeat; a "healthy"
SM with all cohorts silently stalled showed green-status while the
system burned. ~6 hours of zero LAND throughput, ~250-record-per-kick
storms from a separate bug, and the operator had to manually
re-discover what was going on. Operator's verdict: "If you were a
human, I would fire you right now."

The lesson is structural: silence is not a single mode. The
informative-silence (IDLE-by-design) and actionable-signal (blocker
escalates) must both be enumerated. Calibrate, don't pendulum —
when a prior policy was too noisy (keepalive flood), the answer is
NOT all-silence; it's *informative silence + actionable signal*.

## When to apply

- Before issuing any silence directive — write down the four
  failure-mode questions above and answer them.
- Build stall-detection in parallel to issuing the silence policy.
  The detection cron must include:
  - LAND-rate tripwire (e.g., `git log origin/main --since="2 hours ago"`
    count == 0 with active cohorts = stall)
  - Per-cohort branch-advance check (no commits to expected
    work-branch for >Nhr while seat is alive = silent stall)
  - Not just SM heartbeat — SM can be alive-and-busy while cohorts
    are dead.
- Two-mode every silence convention explicitly:
  - IDLE-BY-DESIGN (charter-CLOSED, awaiting auto-prune): silent.
  - BLOCKED / STALLED / AWAITING-CLARIFICATION: MUST signal at least
    every Nmin (default 60min) with `[BLOCKED] reason` /
    `[STALLED-Nh] last-action / waiting-on`. **Stalls are material.**

## When NOT to apply

- The directive is genuinely two-mode by construction (e.g. "silent
  only when charter-CLOSED AND auto-prune handles") — verify the
  construction holds: is there a substrate path that auto-detects
  blocked seats? If yes, the policy is safe. If no, blockers will
  hide.
- Non-coordinator-class seats issuing personal posture choices (not
  cross-seat directives) — but they should still distinguish
  idle-by-design from blocked in their own surfacing.

## Anti-pattern

### Conflating IDLE with BLOCKED under one silence rule

```
Coordinator policy: "Charter-closed seats stay silent unless they
have material output."

Effect: a charter-CLOSED seat with auto-prune coverage is
correctly quiet (IDLE-by-design). A blocked seat awaiting a
peer-decision is ALSO quiet (no material output yet) — and now
invisible. SM doesn't see them. Operator becomes the only failure
detector.

Fix: split. Charter-CLOSED → silent (auto-prune handles).
Charter-OPEN but blocked → MUST signal every Nmin with [BLOCKED].
```

### Pendulum calibration after a too-noisy policy

```
Prior policy: per-wake keepalive ping (too noisy).
Naive retraction: "no keepalive at all".

Better: per-wake keepalive ONLY when CHARTER-OPEN AND
NOT-blocked AND nothing-substantive-to-say (the informative
silence-as-positive-assertion case); blocked seats override the
silence with [BLOCKED] every Nmin.
```

## See also

- [[kris-never-the-relay]] — a buried blocker that should escalate
  to the coordinator (not the operator) is one of the failure modes
  silence-policy-never-binary prevents. Sibling rules.
- [[governance-layer-must-be-durable]] — when a silence directive
  is issued, the durability rule applies: the policy itself must
  be reboot-durable (memory file / Kind.DECISION / committed doc),
  not only in-context.
