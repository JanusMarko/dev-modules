---
name: evidence-persists-never-tmp-only
tier: 1
applies_when:
  - a run is about to produce gate-critical output (full-suite logs, benchmark
    result JSONs, cert evidence, probe matrices, tracebacks)
  - choosing an output path for any artifact a verdict or land-gate will cite
when_not_to_apply:
  - genuinely scratch intermediates no verdict will ever cite (but if a verdict
    later cites them, they were never scratch)
  - secrets-bearing output (persist to $HOME with mode 0600, never to a repo)
origin:
  date: 2026-06-10
  context: 'Crash lessons-learned pass (Kris directive msg-15dae5951227, review-lead
    wsl-plan collation msg-e25880822edd, CTO ratify msg-889211d8fe09). The
    2026-06-10 18:00:15Z host crash wiped /tmp: ALL benchmark raw-result JSONs
    (6 rounds) were lost — conclusions survived only via a decision-doc +
    Telegram-delivered renders (now the only surviving copies); par-plan''s
    predecessor full-suite logs + tracebacks were lost, costing a fresh 6.5-min
    re-run purely to recover evidence. Merged from CTO lesson (c) +
    benchmark-lead L1 + par-plan proposal A. Per-substrate fix-paths stay in
    workshop-lite issue 2026-06-10-09 (bench charters + skill recipe) and the
    par-side equivalent.'
see_also:
  - push-early-unconditional
  - governance-layer-must-be-durable
  - arc-close-handoff-discipline
---

# Gate-critical evidence persists to repo or $HOME at capture time — never /tmp-only

## Rule

Any run output that a verdict, cert, land-gate, or report will cite
is written to a reboot-durable location **at capture time**: a repo
path (committed at the next boundary, or a committed throwaway/wip
branch for bulk data) or `$HOME`. `/tmp` is a proven reboot loss
vector and is never the only copy of gate-critical evidence.

## Why

The 2026-06-10 crash destroyed every /tmp-resident evidence artifact
in one stroke across two independent seats: six benchmark rounds of
raw JSONs (the conclusions now rest on a decision-doc and chat-delivered
renders alone) and a full-suite proof log (recovered only by paying
the run again). Evidence that exists only in /tmp is evidence the
org has not actually captured.

## When to apply

At output-path choice for every gate-critical run — bench rounds,
full-suite proofs, cert harness output, probe matrices. Charters for
evidence-producing seats mandate this at round close (see
workshop-lite issue 2026-06-10-09 for the bench-charter fix-path).

## When NOT to apply

True scratch intermediates; secrets-bearing output goes to $HOME
mode 0600, not a repo.

## Enforcement tier (per 3-layer model — Kris ask msg-a2bd077282de)

**[A] audit-tier detector + narrow skill-layer [E] + [P] pack;
general [E] is dishonest.** "Gate-critical" is agent judgment — the
substrate can't distinguish evidence from scratch at write time, and
a blanket /tmp write-deny breaks legitimate scratch use. Detector:
`[tmp_evidence_reference]` advisory (entities citing /tmp as
evidence) — issue `2026-06-10-12`. Narrow [E]: skill-owned recipes
hard-code durable output paths by construction (bench skill per
issue -09). [P] half rides the Layer-C pack.

## See also

[[push-early-unconditional]] (the commit-side sibling),
[[arc-close-handoff-discipline]] (the inventory that proves delivery),
[[governance-layer-must-be-durable]].
