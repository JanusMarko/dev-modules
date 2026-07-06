---
name: kris-never-the-relay
tier: 1
applies_when:
  - any-coordinator-class-seat-CTO-SM-or-equivalent
  - a-member-is-blocked-on-a-decision-the-coordinator-owns
  - assessing-whether-to-escalate-to-the-operator
when_not_to_apply:
  - the coordinator is genuinely dark past the agreed staleness threshold (then escalation IS legitimate, and is framed as "coordinator unresponsive" not "please relay")
  - non-coordinator-class seats (this rule is about coordinator responsibility for owning their members' unblock path)
  - the operator IS the right decision authority (a genuine GATE / fork moment that the coordinator's autonomy does not cover)
origin:
  date: 2026-05-26
  context: 'Operator-direct correction. MAI-PM was blocked on a verifier-xrequest resolve (TO-SM authority, genuinely the CTO''s job). The CTO had deferred the resolve for hours then gone dark. MAI-PM''s only remaining path to the CTO was the commissar''s whereami digest to the operator''s Telegram, so MAI-PM asked the operator to nudge the CTO in their CC pane. Operator''s response: "Why was mai-pm waiting on you or me? It is your job to make those decisions." Correct — the operator became the relay to make the coordinator do its own job, which is backwards.'
see_also:
  - silence-policy-never-binary
  - governance-layer-must-be-durable
source_memory: feedback_kris_never_the_relay.md (dev-mgmt:plan; promoted cohort U 2026-06-05)
---

# The operator must never be the relay to wake a coordinator to do its own job

## Rule

When a member is blocked on a decision or operation that is the
coordinator's job (CTO / SM / equivalent), the escalation must reach
the coordinator **directly**. Routing it through the operator (via
the commissar's whereami digest, a Telegram nudge, or "please ping
@plan in their CC pane") is a **failure mode**, not a feature.

A coordinator that owns a decision is responsible for unblocking its
members **without the operator in the loop**. Operator-escalation is
last-resort ONLY (the coordinator is genuinely dark past threshold),
and when it fires it is framed as "coordinator is unresponsive" — a
real emergency — never as "please relay this routine decision."

## Why

Operator-direct correction 2026-05-26: a peer waiting on a coordinator
decision routed its escalation through the operator's Telegram digest
because the coordinator had gone dark mid-decide. The operator's
response: "Why was that peer waiting on you or me? It is your job to
make those decisions." Correct — the operator became the relay to
make the coordinator do its own job, which is backwards.

Under full-autonomy delegation, the coordinator seat owns its
decisions autonomously. A member-blocked-on-coordinator-action is the
coordinator's responsibility to unblock without the operator in the
loop. The operator is the observer, not a routing hop.

## When to apply

- A peer surfaces a blocker that names a coordinator-class action
  (ratify, dispatch, scope-decision, member-management). The
  coordinator owns it; act directly.
- When you (the coordinator) return from any dark window — first-scan
  for members blocked on a coordinator-action and clear that backlog
  before anything else. That backlog is your highest-priority unblock.
- Substrate prevention: resolve / close substrate lifecycles AT
  decision-time (see [[resolve-xrequest-at-ratify-time]] in
  cross-tier references) so the blocking-wait never forms.

## When NOT to apply

- The coordinator is genuinely dark past the agreed staleness
  threshold (typically tens of minutes for active arcs, hours for
  overnight windows). Then operator-escalation IS legitimate; frame
  it as **"coordinator is unresponsive"**, never **"please relay this
  routine decision"**.
- Non-coordinator-class seats. A worker blocked on a peer-decision
  routes laterally, not up.
- The operator IS the right decision authority — a genuine GATE or
  fork moment that the coordinator's autonomy does not cover (master
  design forks, cross-substrate blast radius, operator-direct
  delegated ratify). These are the rare paths where the operator is
  the destination, not a relay.

## Examples

### Good — direct escalation between peers

```
Member A is blocked on a verifier-xrequest resolve that the
CTO @plan owns. The CTO is mid-decide (visible chat activity in
the last few minutes). Member A force_wakes @plan directly with
the xrequest id + a 1-line "blocked on this since N min".
@plan resolves; Member A unblocks.
```

### Good — operator-escalation framed as coordinator-unresponsive

```
Member A has been blocked on @plan ratify for 90 minutes. @plan
has no chat activity for the same window; their pane is silent.
Member A escalates to the operator with the framing: "@plan has
been unresponsive for 90min on the ratify ask msg-XXXX; standard
escalation thresholds exceeded." This is a real emergency, not
a routine relay.
```

### Bad — operator as routine relay

```
Member A is blocked on a routine ratify the CTO owns. CTO is
busy with other work in the same session. Member A escalates to
the operator: "please ping @plan to unblock me." The operator
becomes the relay to make the coordinator do its own job —
inverted responsibility.
```

## See also

- [[silence-policy-never-binary]] — silence directives must
  distinguish IDLE from BLOCKED + enumerate stall-detection;
  prevents the buried-blocker pattern that drives operator-relay
  attempts.
- [[governance-layer-must-be-durable]] — operator directives /
  design inputs must be reboot-durable the moment received, so the
  coordinator's decision context survives reseat / compact / dark
  windows.
