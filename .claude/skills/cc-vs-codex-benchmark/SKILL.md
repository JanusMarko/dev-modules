---
name: cc-vs-codex-benchmark
description: Run a CC-vs-codex paired head-to-head benchmark across N role_kinds. Captures wall-clock + correctness + per-role recommendation; produces a synthesis HTML report delivered to @user via Telegram. Use when the user types /cc-vs-codex-benchmark or asks to compare CC and codex on a set of specialized role tasks (tester / planner / postgresql_expert / etc.).
---

# /cc-vs-codex-benchmark

Empirically measure Opus 4.7 (claude-opus-4-7[1m]) vs Codex 0.130 across N specified
role_kinds, producing a results JSON + synthesis HTML for operator decision. Methodology
codified from R1+R2+R3+R4+R5 ground-truth runs on 2026-06-07.

Agent-class-portable: ALL 3 coding-agent classes (CC + codex + agy) can invoke this
recipe. CC users get the slash command; codex/agy users walk the SKILL.md steps directly.

## When to invoke

- Operator types `/cc-vs-codex-benchmark`
- Operator asks for an empirical CC-vs-codex comparison on specific role_kinds
- Planner seat needs to ratify/correct a per-role recommendation with fresh data (e.g.
  a Phase-N follow-up after a substrate change)
- Confirmation/regression run with n=2 on previously-tested roles after model upgrades

## Hard rules

1. **No mainline writes.** Every paired-agent run is in an ephemeral worktree under
   `/tmp/bench-<date>/wts-r<round>/`. Results JSON is committable to a throwaway branch
   only. Mainline branches stay untouched.
2. **3-concurrent CC spawn cap.** Per @plan dispatch msg-d947b72c673d: max 3
   concurrent fresh `parley member spawn --agent-type claude_code` per session. Spawn
   in 3-3-3-... waves; remove finished seats before next wave. Codex headless side has
   no spawn cap (single-process sequential runner).
3. **Distinct charter content per role across rounds.** When running n=2+ on the same
   role_kind, use DIFFERENT charter content (different fixtures / different domain)
   to avoid pattern memorization. Same shape, different specifics.
4. **Heuristic correctness only.** This skill measures artifact-presence + size +
   keyword-coverage. For gold-standard verdicts, run a `/consult devil-advocate`
   over each artifact post-suite as a follow-up; do NOT block synthesis on it.
5. **Night-mode HTML, mobile-friendly viewport.** Kris reads on phone. CSS at
   `/tmp/bench-<date>/render_html.CSS` (or any prior round's `render_html.py`).
6. **Telegram delivery is `sendDocument` curl, NOT `parley telegram send`.** The
   parley verb is plain-text-only; HTML files need Bot API `sendDocument`. See §6.
7. **Firewall the contestant's parley identity (codex legs).** A `codex exec`
   launched in a parley-enabled worktree AUTO-discovers and posts to the LIVE
   session under the ORCHESTRATOR's identity — it will run `parley whoami`/
   `parley read` and can emit chat (e.g. a `[start]`) as you, AND its ambient
   reads contaminate the token measurement. `PARLEY_HOME` redirect is NOT
   sufficient (parley resolves the member from env identity, not cwd). Launch
   every codex contestant with the identity env stripped:
   `env -u TMUX -u TMUX_PANE -u PARLEY_MEMBER_ID -u PARLEY_SESSION codex exec …`
   so parley cannot resolve a member (its calls no-op with a Usage error).
   VERIFY per leg: `grep -c "since last delivery" <runs.jsonl>` must be `0`.
   (Origin: 2026-06-12 4th-case token ladder — leg-1 attempt-1 breached, caught,
   re-run clean. Interactive CC contestants spawned via `parley member spawn`
   are members by design; prefer `--role-kind tester` for
   `subscribes_to_broadcast=False` + `--no-spawn-wake --auto-wake-after-s 0`
   and a charter line forbidding `parley read`.)

## 1. Gather inputs

Required:

- **role_kinds**: list of parley role_kind values to test (e.g. `tester`,
  `adversarial_reviewer`, `postgresql_expert`, ...). Run `parley member spawn --help`
  to see the current enum.
- **round_id**: short id for this round (e.g. `R6`, `R5-confirmation`,
  `phase2-cloud`). Becomes the dir suffix.
- **base_sha**: parley HEAD SHA at dispatch time. Pin for reproducibility.

Optional:

- **n** (default 1): how many independent samples per role_kind. n=2+ requires
  distinct charter content per round.
- **tier** (default `Complex`): difficulty marker on each test (`Simple` | `Complex`).
- **focus_areas**: optional list of specialized-capability angles to probe (e.g.
  "OWASP coverage for security_expert", "index-design intuition for postgresql_expert").

If any required input is missing or ambiguous and you're a CC seat, use
`AskUserQuestion` to collect. If you're codex/agy, surface the gap to the operator.

## 2. Workspace layout

```
/tmp/bench-<YYYY-MM-DD>/
├── charters-r<round>/<test-id>.md          # one charter per test
├── wts-r<round>/bench-<test-id>-{cc,codex}/  # paired ephemeral worktrees
│   ├── CHARTER.md                          # copy of the charter for the seat
│   ├── .start_ts                           # unix-ts marker for wall-clock
│   └── <primary-artifact>                  # produced by the agent
├── runs-r<round>/<test-id>-<adapter>.json  # per-run JSON record
├── runner-r<round>-codex.py                # headless codex runner
├── compile_r<round>.py                     # results compiler
├── SYNTHESIS-r<round>.md                   # round-specific synthesis
└── SYNTHESIS-combined.md (+ .html)         # cross-round synthesis
```

Use `/tmp` because workspaces are throwaway. NEVER write under the workshop-lite repo.

## 3. Author charters (per role_kind)

Each charter is a markdown file the agent reads + executes. Shape:

```markdown
# <test-id> — <role_kind>

<one-paragraph task description — must reveal role-specific capability, not generic
competence. Aim for: a real problem a domain expert would diagnose differently than a
generalist.>

## <Inputs / fixture section>

<inline fixture: README excerpt / function / backlog / transcript / etc. NEVER reference
external files — every input must be inline so the agent in cwd /tmp/bench-* can execute>

## Required sections in <primary-artifact>

<numbered list of sections the artifact must contain>

## Acceptance criteria

<bulleted list of testable assertions: ≥N findings / artifact size threshold / required
concept-keyword presence / structural patterns>
```

**Charter-authoring principles (load-bearing for benchmark value):**

- **Specialized real-world task.** Not "write a CRUD app" (generic) — "design the
  PostgreSQL schema + 1 migration with PG-11+-safe CONCURRENTLY+NOT-VALID+DEFAULT,
  composite index supporting `ORDER BY` without a Sort node" (postgresql-specific).
- **≥4 acceptance criteria per charter.** Below 4, the heuristic-PASS judgment is too
  permissive.
- **At least one criterion that distinguishes generalist from specialist output.** E.g.
  "find the rejected alternative + reasoning" / "name the bottleneck step" / "ranked
  hardest-to-catch mutations".
- **Inline fixtures only.** Self-contained. Charter copies survive across cwd boundary.
- **Length 800-2000 bytes.** Too short = under-specified; too long = anchoring noise.

See `/tmp/bench-2026-06-07/charters-r{3,4,5}/` for 24 worked examples across 22
role_kinds.

## 4. Paired-agent spawn protocol

For each charter, spawn TWO agents in paired ephemeral worktrees:

### CC side (interactive tmux via parley)

```bash
# Touch start marker BEFORE spawn (wall-clock anchor)
date +%s > /tmp/bench-<date>/wts-r<round>/bench-<test-id>-cc/.start_ts

# Spawn via parley member spawn
parley member spawn bench-cc-<test-id> \
  --role-kind <role_kind> \
  --cwd /tmp/bench-<date>/wts-r<round>/bench-<test-id>-cc \
  --tier trusted \
  --agent-type claude_code \
  --speak-policy always \
  --auto-wake-after-s 0 \
  --allow-spawn-burst \
  --role "<round_id> benchmark <role_kind> — execute CHARTER.md; report to @<your-id>"

# Dispatch charter via parley say (heredoc form per [[feedback_parley_say_heredoc_via_stdin]])
parley say --stdin <<EOF
@bench-cc-<test-id> execute CHARTER.md in your cwd. Primary artifact: <artifact-name>.
When done, write artifact then send 'charter_done — <1-sentence summary>' via parley say to @<your-id>.
EOF
```

**Spawn-cap discipline:** keep ≤3 concurrent CC seats. Remove finished seats with
`parley member remove --bulk <id1> <id2> <id3>` before next wave. Some role_kinds
default `can_edit=False` (docs_auditor / reviewer / blind_reviewer) — this is parley
discipline only, NOT adapter-tool-blocking; the agent can still write artifacts.

### Codex side (headless exec)

**FIREWALL FIRST (Hard Rule 7).** Strip the parley identity from the codex
process so it cannot post to / read from the live session as the orchestrator.
Either invoke via `env -u TMUX -u TMUX_PANE -u PARLEY_MEMBER_ID -u PARLEY_SESSION
codex exec …` or, in the python runner, pass a scrubbed `env=`:

```python
import os
_clean_env = {k: v for k, v in os.environ.items()
              if k not in ("TMUX", "TMUX_PANE", "PARLEY_MEMBER_ID", "PARLEY_SESSION")}
# ... then subprocess.run([...], cwd=str(ws), env=_clean_env, ...)
```

After each leg, assert `grep -c "since last delivery" <runs.jsonl> == 0`.

Codex runs in a single background python runner that processes all tests sequentially:

```python
# runner-r<round>-codex.py — adapt from /tmp/bench-2026-06-07/runner-r4-codex.py
import json, subprocess, time
from pathlib import Path

BENCH = Path("/tmp/bench-<date>")
WTS = BENCH / "wts-r<round>"
RUNS = BENCH / "runs-r<round>"
RUNS.mkdir(parents=True, exist_ok=True)

TESTS = [(test_id, role_kind, tier), ...]  # populate
TIMEOUT = 600  # 10min per test

for test_id, role_kind, tier in TESTS:
    target = RUNS / f"{test_id}-codex.json"
    if target.exists():
        continue  # idempotent
    ws = WTS / f"bench-{test_id}-codex"
    prompt = (ws / "CHARTER.md").read_text()
    start = time.time()
    proc = subprocess.run([
        "codex", "exec", "--json",
        "--dangerously-bypass-approvals-and-sandbox",
        "--skip-git-repo-check",
        "-c", "check_for_update_on_startup=false",
    ], cwd=str(ws), env=_clean_env, capture_output=True, text=True, timeout=TIMEOUT, input=prompt)  # env scrubbed per Hard Rule 7
    elapsed = time.time() - start
    # Parse JSON events from stdout, extract final_usage + agent_messages
    # See /tmp/bench-2026-06-07/runner-r4-codex.py for full parser
    target.write_text(json.dumps({
        "test_id": test_id, "adapter": "codex", "role_kind": role_kind, "tier": tier,
        "wall_clock_seconds": round(elapsed, 2),
        # ... full record shape per §7
    }, indent=2))
```

Kick off in background:

```bash
nohup python3 /tmp/bench-<date>/runner-r<round>-codex.py > /tmp/bench-<date>/runner-r<round>-codex.log 2>&1 &
```

Codex side processes ~30s-2min per test typically. Will finish faster than CC waves.

## 5. Monitor + collect

Per-test signals:

- **CC charter_done:** appears in parley chat as a `parley say` from the bench-cc-*
  seat. Pull via `parley read --since msg-<dispatch-id> --full --kind chat`.
- **Artifact present:** check `ls /tmp/bench-<date>/wts-r<round>/bench-<test-id>-cc/`.
  Sometimes the seat writes the artifact but forgets the charter_done — treat
  artifact-present as effective completion after ~5min seat-quiet.
- **Codex done:** check `tail /tmp/bench-<date>/runner-r<round>-codex.log` for
  `-> <test-id>-codex.json (exit=0, wall=Xs)`.

Wall-clock for CC: `artifact_mtime - .start_ts`. Wall-clock for codex: in the JSON
record. Heuristic PASS: artifact exists with size > 200 bytes (adjust per charter).

When wave complete (all 3 artifacts present), `parley member remove --bulk` the wave
+ spawn next wave's 3 seats.

## 6. Synthesis HTML + Telegram delivery

### Markdown synthesis

Sections in order (R1-R5 reference: `/tmp/bench-2026-06-07/SYNTHESIS-combined.md`):

1. **Headline** — total paired tests, total role_kinds, PASS/PASS ratio per adapter,
   aggregate wall-ratio.
2. **THE SPINE — per-role recommendation** — a table with columns: role_kind | paired
   tests (n) | recommendation (codex / CC / either) | why. This is the load-bearing
   output. Recommendation logic:
   - codex preferred: capability parity + codex 2×+ faster wall
   - CC preferred: only if specialized-capability evidence OR Kris durable-default
     applies
   - either: capability parity + wall-ratio < 1.5× (close pair) OR speed-dependent
     operator choice
3. **Per-round result tables** — one per round, with columns: test_id | role_kind |
   CC pass/wall | codex pass/wall | CC/codex ratio.
4. **Cumulative cross-round table** — one row per round + cumulative row.
5. **Substrate-doctrine findings** — independent of per-role. Headless-CC cap exposure,
   interactive cap-resilience, wall-clock scaling with content density, token-telemetry
   asymmetry, etc.
6. **Specialized-capability evidence by role** — qualitative reads of standout
   artifacts (sharp first-actions, rejected-alternative reasoning, etc.).
7. **Verdict** — capability + operational + mix-mode recommendation.
8. **Caveats** — n-counts per role, heuristic-vs-gold-standard, outlier flags, charter
   scope, adapter versions.
9. **Round artifacts** — paths to source JSONs + synthesis + decision-docs.

### HTML render

Use the same night-mode CSS as prior rounds. Pattern at
`/tmp/bench-2026-06-07/render_html_combined.py`:

```python
import re, sys, markdown
from pathlib import Path
sys.path.insert(0, "/tmp/bench-<date>")
import render_html  # type: ignore  (CSS module from prior round)

md_text = Path("/tmp/bench-<date>/SYNTHESIS-combined.md").read_text()
body_html = markdown.Markdown(extensions=["tables", "fenced_code", "sane_lists"]).convert(md_text)

# Wrap "THE SPINE" section as the callout
pattern = re.compile(r'(<h2>THE SPINE[^<]*</h2>)(.*?)(?=<h2>)', re.DOTALL)
body_html = pattern.sub(lambda m: f'<div class="callout">{m.group(1)}{m.group(2)}</div>\n', body_html)

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, user-scalable=yes">
  <meta name="color-scheme" content="dark">
  <title>CC-vs-Codex — Synthesis</title>
  <style>{render_html.CSS}</style>
</head>
<body><div class="container">{body_html}</div></body>
</html>
"""
Path("/tmp/bench-<date>/SYNTHESIS-combined.html").write_text(html)
```

### Telegram delivery

**Use `sendDocument` curl, NOT `parley telegram send`.** Telegram chat-body limit is
4096 chars; HTML reports exceed it. Plain-text path-to-file delivery fails on phone
(no shell access).

```bash
# Read bot config
BOT_TOKEN=$(python3 -c "import json; print(json.load(open('$HOME/.parley/secrets/telegram.json'))['bot_token'])")
CHAT_ID=$(python3 -c "import json; print(json.load(open('$HOME/.parley/secrets/telegram.json'))['chat_id'])")

# Upload HTML as Telegram document
curl -sS -F "chat_id=$CHAT_ID" \
  -F "document=@/tmp/bench-<date>/SYNTHESIS-combined.html;type=text/html" \
  -F "caption=📊 CC-vs-Codex <round_id> Synthesis (N tests / M role_kinds). Open in any browser (night-mode, mobile-friendly)." \
  "https://api.telegram.org/bot$BOT_TOKEN/sendDocument"

# Response: {"ok":true,"result":{"message_id":<n>,"document":{...}}}
```

Confirm message_id to operator via parley say after success.

## 7. Per-round JSON result shape

```json
{
  "benchmark_id": "cc-vs-codex-phase<N>-<YYYY-MM-DD>-<round_id>",
  "round": "<round_id>",
  "base_sha": "<parley-HEAD-at-dispatch>",
  "started_ts": <unix>,
  "ended_ts": <unix>,
  "tests": [
    {
      "test_id": "<id>",
      "role_kind": "<role_kind>",
      "tier": "Simple|Complex",
      "primary_artifact": "<filename>",
      "cc": {
        "pass": <bool>,
        "wall_s": <float>,
        "artifact_size_b": <int>,
        "tokens_input": <int|null>,  // null for interactive tmux CC
        "tokens_output": <int|null>,
        "quality_notes": "<1-3 sentences>",
        "self_recovery": "yes|no|n/a"
      },
      "codex": {
        "pass": <bool>,
        "wall_s": <float>,
        "artifact_size_b": <int>,
        "usage": <codex final_usage JSON | null>,
        "quality_notes": "<1-3 sentences>",
        "self_recovery": "yes|no|n/a"
      },
      "cc_over_codex": <float | null>,
      "divergence": ["<note 1>", "<note 2>"]  // optional
    }
  ],
  "summary": {
    "cc_pass_n": <int>,
    "codex_pass_n": <int>,
    "cc_wall_total_s": <float>,
    "codex_wall_total_s": <float>,
    "cc_over_codex_aggregate": <float>,
    "verdict": "<short headline>"
  }
}
```

Compiler script: see `/tmp/bench-2026-06-07/compile_r4.py` for the reference shape.

## 8. Substrate-doctrine collection

While running rounds, capture cross-cutting findings that are NOT per-role
(applicable to orchestrator design decisions). Examples observed in R1-R5:

- **Headless cap exposure:** `claude -p` from a single host hit 429 at ~9 min on R1
  phase A. Codex did not.
- **Interactive cap-resilience:** `parley member spawn --agent-type claude_code` had
  0 cap signals across 40+ invocations.
- **Wall-clock scales with content density:** denser charters (PRDs / ADRs / dense
  designs) amplify CC overhead 2-6× vs codex. Less-dense charters (simple algorithms)
  show 1-2× ratio.
- **Token telemetry asymmetric:** codex emits clean JSON usage; interactive CC does
  not (interactive tmux can't be `/context`-scraped reliably).
- **PRD-class drafting has high within-role CC variance:** R4-pm 151s vs R5-pm 839s
  = 5.5× spread for same role on different charters. Codex is more wall-clock-
  predictable for drafting-heavy work.

Include these as a section in the synthesis. Update for each new round.

## 9. Filing the cross-substrate decision-doc

If the benchmark surfaces a role_kind enum recommendation (add / deprecate / rename),
file via the `/record-decision` skill BEFORE running the cohort-implementation
follow-up.

```
/record-decision
  title: "<add/keep/deprecate> role_kind enum values per benchmark <round_id>"
  rationale: "<empirical evidence + Kris durable-default if applicable>"
  scope: "design:PARLEY-DEV-MGMT-INTEGRATION"
  options-json: <chosen-and-rejected-alternatives JSON>
  linked-msg-ids: <comma-separated parley msg-IDs: charter dispatch + ratify + LAND>
  affects: "Parley substrate enum change; implementation via @par-plan FULL-3-leg or LIGHT-single-seat cohort per @plan scope-shape ruling"
```

Reference: `docs/decisions/2026-06-08-01-add-6-parley-role-kind-enum-values-per-cc-vs-codex-r3-roles-benchmark.md`.

## 10. Cross-references

- **Worked examples (full ground-truth):** `/tmp/bench-2026-06-07/SYNTHESIS-combined.md`
  + `.html` + 5 round JSONs.
- **Charter library (24 worked charters across 22 role_kinds):**
  `/tmp/bench-2026-06-07/charters-r{3,4,5}/`.
- **Setup scripts (reference):** `/tmp/bench-2026-06-07/setup_r{4,5}.py`.
- **Codex runners (reference):** `/tmp/bench-2026-06-07/runner-r{3,4,5}-codex.py`.
- **Compilers (reference):** `/tmp/bench-2026-06-07/compile_r{4,5}.py`.
- **HTML renderer (reference):** `/tmp/bench-2026-06-07/render_html_combined.py` +
  `render_html.py` (CSS module).
- **Per-role recommendation spine (22 roles, post-R5):**
  `/tmp/bench-2026-06-07/SYNTHESIS-combined.md` §"THE SPINE".
- **WL decision-doc on the role_kind enum extension:**
  `docs/decisions/2026-06-08-01-add-6-parley-role-kind-enum-values-per-cc-vs-codex-r3-roles-benchmark.md`.

## Notes

- This skill is **parley-coupled at the SKILL layer** (Hard Rule 1 in workshop-lite
  CLAUDE.md): the recipe calls `parley member spawn` + `parley say` + `parley read` +
  the Bot API curl. The skill IS the parley coupling; the lib stays clean.
- For codex/agy invocation: read this SKILL.md, execute the bash + python steps
  inline. No special tooling required — every step is a shell command or a python
  script. Codex/agy users may want to add inline progress markers since they don't
  have the CC tool-call streaming.
- **Round naming convention:** `R<n>` for vanilla rounds; `R<n>-<descriptor>` for
  specialized rounds (e.g. `R5-roles-n2` for n=2 confirmation). Increment monotonically;
  preserve all prior round artifacts (alongside, never superseded).
- **n=1 → n=2+ uplift:** when re-running for n=2 confirmation, USE DIFFERENT CHARTER
  CONTENT (different fixture / domain). Same role_kind task shape but distinct details
  to avoid pattern memorization. Reference R5 vs R4 charters for examples.
