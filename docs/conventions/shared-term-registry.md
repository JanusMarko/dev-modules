# Workshop-Lite — Shared-Term Registry

**Steward:** wl-pm2 coordination; wl-pm-cc C3b coverage; wl-l2 acceptance boundary   ·   **Created:** 2026-07-05
**Standard:** documentation-expert:docs/kits/general/shared-term-registry-standard.md @c79e6f2
**Tier:** local:workshop-lite
**Shared-tier contract:** dev-mgmt-session:docs/conventions/shared-term-registry.md @4373571ceb329fb7152693d674bf3bc60d577a65 — shared > local, always; entries promoted there are tombstone-pointed below, never restated.

## Registered terms

| term | sense (one line) | scope | status | canonical-def | never-write | decided |
|---|---|---|---|---|---|---|
| cohort | A bounded Workshop-Lite work unit with declared scope, participating seats, evidence expectations, and close/land disposition. | local:workshop-lite | active | docs/conventions/cohort-shape-variant-pre-declaration.md | Do not use "cohort" for an unscoped chat, loose topic, sprint, or org-wide build-wave. | 2026-07-05; parley:v3-org-core:v3-21697 and v3-21714 |
| charter | The dispatch artifact that pins implementation shape, role/SoD expectations, certification axes, and acceptance evidence before a build or cert leg begins. | local:workshop-lite | active | docs/design/wl-2-0/charters/ | Do not use "charter" for a post-hoc status report, generic plan, or implementation summary. | 2026-07-05; parley:v3-org-core:v3-21697 and v3-21714 |
| design-to-build registry | The WL2.3 living status registry under `.workshop-lite/registry/`, used to track design/spec/build-plan/work/gate records and transitions. | local:workshop-lite | active | docs/design/wl-2-3/2026-07-03-wl2.3-product-spec.md | Bare "registry"; use qualified forms because shared-tier "registry" is banned-bare. | 2026-07-05; parley:v3-org-core:v3-21714 |
| kind | The WL2.3 tracked-item discriminator used by design/spec/build-plan/work/capability/gate/decision/fanout/audit/Track-S-binding records. | local:workshop-lite | active | docs/design/wl-2-3/2026-07-03-wl2.3-build-plan.md | Do not use "kind" as a casual synonym for "type" in record/gate contexts; name the concrete kind. | 2026-07-05; parley:v3-org-core:v3-21697 and v3-21714 |
| side-state | A WL2.3 retained lifecycle/disposition state or transition qualifier, resolved only when its required qualifier is present. | local:workshop-lite | active | docs/design/wl-2-3/2026-07-03-wl2.3-build-plan.md | Do not call side-state a gate result, release state, or conformance claim; do not treat an unqualified side-state as resolved. | 2026-07-05; parley:v3-org-core:v3-21697 and v3-21714 |
| conformance | A WL product-local evidence record or check that cites the declared standard, contract, compatibility row, and evidence refs. | local:workshop-lite | active | docs/design/wl-2-3/2026-07-03-wl2.3-build-plan.md | Do not claim measured or live-runtime conformance from a product-local record unless release gates and measurement evidence have cleared. | 2026-07-05; parley:v3-org-core:v3-21697 and v3-21714 |
| handoff | The settled post-state document for the next worker at an arc close, session end, or compact boundary. | local:workshop-lite | active | .codex/skills/handoff/SKILL.md | Do not use handoff for self-resumption state; that is a resume-ledger. | 2026-07-05; parley:v3-org-core:v3-21714 |
| resume-ledger | The in-flight state and next actions for the next incarnation of the same worker after a restart. | local:workshop-lite | active | .codex/skills/write-resume-ledger/SKILL.md | Do not conflate resume-ledger with handoff; they cross different worker/session boundaries. | 2026-07-05; parley:v3-org-core:v3-21714 |
| sprint | A Workshop-Lite sprint folder lifecycle under `docs/sprints/`, with free-form sprint IDs and plan/tasks/retro artifacts. | local:workshop-lite | active | CLAUDE.md#sprint-convention | Do not use sprint for a cohort or build-wave; those have different dispatch and certification lifecycles. | 2026-07-05; parley:v3-org-core:v3-21714 |

## Promoted terms (tombstones)

| term | promoted to shared | date |
|---|---|---|
| build-wave N / wave | dev-mgmt-session:docs/conventions/shared-term-registry.md @4373571ceb329fb7152693d674bf3bc60d577a65 | 2026-07-05 |
| owner | dev-mgmt-session:docs/conventions/shared-term-registry.md @4373571ceb329fb7152693d674bf3bc60d577a65 | 2026-07-05 |
| registry | dev-mgmt-session:docs/conventions/shared-term-registry.md @4373571ceb329fb7152693d674bf3bc60d577a65 | 2026-07-05 |
| gate | dev-mgmt-session:docs/conventions/shared-term-registry.md @4373571ceb329fb7152693d674bf3bc60d577a65 | 2026-07-05 |

## Local gate kinds

The shared `gate` entry owns the cross-system sense and bans bare `gate`;
Workshop-Lite keeps its qualified kind list here without restating the shared
definition. Workshop-Lite currently has cross-session gates, phase-exit gates,
and cert gates; never write bare `gate` when the kind is ambiguous across those
WL gate kinds. The primary WL canonical-def paths are
`docs/design/LIGHTWEIGHT-DEV-MGMT-SYSTEM.md` and
`docs/design/wl-2-3/2026-07-03-wl2.3-build-plan.md`.

| gate kind | WL-local sense | canonical-def | never-write |
|---|---|---|---|
| cross-session gate | A durable `docs/gates/` blocker whose `status: open` and `what_you_cannot_do` list constrain non-trivial cross-session work until cleared or expired. | docs/design/LIGHTWEIGHT-DEV-MGMT-SYSTEM.md | Do not use for WL2.3 phase-exit predicates or build/cert review bars. |
| phase-exit gate | A WL2.3 no-silent-drop registry predicate that blocks advancement when tracked items lack required state, ownership, evidence, dependency, fan-out, or side-state qualifiers. | docs/design/wl-2-3/2026-07-03-wl2.3-build-plan.md | Do not use for `docs/gates/` runtime blockers or cert panel acceptance. |
| cert gate | A build/certification acceptance bar that closes a cohort, build leg, or verifier leg only after its declared cert axes pass. | docs/design/wl-2-0/charters/ | Do not use for cross-session blockers or WL2.3 no-silent-drop phase-exit checks. |

## Coverage notes

This same-day instance seeds collision-prone Workshop-Lite terms used across
WL2.3 design, build-plan, registry, gate, and ledger surfaces. Candidate terms
flagged for future gates include scenario, formation, pattern, recipe, engine,
role-set, workflow, and BC-series cohort identifiers. WL2.3 W6 role vocabulary
is a shared-tier promotion candidate because it crosses system boundaries. These
terms remain unregistered until a document or gate needs an exact C3b pin for
their senses.

## Gate-record pin format

From the next C3b/naming gate onward, records cite:

`checked against: dev-mgmt-session/docs/conventions/shared-term-registry.md@<shared-SHA> + workshop-lite/docs/conventions/shared-term-registry.md@<local-SHA> -> result (clean | collisions listed)`

MUST-FIX classes: local redefinition of a shared term; a second sense of any
registered term; an unregistered cross-document load-bearing term at a ratify
gate; or a gate record claiming the naming check without this pin.

## History rule

Forward-only: pre-registry documents are not rewritten; a header note in the
legacy doc points here. New and revised documents conform directly.
