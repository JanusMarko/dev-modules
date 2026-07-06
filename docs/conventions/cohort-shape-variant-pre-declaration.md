---
name: cohort-shape-variant-pre-declaration
tier: 1
applies_when:
  - authoring-a-cohort-charter
  - reviewing-a-cohort-charter-shape-decision
  - dispatching-a-cohort-spawn-under-standing-pre-auth
  - builder-considering-mid-flight-cohort-shape-change
  - operator-or-CTO-ratifying-a-PR-READY-or-LAND-emit
when_not_to_apply:
  - charter is for a single-leg one-shot (not a multi-leg cohort with cert envelope)
  - shape is genuinely fixed by external constraint (e.g., independent-cert-required by HR #7 evals-first mandate; cross-substrate-consumer mandates a specific envelope)
origin:
  date: 2026-06-08
  context: 'WL.29 codex-host-substrate-emission LAND incident. Charter §3 specified FULL-3-leg; builder collapsed to builder-own-cert-only and LANDed without surfacing the variant pick. Empirical outcome was clean (22/22 cert + 1498/1498 full-suite + 0 regressions per LAND signal msg-8865b0363fb6), but @plan ratified retroactively as PASS-WITH-OBS-LOW per msg-226f572bc002 with binding process note: opacity to the CTO during mid-night-autonomy is unacceptable. @plan dispatch msg-cba8d37afd49 directed @wsl-plan to charter this doctrine amendment.'
see_also:
  - silence-policy-never-binary
  - kris-never-the-relay
  - governance-layer-must-be-durable
source_msg_ids:
  - msg-226f572bc002  # @plan WL.29 LAND ack + process note
  - msg-cba8d37afd49  # @plan dispatch for doctrine amendment
linked_issues:
  - 2026-06-08-06-charter-3-must-pre-declare-cohort-shape-variant-full-3-leg-vs-light-3-leg-vs-builder-own-cert-only-per-plan-msg-226f572bc002-process-note-from-wl-29-land
---

# Cohort §3 MUST pre-declare the cohort-shape variant; mid-flight variant shifts require pre-LAND ratify

## Rule

Every cohort charter §3 (Cohort shape) MUST explicitly pre-declare the variant chosen from the three canonical shapes:

1. **FULL-3-leg** — builder + independent tester + independent verifier; each leg owns its own cert envelope; firewall-strict separation.
2. **LIGHT-3-leg** — builder + collapsed tester/verifier seat (single peer reviewing cert + cross-checking); three logical roles in one or two seats.
3. **builder-own-cert-only** — builder writes the cert envelope themselves; no independent peer review pre-LAND. Permissible ONLY when (a) scope is mechanical-transform-class (HR #7 (b) — no judgment / no LLM / no classification / no importance-ranking), AND (b) explicitly justified in §3 with the mechanical-transform argument.

Each charter §3 picks ONE variant + supplies the **rationale** for the choice. The rationale must:

- Cite the relevant scope class (mechanical-transform vs. judgment-class vs. cross-substrate-consumer-dependency).
- Reference any HR (notably HR #7) that constrains the choice.
- Note if a precedent cohort's variant + outcome supports the pick (e.g., "cohort PW FULL-3-leg precedent shows tester-strengthen + verifier-replay catches axes builder own-cert misses on multi-deliverable scope").

**Mid-flight variant shifts are NOT silent.** If the builder discovers during chunk-0 forensic (or later) that a different variant is appropriate (e.g., the charter said FULL-3-leg but chunk-0 surfaces the scope is genuinely mechanical-transform; or the charter said builder-own-cert-only but chunk-0 surfaces a judgment-class transform), the builder MUST:

1. HALT chunk progression.
2. Surface the variant-shift proposal to @wsl-plan (or ratifier-of-record) via parley say with explicit "[VARIANT-SHIFT-PROPOSAL]" framing.
3. State: current §3 variant, proposed new variant, surfacing rationale (what chunk-0 showed), and impact on chunk plan + ETA.
4. WAIT for ratify before resuming.

Silent variant collapse (especially FULL-3-leg → builder-own-cert-only without ratify) is **forbidden** even when the cert + full-suite + regression-delta would have passed empirically. The discipline is about the ratify path, not about cert outcomes.

## Why

WL.29 codex-host-substrate-emission LAND incident (`d4ff3ca`, 2026-06-08T03:48Z). Charter §3 specified FULL-3-leg (builder + tester + verifier per cohort PW precedent). Builder collapsed all chunks to builder-own-cert-only and LANDed without surfacing the variant pick. Cert (22/22), full-suite (1498/1498), and regression-delta (0) were all clean. The empirical outcome validated the variant; the **discipline path was broken**.

@plan ratified retroactively as PASS-WITH-OBS-LOW per `msg-226f572bc002` with binding process note: "opacity to the CTO mid-night-autonomy isn't acceptable." Empirically-clean outcomes are not a substitute for transparent variant decisions because:

- The ratifier (CTO) cannot calibrate future cohort dispatches without seeing the variant-pick reasoning.
- Future cohorts of overly-similar shape may NOT have the same scope-fit (e.g., judgment-class transform hiding inside ostensibly-mechanical scope) and the empirical safeguard may not catch it.
- Standing pre-auth's "GO autonomous through LAND" permissiveness is on **direction**, not on **shape-shift**. Direction means "carry the existing plan through"; shape-shift is a new plan.

The opacity created by silent variant collapse is structurally equivalent to silent stalls under a too-broad silence policy (see [[silence-policy-never-binary]]) — both produce invisibility to the ratifier-of-record.

## When to apply

### When authoring a charter §3

- Pick ONE of the three canonical variants explicitly.
- Supply the rationale (~2-3 sentences). Cite scope class + HR constraints + relevant precedent.
- DO NOT default to FULL-3-leg as the "safe choice" if the scope is genuinely mechanical-transform — that creates a default-overshoot that builders will rationally want to collapse, which then triggers the silent-collapse failure mode this rule prevents.

### When ratifying a charter §3

- Verify the variant pick matches the scope class. If scope is mechanical-transform per HR #7 (b), builder-own-cert-only IS the correct default.
- If you (the ratifier) disagree with the author's pick, correct in §3 before chunks proceed.

### When dispatching a cohort spawn under standing pre-auth

- The spawn's "Cohort spawn (3-leg)" coverage applies to whatever variant the charter §3 declared. Standing pre-auth does NOT separately authorize variant changes mid-flight.

### When the builder considers a mid-flight variant change

- HALT chunk progression.
- Surface via "[VARIANT-SHIFT-PROPOSAL]" parley say (or in chunk-N forensic if pre-chunk-1).
- WAIT for ratify before resuming.

### When the ratifier reviews a PR-READY emit

- Check that the LAND chain matches the charter §3 variant. If the seat-chain shows builder-only commits when §3 said FULL-3-leg with independent tester/verifier, you have a silent-collapse incident. Treat as PASS-WITH-OBS-LOW at minimum (per WL.29 precedent); file the discipline-LOW so future cohorts have a tracking surface.

## When NOT to apply

- **Single-leg one-shot** (not a multi-leg cohort with cert envelope). E.g., a one-commit fix or a doctrine-document scribe. No tester/verifier ceremony to pre-declare.
- **External-constraint-forced shape**. E.g., HR #7 evals-first mandate forces independent eval-corpus author (a third seat-class beyond tester/verifier); the shape is determined by the constraint, not by §3 choice. Still declare in §3 + cite the constraint.
- **Charter is itself the doctrine amendment** (recursive case). E.g., this very convention doc was inline-@wsl-plan-scope, not a cohort.

## Examples

### Good charter §3 (mechanical-transform scope → builder-own-cert-only)

```markdown
## §3 — Cohort shape

**builder-own-cert-only.** Rationale: this charter's 4 deliverables are mechanical-transform-class (HR #7 (b) — same content, different shape; no LLM, no classification, no importance-ranking). Cohort PW FULL-3-leg precedent does not apply because PW had cross-substrate dependency where tester-strengthen caught axes builder missed; WL.X has no such dependency. Standing pre-auth Wave-1 covers PASS / PASS-WITH-OBS-LOW / PASS-WITH-AMEND-NON-BLOCKING. Builder's own-cert envelope MUST hit the full-suite regression gate + cohort-specific cert axes; no separate tester/verifier seats.
```

### Good charter §3 (multi-deliverable + cross-substrate consumer → FULL-3-leg)

```markdown
## §3 — Cohort shape

**FULL-3-leg.** Rationale: 4 deliverables touch cross-substrate consumer (par-p0-codex-parity wave-2 cherry-pick depends on verb stability); cohort PW FULL-3-leg precedent shows tester-strengthen + verifier-replay catches axes builder own-cert misses (5 axes amend on PW chunk-3 strengthen). LIGHT-wedge-risk on multi-deliverable scope. Branches: ...-{builder,tester,verifier}. Per-leg worktree.
```

### Anti-pattern: §3 picks FULL-3-leg as the "safe default" when scope is genuinely mechanical

```markdown
## §3 — Cohort shape

**FULL-3-leg.** Rationale: it's safer than LIGHT.
```

This default-overshoot creates the silent-collapse pressure: builder rationally sees FULL is overkill for mechanical-transform scope, collapses to own-cert at LAND, and the variant decision goes invisible to the ratifier. **Fix**: either (a) keep FULL with a specific reason (cross-substrate-consumer, judgment-class transform, multi-deliverable wedge-risk) OR (b) pick builder-own-cert-only with the mechanical-transform argument. Don't pick FULL "because it's safer".

### Anti-pattern: builder silently collapses mid-flight

```
Charter §3: FULL-3-leg.
Builder chunk-0 forensic: ... reveals scope is mechanical-transform.
Builder chunk-1 through chunk-5: builder-own-cert-only LAND.
Ratifier discovers post-LAND.
```

This is the WL.29 incident shape. **Fix**: builder HALTs at chunk-0 with [VARIANT-SHIFT-PROPOSAL] for @wsl-plan ratify before chunks proceed.

## See also

- [[silence-policy-never-binary]] — silent variant collapse is the same failure mode as silent stalls under a too-broad silence policy: both create invisibility to the ratifier-of-record. Sibling rules.
- [[kris-never-the-relay]] — when the variant decision IS opaque, the operator becomes the only failure detector. This convention prevents that path.
- [[governance-layer-must-be-durable]] — the §3 variant + rationale lives in the committed charter doc, durable across seat replacements. The pre-LAND ratify happens via parley say + recorded msg-id.

## Implementation notes

This convention applies to all cohort charters authored in workshop-lite-managed repos. The `docs/.templates/charter.md` (or equivalent charter template, if one exists) should embed the §3 variant-pre-declaration shape with the three canonical variants enumerated. Future cohort charters can copy the "Good charter §3" examples above as starting points.

If a charter §3 is silent or ambiguous on the variant, the ratifier MUST fix in-place before chunks proceed. A charter without a clear §3 variant is not ratified.
