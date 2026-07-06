---
name: scope-routing
description: The 2-axis SCOPE × LAYER discipline for routing backlog items, sprint scopes, and ownership decisions. Use when filing an issue, dispatching a sprint, picking an artifact location, or deciding who owns a piece of work. Doctrine-level reference, not an action-invoked verb.
---

# scope-routing — the 2-axis SCOPE × LAYER discipline

**Documentation skill, not an action-invoked verb.** This is the canonical reference for the SCOPE × LAYER classification scrum-masters apply BEFORE filing issues, dispatching sprints, or choosing artifact locations.

Per @user msg-de2a56fae543 + msg-9453e119b8e9 (Kris-direction routed through @user dispatches): every piece of backlog work has two orthogonal coordinates. Classify both before acting.

## The two axes

### Axis 1: SCOPE — *WHERE does the work physically live?*

| SCOPE value | Repo / substrate | Ownership |
|---|---|---|
| **parley-substrate** | `parley/parley/` code; parley sidecar; parley CLI | @plan(dev-mgmt) / parley team |
| **WL-substrate** | workshop-lite: `.claude/skills/`, `.claude/scripts/dev-mgmt/`, `.claude/hooks/`, `docs/design/` | @wl-plan / WL maintainers |
| **repo-where-found** | per-consumer repo (maxai, ccweb, dev-modules, parley-as-consumer, etc.) — any repo importing WL as a substrate | the consumer's owner / team |

The SCOPE value is determined by **where the fix lives**, not where the symptom appears. A failure observed in maxai but caused by a WL substrate bug is `WL-substrate` SCOPE.

### Axis 2: LAYER — *WHAT KIND of artifact?*

| LAYER value | Artifact shape | Where it ends up |
|---|---|---|
| **user-preference** | User-scoped TOML knob (per-human, global across that human's projects) | `.claude/preferences.toml` (or equivalent in `parley-substrate` / `repo-where-found` cases) |
| **substrate-generic** | Substrate-level mechanism / helper code / convention doc reusable across all consumer projects. Pure structural; parley-agnostic at base (CLAUDE.md Hard Rule 1) | `.claude/scripts/dev-mgmt/*.py` lib; `docs/design/*.md` doctrine; `.claude/skills/*/SKILL.md` discipline |
| **substrate-project-coupled** | Substrate config / hook / carve-out that's per-consumer-project. Substrate provides the mechanism; consumer-project configures it | `.claude/workshop-lite-config.toml` per-project section; `.claude/hooks/*.sh` per-project paths; consumer-specific carve-outs |
| **project-code** | Per-consumer business logic / app code. NOT substrate-level | The consumer repo's actual codebase (e.g., `maxai/services/maxview/`) |

The LAYER distinguishes *what abstraction level* the change lives at. Abstraction-first default (per `feedback_abstraction_first_default_lens.md` memory): prefer `user-preference` > `substrate-generic` > `substrate-project-coupled` > `project-code` when multiple layers are viable.

## The 3 × 4 matrix

12 cells. Each cell has either a concrete pattern OR an explicit non-cell disposition.

|  | parley-substrate | WL-substrate | repo-where-found |
|---|---|---|---|
| **user-preference** | parley user-prefs (parley-domain) — e.g., `auto_wake_after_s` defaults | **WL user-prefs** — `.claude/preferences.toml` conventions (autonomy_level, planning.abstraction_first, etc.) | Consumer-local user-prefs (per-consumer-repo `.claude/preferences.toml`) |
| **substrate-generic** | parley substrate helper code — e.g., commissar reasoning, sidecar grammar | **WL substrate-generic** — `cross_links.py`, `validate.py`, doctrine docs, skills | (rare) — a consumer authoring substrate-generic code typically promotes it to WL-substrate |
| **substrate-project-coupled** | parley substrate config — e.g., session.toml | **WL substrate-project-coupled** — `.claude/workshop-lite-config.toml` `[cross_links].cross_substrate_roots` | Consumer's substrate config — per-project hook paths, per-project carve-outs |
| **project-code** | parley impl code — parley-domain features | (rare) — WL is a substrate, not a project; "WL-substrate + project-code" cell maps to the WL repo's own infrastructure code (CLI tooling, etc.) | **Consumer business logic** — the consumer's actual app code |

**Non-cell / rare dispositions:**

- `parley-substrate × project-code`: doesn't really exist independently — parley IS a substrate, so "project-code" in parley means parley's own impl, which collapses into substrate-generic from parley's own perspective.
- `repo-where-found × substrate-generic`: rare. When a consumer authors a reusable substrate-level mechanism, the canonical path is to promote it to WL-substrate (or contribute upstream).
- `WL-substrate × project-code`: rare. WL's own tooling (CLI, test infrastructure) lives here, but it's a small surface.

## Worked-example table

| Work item | SCOPE | LAYER | Artifact location |
|---|---|---|---|
| 421-warning OPT-(b) suppression mechanism (Issue 2026-05-31-03) | WL-substrate | substrate-generic (mechanism) + substrate-project-coupled (date-cutoff config) | `cross_links.py` extension + `workshop-lite-config.toml` cutoff section |
| 2-axis scope-routing skill (this very skill) | WL-substrate | substrate-generic | `.claude/skills/scope-routing/SKILL.md` |
| install-verb cert exhaustive bundle fidelity (wl.13) | parley-substrate (verb impl) + WL-substrate (assembler manifest + cert) | substrate-generic (both sides) | `parley/adopt.py` + `tests/test_adopt_workshop_lite_install_output.py` |
| EVALS-FIRST doctrine | WL-substrate | substrate-generic (doctrine doc + Hard Rule #7) | `docs/design/EVALS-FIRST-DOCTRINE.md` + `CLAUDE.md` |
| Q8=a grandfather cross-substrate fold-in (wl.21) | WL-substrate | substrate-generic (mechanism) + substrate-project-coupled (`cross_substrate_roots` config) | `cross_links.py:_captured_msg_id_set` + `workshop-lite-config.toml` |
| autonomy_level forward-motion pref (wl.15) | WL-substrate | user-preference | `.claude/preferences.toml` `[planning].autonomy_level` |
| Sidecar §1-vs-§4 boundary ratification ask (Issue 2026-05-31-04) | parley-substrate (the components) + WL-substrate (the doctrine governing them) | substrate-generic (boundary call) | Routes to @plan(dev-mgmt); affects parley sidecar code + WL EVALS-FIRST doctrine §4 |
| CI queue bottleneck (par-plan-class) | parley-substrate | substrate-project-coupled (runner manifest) | parley CI config — out of WL ownership |
| D3 cross-repo /whereami (Issue 2026-05-16-02) | WL-substrate (whereami skill) | substrate-generic (mechanism) gated on parley-substrate × substrate-project-coupled (substrate_path) | `.claude/skills/whereami/` extension, gated on @Par `whoami.substrate_path` landing |

## When to invoke this discipline

The 2-axis classification is the FIRST step in any of these:

1. **Filing a new Issue (`/record-issue`)**: classify the issue's SCOPE × LAYER. File the issue in the SCOPE's repo's `docs/issues/`. The LAYER informs the eventual fix shape.
2. **Dispatching a new Sprint**: classify the sprint's SCOPE × LAYER. If SCOPE is not WL-substrate, the sprint may need cross-arc coordination (xrequest to the SCOPE's owner). If LAYER is `user-preference`, default to abstraction-first (memory `feedback_abstraction_first_default_lens.md`).
3. **Choosing an artifact location**: the SCOPE × LAYER pair maps directly to a file location. Don't put substrate-generic code in a consumer repo; don't put consumer business logic in `.claude/scripts/dev-mgmt/`.
4. **Ownership routing**: SCOPE determines which team owns the work. Cross-scope items need explicit cross-arc coordination, not silent assumption.

## Cross-discipline cross-links

- **CLAUDE.md Hard Rule 1** (parley-agnostic at base): pins the SCOPE × LAYER boundary at the lib layer — WL-substrate × substrate-generic code must NEVER import parley. Parley-coupling only at SKILL / hook layer (substrate-project-coupled or above).
- **CLAUDE.md Hard Rule 2** (Workshop importability): WL-substrate × substrate-generic must map 1:1 to Workshop entity schema columns.
- **`feedback_abstraction_first_default_lens.md`** memory: when multiple LAYER values are viable, default to user-preference > substrate-generic > substrate-project-coupled > project-code.
- **`preferences` skill** (`.claude/skills/preferences/SKILL.md`): canonical reference for the user-preference LAYER mechanism.
- **`feedback_parley_routing_discipline.md`** memory: substantive cross-scope communication routes via `parley say` (not terminal text). Aligns with this skill's "cross-scope items need explicit cross-arc coordination" application rule.

## Application notes

- **Edge case — multi-LAYER work**: a single deliverable can span multiple LAYER values. E.g., the 421-suppression mechanism is `substrate-generic (mechanism) + substrate-project-coupled (config)`. Note both; don't pick one and lose the other.
- **Edge case — multi-SCOPE work**: a deliverable can span SCOPEs (e.g., the install-verb cert spans parley-substrate + WL-substrate). When it does, decompose the work into per-SCOPE chunks for execution; reconverge at integration.
- **Non-discipline cases**: this skill does NOT apply to (a) pure operational ops (commit, PR, branch hygiene), (b) immediate-conversation responses, (c) trivial copyedits. Reserve for material backlog / sprint / artifact-location decisions.

## Origin

Source Kris directives 09:42 + 09:50Z (2026-05-31). Routed through @user dispatch msg-de2a56fae543 (wl.21 sprint), msg-dd5c9deb97eb (421-warning classification example), msg-9453e119b8e9 (wl.23 sprint dispatch). Codified by sprint wl.23.
