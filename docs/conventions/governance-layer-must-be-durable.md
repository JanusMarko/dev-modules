---
name: governance-layer-must-be-durable
tier: 1
applies_when:
  - operator-directive-or-design-input-just-received
  - parley-backlog-defect-just-surfaced
  - load-bearing-mandate-just-declared-and-not-yet-committed-anywhere-durable
  - charter-delta-just-delivered-to-a-seat (widening / narrowing / re-scoping)
when_not_to_apply:
  - transient operational context (in-flight task state, current sprint stage) — that belongs in plan / task / handoff entities, not the governance layer
  - the directive is already durable in one of the three accepted mechanisms (memory file / Kind.DECISION / committed doc)
origin:
  date: 2026-05-16
  context: 'Commissar finding (operator-raised, evidence-confirmed): a standing-state integrity gap. The substantive engineering decisions ARE durable (Kind.DECISION → planner-state.md), but the *governance/directive layer* — relayed operator directives, automated-commissar v2.0 design inputs, parley backlog defects — existed ONLY in the in-context task ledger + hand-prepared /tmp resume-ledgers at deliberate seams. That layer survived the last compact ONLY because the coordinator hand-prepared a resume-ledger at a deliberate seam. An UNPLANNED loss (CC-crash, delivery-gap, harness summarization at a non-seam) loses it — and /tmp is not reboot-durable. The governance layer is the least-durably-recorded yet highest-value layer (design inputs are the basis for whole subsystems; operator directives are load-bearing mandate).'
see_also:
  - kris-never-the-relay
  - silence-policy-never-binary
source_memory: feedback_governance_layer_must_be_durable.md (dev-mgmt:plan; promoted cohort U 2026-06-05)
---

# Operator directives + design inputs + backlog defects MUST be reboot-durable the moment received

## Rule

Any **load-bearing directive, design input, or backlog defect** must
land in a reboot-durable mechanism the moment it is received — not
deferred to the next compact seam, not held in the in-context task
ledger, not staged only in a /tmp resume-ledger.

The three accepted reboot-durable mechanisms:

1. **Memory file** at `~/.claude/projects/<slug>/memory/<name>.md`
   (loaded every session by CC; survives crashes; canonical for
   persistent rules).
2. **`Kind.DECISION` record** via the parley substrate (→
   planner-state.md; canonical for substantive ratified choices).
3. **Committed doc** in a git repo (decisions / handoffs / dispatches
   / conventions / runbooks; canonical for design + governance
   artifacts).

A directive that lives ONLY in the in-context task ledger or /tmp
fails this bar. The task ledger is reset on reseat / compact /
crash; /tmp is per-machine ephemeral and not snapshot-protected.

## Why

Operator-raised finding 2026-05-16: a commissar audit surfaced a
standing-state integrity gap. The substantive engineering decisions
WERE durable (Kind.DECISION → planner-state.md), but the
*governance / directive layer* — relayed operator directives,
v2.0 design inputs, parley backlog defects — existed ONLY in the
in-context task ledger + hand-prepared /tmp resume-ledgers at
deliberate seams. That layer survived the last compact ONLY
because the coordinator hand-prepared a resume-ledger at a
deliberate seam.

An UNPLANNED loss (a CC-crash, a delivery-gap, harness
summarization at a non-seam) loses it. And /tmp is not
reboot-durable. The governance layer is the least-durably-recorded
yet highest-value layer — design inputs are the basis for whole
subsystems; operator directives are load-bearing mandate.

The rule is: durable-at-receipt, not durable-at-next-seam.

Crash-confirmed 2026-06-10 (lessons-learned pass, Kris directive
msg-15dae5951227): a pm charter-widening (design/decision-partnership
lane) had a failed file-write pre-crash and existed only in the dead
seat's context — it is now lost pending re-issuance. **Charter deltas
are durable-on-disk at delivery time or they don't exist.** The
deliverer confirms the write landed; the receiver verifies before
acting on the new scope.

## When to apply

- **Operator surfaces a binding directive**: immediately write a
  memory file (for cross-session-applicable rules) AND/OR a
  committed Decision entity (for the active arc). Reference the
  message id (parley msg-XXXX) in the durable record so provenance
  survives.
- **Coordinator receives a v2.0 design input / backlog defect**:
  immediately file an Issue entity in the appropriate substrate
  (workshop-lite docs/issues/ or parley docs/issues/) with the
  source ref. Don't wait for the next sprint.
- **Cross-session directive that should bind multiple seats**:
  promote to a substrate-portable convention (see
  [[memory-audit-and-promote-pattern]]) so it discovers via
  substrate install, not via per-seat memory osmosis.

## When NOT to apply

- **Transient operational context** (in-flight task state, current
  sprint stage, "I'm working on chunk-3 right now") — that's
  task / handoff / plan content, not governance. Don't promote
  it; it ages out naturally.
- The directive is already durable in one of the three accepted
  mechanisms — don't duplicate.
- The directive is genuinely scoped to ONE session-internal moment
  (e.g. "for this dispatch only, skip cohort-X") — note in the
  dispatch / charter entity, not as a standing rule.

## How to apply — practical recipe

For an operator directive received via parley chat:

1. **Surface receipt** via parley say so the durability action is
   observable.
2. **Pick the right durability mechanism** based on scope:
   - Cross-session standing rule → memory file under your seat's
     slug.
   - Cross-seat load-bearing mandate → committed convention doc
     (per [[memory-audit-and-promote-pattern]]).
   - Active-arc design input → committed Decision entity in the
     active substrate.
   - Substrate gap / defect → committed Issue entity.
3. **Write the durable record** with provenance (`linked_msg_ids:
   [msg-XXXX]`) within the same turn / before the next tool call
   that could fail.
4. **Acknowledge in chat** with the path to the durable record.

For a v2.0 design input surfaced in a peer-message: same flow,
but the durable record is typically an Issue or a Decision in the
relevant substrate's docs/.

## Anti-patterns

### Deferring to the next seam

```
Operator: "Standing rule: prefer X over Y."
Coordinator: "Noted, I'll fold into the next handoff."

Reboot before the next handoff → rule lost. The handoff was
supposed to be the durability mechanism; instead it became a
single point of failure.
```

### /tmp resume-ledger as durability

```
Coordinator drafts a /tmp/resume-ledger.md at every clean seam
containing all standing directives.

The file is per-machine ephemeral; a host reboot or /tmp cleanup
loses it. /tmp resume-ledgers are *convenience* for restoring
context post-compact, NOT a durability guarantee.
```

### Task ledger as governance store

```
Coordinator tracks operator directives in the in-context task
ledger (TaskCreate entries).

Tasks are scoped to the current conversation; they reset on
reseat / compact / crash. Tasks track work, not governance.
```

## See also

- [[kris-never-the-relay]] — a coordinator that loses a directive
  in an unplanned reseat may default-route the resulting blocker
  through the operator instead of owning it; sibling failure mode.
- [[silence-policy-never-binary]] — silence directives are
  particularly important to durabilize; an undurabilized silence
  policy creates the conditions for the buried-blocker pattern.
- [[memory-audit-and-promote-pattern]] — the substrate-portable
  promotion mechanism for rules that should bind across seats.
