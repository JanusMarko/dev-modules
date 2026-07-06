---
name: worktree-branch-hygiene
tier: 1
applies_when:
  - dispatching-a-cohort-or-charter-that-may-need-worktree-isolation
  - cohort-shape-pre-declaration-includes-worktree-decision
  - operator-or-planner-considering-worktree-cleanup
  - planner-considering-branch-naming-for-a-new-cohort
  - operator-running-post-LAND-cleanup-sweep
  - planner-or-validator-detecting-orphan-worktree-or-branch-state
when_not_to_apply:
  - single-seat-LIGHT cohort with no parallel-stream / firewall need (no worktree needed; main branch + ephemeral dev is fine)
  - one-shot doc / convention / decision filing (single-commit on main; no branch)
origin:
  date: 2026-06-08
  context: '@plan dispatch msg-6087e6eec91d (Q4 of Q3+Q4 split) routed via msg-7437ea3911f7. Empirical basis: Q3 workshop-lite archeology audit (docs/audits/2026-06-08-workshop-lite-archeology-restore-redo-abandon-superseded.md) which catalogued ~115 artifacts across 4 surfaces (Claude project keys + git worktrees + local branches + remote branches) and surfaced 3 orphan-class taxonomy (§7.2) + 3 anti-pattern candidates (§7.3). Convention codifies the rules to prevent the anti-patterns from accumulating in future cohort cycles.'
see_also:
  - cohort-shape-variant-pre-declaration
  - silence-policy-never-binary
  - governance-layer-must-be-durable
source_msg_ids:
  - msg-6087e6eec91d  # @plan Q3+Q4 dispatch (lead-only to par-plan)
  - msg-7437ea3911f7  # @plan rebroadcast with @wsl-plan Q3+Q4 split
  - msg-aa6475204f61  # @plan ratify queue-to-next-seat
linked_audits:
  - 2026-06-08-workshop-lite-archeology-restore-redo-abandon-superseded  # Q3 empirical basis
linked_issues:
  - 2026-06-04-13-editable-install-mapping-rewritten-by-pip-install-e-from-worktree-causes-silent-substrate-breakage-on-worktree-cleanup  # cross-substrate workaround tied to worktree cleanup (parley-side, resolved)
---

# Worktree + branch hygiene convention

## Rule

The workshop-lite substrate uses **branch-per-cohort + worktree-per-seat + merge-to-main + post-LAND-prune** as its concurrency + isolation model. This convention codifies the **when** + **how** of each step so orphan accumulation does not silently degrade the surface over time.

The convention has 5 sections:

1. **When to create a worktree** (§A)
2. **Branch naming** (§B)
3. **Worktree cleanup** (§C)
4. **Branch cleanup** (§D)
5. **Enforcement candidates + validator hooks** (§E)

## §A — When to create a worktree

A git worktree is created when one of the following triggers apply. **Default: do not create a worktree.** Worktree creation is opt-in per trigger.

### §A.1 — Triggers (create a worktree)

- **Cohort isolation** — a cohort charter §3 specifies FULL-3-leg / LIGHT-3-leg with a separate builder seat that needs its own checkout (so the builder can rebase + amend + commit without contending with main-cwd seats). One worktree per cohort builder + optionally per tester + per verifier when those legs spawn separate seats.
- **Parallel-stream concurrency** — two or more cohorts (or two non-cohort charters) are in flight simultaneously and their working trees would otherwise contend on the same files. The worktree pattern is the substrate-level concurrency primitive.
- **Firewall-strict adversarial review** — verifier / adversarial review seats that must NOT see builder-side context spawn into a separate worktree with restricted visibility (`visibility_profile.diff = false` on the parley seat side; worktree provides the cwd-side isolation).
- **Long-running investigation / exploration** — investigator seats (e.g., shared-cwd race investigator, archeology investigator on a remote substrate, RCA seat) that need a stable checkout for the duration of an N-hour-to-N-day investigation without main-cwd churn.

### §A.2 — When NOT to create a worktree

- **Single-seat LIGHT-class work** — one-shot transforms, doc updates, convention filings, single-cohort cert envelopes that fit in one seat. Use main directly with a feature-branch IF the work is multi-commit AND wants pre-LAND review; otherwise commit directly to main under standing pre-auth.
- **Single-commit on main** — decision filings, issue filings, doc updates that fit in one commit + push do not need a branch let alone a worktree.
- **Read-only audit / archeology / review** — auditor / reviewer seats that don't make code changes don't need a worktree (they can read from main-cwd or remote).
- **Mechanical-transform-class** — if the work is mechanical-transform per HR #7 (b) and the charter §3 picked `builder-own-cert-only` per [[cohort-shape-variant-pre-declaration]], the worktree is optional; if the transform is single-commit + low-risk, main-cwd direct is acceptable.

### §A.3 — Worktree creation discipline

When a worktree IS created per §A.1:

- **Path convention**: `/home/krisd/code/.<repo-name>-<cohort-or-seat-id>-<role>-wt/` (dot-prefix hides from default `ls`; role suffix distinguishes builder / tester / verifier / investigator / etc.).
- **Branch convention**: per §B below.
- **Editable-install discipline**: NEVER run `pip install -e .` from within a worktree per CLAUDE.md HR #11 (parley-substrate). The shared venv's MAPPING is anchored at the canonical repo; running editable-install from a worktree silently rewrites the MAPPING to point at the worktree, causing breakage when the worktree is removed. (Tracked at par:2026-06-04-13; substrate-enforced via `parley worktree-remove` refuse-to-remove gate + `parley install --verify-editable-mapping` audit verb; this rule propagates from the parley substrate.)
- **Worktree spawn registration**: when spawned as a parley member, the worktree path should appear in the member's `cwd` field for transparency to coordinator + CTO. The pattern is mature on the parley substrate (per `parley member spawn`) and the WL substrate inherits it via parley-aware skills.

## §B — Branch naming

Branches are the load-bearing identifier for the work-in-flight. Naming is the institutional memory of who-is-doing-what.

### §B.1 — Canonical naming patterns

Three patterns are canonical. Each pattern has a per-pattern hygiene rule.

#### §B.1.a — Cohort-id-prefixed (preferred for multi-leg cohort work)

Pattern: `<repo>-cohort-<id>-<role-or-content>` where `<id>` is the cohort identifier (A / B / C / GG / JJ / KK / PW / WL.29 / WL.30 / etc.) and `<role-or-content>` is one of `builder` / `tester` / `verifier` / a short content descriptor.

Examples:
- `workshop-lite-cohort-WL30-builder`
- `workshop-lite-cohort-PW-2026-06-07-playwright-web-ui-verify`
- `workshop-lite-cohort-GG-tester-cert`

Hygiene rule: post-LAND, the cohort branch is merged via no-ff merge into main + the branch ref is eligible for cleanup per §D below.

#### §B.1.b — Sprint-id-prefixed (legitimate for sprint-internal work)

Pattern: `<repo>-sprint-<id>-<content>` for work scoped to a sprint internal milestone rather than a free-standing cohort.

Hygiene rule: branches eligible for cleanup at sprint-close.

#### §B.1.c — Issue-id-prefixed (for issue-fix branches outside cohort scope)

Pattern: `<repo>-issue-<YYYY-MM-DD-NN>-<short-slug>` for issue-fix work that doesn't warrant a full cohort spawn.

Examples (from Q3 archeology empirical surface):
- `workshop-lite-issue-08-cursor-chain-d6-impl`

Hygiene rule: branches eligible for cleanup post-LAND.

### §B.2 — Anti-pattern: platform-named branches (avoid)

**Avoid platform-named branches** (e.g., `consult-skill-platform-cert-harness`, `consult-skill-v2-impl`, `prd-entity-cross-repo-pm-bridge-verifier-review`).

Q3 archeology §7.3 finding: platform-named branches drift into a **direct-main-commit shipping pattern** (the platform LANDs via direct main commits after pre-LAND iteration, rather than via branch merge), leaving the platform-named branch ref unmerged-but-superseded. These accumulate as the "direct-main-commit orphans" class (§7.2.3) — content shipped, branch ref stale, no cleanup signal.

Cohort-id naming + the post-LAND-merge discipline avoid this.

If a platform charter MUST use platform-named branches (e.g., for legacy / migration / external coordination reasons), the charter §3 must declare:
- The intended shipping path (branch-merge OR direct-main-commit-with-explicit-branch-cleanup).
- If direct-main-commit: the post-LAND `git branch -D <platform-branch>` step is part of the LAND signal flow.

### §B.3 — Anti-pattern: auto-spawn-hash branches (worktree-agent-*) accumulate silently

Q3 archeology §5.4 surfaced 8 `worktree-agent-<hash>` branches from prior automation. All MERGED to main but persist as orphan refs.

**Rule**: any automation that creates branches MUST emit a post-cleanup signal that the branch refs are eligible for `git branch -d` removal once the automation completes. If automation doesn't emit cleanup signal, the branches must be tagged with a `auto-spawn-cleanup-eligible-after-<date>` ref-message convention so a periodic cleanup sweep can identify them.

### §B.3.par — Parley-substrate automation-branch naming (@par-plan amendment)

Parley substrate carries two automation-branch surfaces:

**Surface 1: `parley member spawn --cohort-impl-branch <branch>`** (par-p0-defect-58 cohort branch polling primitive). When a cohort builder is spawned with this flag, the sidecar registers the seat as the emitter of the named branch + polls origin for SHA advances + emits `Kind.BRANCH_UPDATED` records. The branch is created BY THE COHORT BUILDER (typically via `git worktree add -b <branch>`) and is named per §B.1.a cohort-id-prefixed pattern.

**Recommended naming for parley cohorts** (forward-only post 2026-06-08, per arc-not-sprint-nomenclature retirement):
- Builder impl: `parley-cohort-<id>-<topic-slug>` (e.g., `parley-cohort-QQ-force-wake-noise-kind-filter`)
- Tester cert: `parley-cohort-<id>-tester-cert`
- Verifier cert: `parley-cohort-<id>-verifier-cert` (when verifier is a spawned seat; when verifier role is replaced by `/consult devil-advocate`, no third branch is needed)

**Legacy patterns observed in the parley substrate** (per the parley-side Q3 archeology at `parley/docs/audits/2026-06-08-par-substrate-archeology-investigation.md` §2): `par-p0-cohort-<id>-impl` / `par-p0-cohort-<id>-tester-cert` / `par-p0-cohort-<id>-verifier-cert` were used through May/early-June. These predate the arc-not-sprint nomenclature retirement (2026-06-03) and are retained for forensic re-replay; new cohorts use the `parley-cohort-` prefix.

**Surface 2: Auto-LAND-fire daemon** (planned/in-design per cohort-builder-substrate-fix-arc). When the auto-LAND-fire primitive ships, it will create + merge cohort-LAND-merge branches programmatically. The auto-spawn cleanup signal pattern applies: each programmatic branch must emit a post-merge `Kind.SHIP_EPIC_*` audit-trail that includes the branch cleanup-eligibility signal.

**Cross-surface rule**: programmatic-emitted parley branches MUST be discoverable via `parley overview --cohort-impl-branches` (planned surface; the inventory verb candidate from this convention's §E.2). Until the verb ships, `git for-each-ref refs/heads --format='%(refname:short) | %(committerdate:iso) | %(authorname)' | grep -E '^parley-cohort-'` is the manual probe.

## §C — Worktree cleanup

A worktree exists for the lifetime of its purpose. After the purpose is served (LAND complete + follow-up window closed), the worktree is cleanup-eligible.

### §C.1 — Cleanup triggers

- **Post-LAND + N-day stability window**: once a cohort's LAND has been on main for **N days** without rollback / amend-and-replay / follow-up-LAND, the worktree is eligible for `git worktree remove <path>`. Default N = 7 days; charter §3 may declare a longer window for high-risk LANDs (e.g., cross-substrate migrations may declare 14 or 30 days).
- **Charter abandonment**: if a charter is explicitly abandoned (CTO ratify or operator direct), all its worktrees are immediately eligible for cleanup.
- **Worktree-idle-90-days**: any worktree with no commits + no `git status` changes for 90 days is eligible for cleanup with `git worktree remove --force` (the --force handles the case where the worktree dir is missing).

### §C.2 — Cleanup execution

- Use `parley worktree-remove <path>` (parley-substrate-mandated; pre-checks the editable-install MAPPING per par:2026-06-04-13 substrate-enforcement and refuses-to-remove if the target is the editable-install anchor).
- If the worktree path is the editable-install anchor, the operator must re-anchor via `pip install -e /home/krisd/code/<repo>` from the canonical repo path BEFORE the worktree-remove proceeds. Per CLAUDE.md HR #11 (parley-substrate).
- Post-`git worktree remove`, run `parley install --verify-editable-mapping` to confirm the venv MAPPING is intact at the canonical repo path.

### §C.3 — Claude CLI project-key sweep

Each worktree at cleanup time has an associated `~/.claude/projects/-home-krisd-code-<hashed-path>` directory holding Claude CLI session traces. These persist as orphan project keys after worktree removal.

**Rule**: post-worktree-removal, `rm -rf ~/.claude/projects/-home-krisd-code-<hashed-path-matching-removed-worktree>` is cleanup-eligible. The project key is a cache, not load-bearing; deletion is lossless.

Q3 archeology found **22 orphan project keys** under workshop-lite patterns; cleanup is informational + operator-discretionary.

### §C.4 — Anti-pattern: indefinite-leave-idle (clarifies prior handoff convention)

Prior handoff convention was "leave [cohort worktrees] idle until kicked." This produces sustained orphan-project-key accumulation across cohort cycles.

**Convention amendment**: replace "leave idle until kicked" with "**stability-window-cleanup-default + scale-trigger-exception**":
- **Default**: cleanup at post-LAND + 7-day stability window per §C.1 above.
- **Scale-trigger exception**: if cohort count consistently exceeds 5-7 across multi-cohort windows (per [[D3 audit Row 4 scale-trigger framing]]), defer cleanup until the cohort-fan-out window closes to avoid churn — but never indefinitely.
- **Forensic exception**: if a cohort's LAND is under post-LAND investigation (e.g., DA-find class follow-up, regression bisect), the worktree is preserved until investigation completes.

## §D — Branch cleanup

Branches accumulate as the per-cohort + per-stream identifier. Post-LAND, most are tracker-only orphans.

### §D.1 — Cleanup triggers (per §B branch class)

- **Cohort-id-prefixed (§B.1.a)**: branch cleanup-eligible at the same time as its worktree (post-LAND + N-day stability window). Use `git branch -d <name>` (merged) for the canonical case.
- **Sprint-id-prefixed (§B.1.b)**: at sprint-close (sprint moved from `active/` to `archive/` per /end-sprint).
- **Issue-id-prefixed (§B.1.c)**: post-LAND immediately.
- **Platform-named (§B.2 anti-pattern — avoid, but if present)**: post-LAND with `git branch -D <name>` (force-delete; content shipped via direct main commits not branch merge — branch is unmerged from main's perspective).
- **Auto-spawn-hash (§B.3 anti-pattern — avoid)**: at automation-cleanup-signal OR via periodic sweep.
- **Verifier-leg branches with finding-absorption shipping**: see §D.2 below.

### §D.2 — Verifier-finding-absorption shipping (cohort GG class)

Q3 archeology §7.2.2 + §7.3.2 surfaced the **finding-absorption orphan** class: verifier leg branches whose findings were extracted into discrete per-finding main commits (doc updates / decisions / issues) rather than merged as a cohort leg.

This is a real pattern. The cohort GG verifier-verdict (`workshop-lite-cohort-GG-verifier-verdict`) is the canonical example: 7-axis mutation matrix + A8 re-trial replay produced findings that landed via `85d0695 doc(consult SKILL.md) ... per cohort GG OBS-1` + `1d06f28 close(wl:2026-06-05-08) ... post cohort GG LAND` rather than as a verifier leg merge.

**Rule**: verifier-verdict-disposition is a charter §3 sub-declaration:
- **(disposition-a)** Verifier verdict merges as a leg (default; verdict content is structural — cert axes / replay runs).
- **(disposition-b)** Verifier verdict findings are absorbed via per-finding discrete commits (when verdict content is better expressed as per-finding decisions / docs / issues; e.g., adversarial mutation findings without structural code changes).

If disposition-b, the charter MUST enumerate the expected per-finding commit list at chunk-5 LAND time + the verifier branch is `git branch -D` cleanup-eligible.

### §D.3 — Remote branch pruning

Q3 archeology §6 surfaced 20 remote branches on origin. Same disposition logic as local; cleanup with `git push origin --delete <branch>`.

**Rule**: post-LAND + N-day stability window, sweep `git for-each-ref refs/remotes/origin --format='%(refname:short) %(committerdate:iso)'` for cohort branches older than the window AND merged to origin/main → eligible for `git push origin --delete`.

### §D.4 — Never-merged-flag

A branch that is local + unmerged + has no commits in N days is a `never-merged-flag` candidate. Per §B.2 + §B.3 anti-patterns, these accumulate from platform-named direct-main-commit-shipping + auto-spawn automation.

**Rule**: planner-class periodic sweep — `git branch --no-merged main | xargs -I {} sh -c "git log -1 --format='%cd %h {}' {}"` → identify branches with stale commit dates → propose-and-execute cleanup (use `git branch -D` for unmerged branches whose content is otherwise on main; flag for restore-investigation if the branch's tip commit is NOT on main).

## §E — Enforcement candidates + validator hooks

This convention is Tier-1 + portable; the discipline is operator + planner responsibility primarily. Enforcement candidates below are optional substrate hooks that automate the discipline.

### §E.1 — HR-style enforcement candidates

These are CLAUDE.md HR (Hard Rule) candidates derived from §A–§D:

- **HR candidate: pre-auth-pre-declare-worktree-trigger**. A cohort charter §3 picking FULL-3-leg / LIGHT-3-leg MUST pre-declare whether worktrees are created + the path convention.
- **HR candidate: post-LAND-cleanup-signal**. A cohort LAND signal flow MUST include the worktree + branch cleanup-eligibility-window declaration (default 7d; override stated).
- **HR candidate: editable-install-discipline**. NEVER `pip install -e .` from a worktree (already on parley substrate per HR #11; propagates to workshop-lite as cross-substrate inherited rule).
- **HR candidate: platform-named-branches-require-explicit-shipping-path**. If a charter uses platform-named branches (e.g., `consult-skill-*`, `prd-entity-cross-repo-pm-bridge-*`), §3 MUST declare branch-merge vs direct-main-commit shipping path + explicit cleanup step.

### §E.2 — Validator hooks

Workshop-lite validator (`python3 .claude/scripts/dev-mgmt/cli.py validate`) does NOT currently sweep git state per HR #5 (never-block discipline). Validator hooks for worktree + branch hygiene are advisory-only candidates:

- **Validator hook: orphan-project-key advisory**. Periodic sweep of `~/.claude/projects/` for workshop-lite patterns; surface count of orphan project keys (worktree-not-found) as advisory output. Threshold: surface in `state_digest` if count > 30.
- **Validator hook: stale-worktree advisory**. `git worktree list` + per-worktree commit-recency check; surface worktrees with no commits in 14+ days as advisory output.
- **Validator hook: never-merged-branch advisory**. `git branch --no-merged main` count + names; surface if count > 5 as advisory output (signal that platform-named or auto-spawn-hash anti-patterns are accumulating).

All validator hooks are ADVISORY ONLY; never block, never auto-cleanup. Cleanup remains operator-discretionary + planner-coordinated.

### §E.3 — Periodic sweep cadence (planner-class operator-coordinated)

Recommended planner-class cadence:
- **Daily**: read the validator advisory output; act on high-water-mark surfaces (orphan project keys > 30; stale worktrees > 5; unmerged branches > 10).
- **Weekly**: dedicated cleanup sweep — execute the safe-to-execute-now cleanup operations from Q3 archeology §8.1; deferred operations from §8.2 + §8.3 considered per stability-window state.
- **Post-major-LAND**: incremental cleanup of just-LANDed cohort artifacts + 7-day stability-window timer started.

## §F — Cross-substrate coordination

This convention is workshop-lite-canonical; parley-substrate has its own counterparts that compose with it.

### §F.1 — Parley-side coupling (@par-plan amendment 2026-06-08)

Parley substrate carries the following load-bearing primitives that interact with this convention. The parley-side empirical basis is the @par-plan archeology at `parley/docs/audits/2026-06-08-par-substrate-archeology-investigation.md` (55 worktrees / 128 branches / 566 CC jsonl files surveyed; 10 lost-work candidates; 9 anti-patterns).

**§F.1.a — Parley CLI verbs (substrate-enforced gates)**:

- `parley worktree-remove <path>` — refuse-to-remove gate for editable-install MAPPING per par:2026-06-04-13 (HIGH-severity substrate bug class). Pre-checks the venv's `__editable___parley_*_finder.py` MAPPING; refuses-to-remove if the target IS the MAPPING anchor; surfaces remediation verb-string. This is the CANONICAL worktree-removal verb on the parley substrate — `git worktree remove <path>` direct-invocation is allowed but bypasses the gate.
- `parley install --verify-editable-mapping` — audit verb that surfaces the current MAPPING target + WARNs on non-canonical paths. Recommended periodic operator-cadence (weekly per §E.3 sweep cadence).
- `parley member spawn --cwd <path>` — cohort-seat spawn primitive that records the worktree's path in the roster Member.cwd field for coordinator + CTO visibility. The seat's parley membership is bound to the worktree's cwd for the seat's lifetime.

**§F.1.b — Parley-substrate cohort topology** (empirical from @par-plan archeology):

The parley substrate produces a per-cohort worktree set scoped per the cohort's FULL-3-leg / LIGHT-3-leg variant:

- **FULL-3-leg with codex-builder + cc-cert + /consult devil-advocate** (cohort QQ exemplar, 2026-06-08): 2 worktrees per cohort (`/home/krisd/code/.parley-cohort-<id>-builder-wt` + `/home/krisd/code/.parley-cohort-<id>-tester-wt`); verifier role replaced by single-shot `/consult devil-advocate` consultation (no third worktree).
- **FULL-3-leg with traditional builder + tester + verifier** (cohort PP exemplar): 3 worktrees per cohort; verifier seat spawned at adversarial-review phase.
- **LIGHT-single-seat** (par:06-06-04/06/07 exemplars from earlier this session): 0 worktrees; the builder operates in main-cwd directly. Per §A.2.

**§F.1.c — CLAUDE.md HR #11 inheritance**:

The parley substrate's CLAUDE.md Hard Rule #11 codifies the editable-install discipline ("NEVER `pip install -e .` from a worktree; use the canonical repo path"). This rule is parley-substrate-side enforcement; the workshop-lite-installed convention adopts it as cross-substrate inherited (§E.1 HR candidate `editable-install-discipline`).

**§F.1.d — Parley-side cleanup anti-patterns (per @par-plan archeology §5)**:

The parley substrate's archeology surfaced 9 anti-patterns (this convention's §A–§D address the bulk; the parley-specific deltas):

1. **Persistent WIP on main worktree** — Candidate 1 at the @par-plan archeology surfaced 57 uncommitted files on `/home/krisd/code/parley` main worktree surviving multiple seat-reseats. Per this convention, main-worktree should not become a permanent WIP store; the discipline-violation candidate is for future HR codification.
2. **Untracked code in feature worktrees** — Candidate 2 (rescued at par-p0-codex-parity-builder commit `441a6b0` post-`@plan ratify msg-94c66da534d2`): the `mcp_*.py` quartet + translate skill + bin/wl-mcp existed only on disk in `/home/krisd/code/parley-wt-codex-parity`. Per §C.1, worktree cleanup must not happen before untracked files are committed-or-stashed.
3. **Cert-branch retention indefinite** — 66% of parley branches (85 of 128 per @par-plan archeology §2) are merged-but-not-pruned. The cert-branch worktree retention serves forensic re-replay (per [[reference_cert_builder_worktree_env_override]]) but cleanup-policy was undefined pre-this-convention. Now governed by §C.4 + §D.1.
4. **/tmp worktrees** — 2 `/tmp`-rooted parley worktrees observed (vanish on reboot). Operators may treat /tmp worktrees as known-ephemeral; explicit `parley worktree-remove` on reboot is hygiene + records the cleanup in the audit trail.

**§F.1.e — Parley-side automation-branch naming** (see §B.3.par for full details):

The `parley-cohort-<id>-<topic-slug>` pattern is the forward-only canonical shape; legacy `par-p0-cohort-<id>-*` is retained for forensic re-replay but new cohorts use the new pattern.

**§F.1.f — Cross-substrate companion issues filed (D3 audit chunk-4 par-side)**:

The parley substrate has three par-side tracking issues filed today that compose with this convention's hygiene rules:

- `par:2026-06-08-03` (MEDIUM scale-trigger) — `charter_closed` state primitive + `Kind.MEMBER_AUTO_PRUNED`; composes with §C.4 scale-trigger exception
- `par:2026-06-08-04` (LOW) — direct_only delivery gap structural-enforcement for headless consumer class
- `par:2026-06-08-05` (LOW) — resume-nudge silence-class classifier (composes with operator-cadence sweeps via cleaner banner-counts)

These are tracked-defer items; the convention's discipline operates orthogonally.

### §F.2 — Workshop-lite as cross-substrate adopter

For consumer repos that adopt workshop-lite (parley / ccweb / maxai / external), this convention propagates via the workshop-lite installer drop-set. Adopters inherit:
- §A worktree triggers (substrate-portable)
- §B canonical branch naming patterns
- §C cleanup triggers + Claude CLI project-key sweep rule
- §D branch cleanup + verifier-finding-absorption disposition
- §E validator-hook candidates (workshop-lite-installable; adopters opt-in via `.claude/dev-mgmt-validator.toml`)

## §G — Compositional notes

This convention composes with:

- [[cohort-shape-variant-pre-declaration]] — §3 of any cohort charter is the primary integration point for §A worktree pre-declaration + §D verifier-finding-absorption disposition.
- `feedback_shared_cwd_contention.md` — pre-worktree shared-cwd race (resolved by worktree-per-worker convention; this convention codifies the resolution).
- `feedback_watchdog_post_charter_satisfaction.md` — post-LAND "leave idle until kicked" rephrased per §C.4 stability-window-cleanup-default convention amendment.
- [[D3 audit Row 4]] — scale-trigger framing on cohort-fan-out informs §C.4 scale-trigger exception.

## §H — Status

**Authored 2026-06-08T15:20Z by @wsl-plan** per @plan dispatch msg-6087e6eec91d. **@par-plan amendment 2026-06-08T15:25Z**: §B.3.par + §F.1.a-f populated with parley-substrate specifics (cohort topology, CLI verbs, HR #11 inheritance, anti-pattern deltas, automation-branch naming, cross-substrate companion issues). Tier-1 substrate-portable; propagates to consumer repos via `parley adopt-workshop-lite` install drop-set.

This convention is the durable rules-of-play artifact; the Q3 archeology audit is the empirical inventory that informed it.
