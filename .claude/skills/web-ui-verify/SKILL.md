---
name: web-ui-verify
description: |
  Playwright headless-load smoke for web-UI bundles — the substrate-mandated
  cert axis every web-UI LAND charter must include. This skill is the
  *discovery surface*, not the recipe; the recipe lives at
  `bin/web-ui-verify` and is invokable by any agent class (cc / codex /
  antigravity / subprocess) via shell-out. Use when filing or executing a
  charter that lands a web-UI dist-artifact, or when probing why a deployed
  bundle white-screens / errors in the browser.
---

# web-ui-verify — substrate-mandated headless-load smoke

**The recipe is the script at `bin/web-ui-verify`. This SKILL.md is documentation only.**

Per doctrine [`docs/decisions/2026-06-07-01-playwright-headless-load-smoke-verification-required-for-every-web-ui-land.md`](../../../docs/decisions/2026-06-07-01-playwright-headless-load-smoke-verification-required-for-every-web-ui-land.md), every web-UI LAND charter MUST include a playwright headless-load smoke as a cert axis. This skill records the binding rule + invocation contract + cert-envelope shape so authors paste a consistent block into their charters and so any agent class can drive the recipe identically.

## Why this exists

The 2026-06-07 ccweb blank-screen incident shipped a broken bundle to the user's browser (two stacked JS bugs: `BUILD_ID` undefined and `restartBySid` undefined). Neither bug was caught by anything other than the user's eyeballs. A 30-second headless-Chromium load with uncaught-error capture would have caught both. The cohort PW dispatch promoted that 30-second smoke from "good idea" to substrate-rule.

## The binding rule

> Every web-UI LAND charter that produces a dist-artifact (or that modifies code which becomes a dist-artifact via downstream build) MUST include the three cert axes below. Either the charter author embeds them directly in §6, or they paste the snippet at [`docs/.templates/charter-template-snippet-web-ui-verify.md`](../../../docs/.templates/charter-template-snippet-web-ui-verify.md).

This rule binds the *charter*, not the recipe — the recipe is a stable command surface; charters reference it by name.

## Invocation contract

```
bin/web-ui-verify <url> [--expected-no-error <regex>...] [--timeout <seconds>] [--wait-network-idle]
```

The recipe is **pure python** (`#!/usr/bin/env python3`) with a venv-aware re-exec at the top. Calling it via subprocess from ANY context (CC bash tool / codex shell-out / antigravity / a plain shell session / a CI workflow) is identical:

```bash
workshop-lite/bin/web-ui-verify https://preview.example.com/foo
echo $?   # 0 = clean, 1 = uncaught errors, 2 = could not load OR playwright missing
```

**Exit codes**:

| Code | Meaning |
|---|---|
| `0` | Bundle loaded cleanly. No uncaught console errors, no `pageerror` events, no unhandled promise rejections, no 4xx/5xx responses. |
| `1` | Uncaught errors fired. Each error printed to stderr one per line (machine-parseable: `[console.error]` / `[pageerror]` / `[network <status>]` / `[unhandledrejection]` prefix tags), followed by a `[summary] N uncaught error(s)` count line. |
| `2` | Bundle could not be loaded (timeout, connection refused, etc.) OR the `playwright` python package is not installed. Diagnostic printed to stderr; when playwright is missing the diagnostic includes the install command path. |

**Captured signals** (per charter §2 Sub-fix 1):

- Console errors (`msg.type == "error"`)
- Uncaught exceptions (`pageerror` event)
- Unhandled promise rejections (window-level `unhandledrejection` listener, captured via init script and surfaced as a `console.error` so the same handler picks it up)
- Failed network requests (HTTP status ≥ 400)

**Tolerations**: `--expected-no-error <regex>` (repeatable; Python `re` syntax) — matching lines are filtered out of the failure set. A 404 on a sub-resource typically surfaces twice (once as `[network 404] <url>` and once as `[console.error] Failed to load resource: ...`); tolerate it by passing **two** patterns, one per prefix.

## Install prerequisites

The recipe uses **playwright-python** (the python package), NOT the JS CLI at `/usr/bin/playwright` (which is `@playwright/test` for node and unrelated). The python package is **not** part of the baseline workshop-lite adopt — it's an opt-in extra:

```bash
# In any workshop-lite-adopted consumer repo
python3 -m venv .venv  # if absent
.venv/bin/pip install -e ".[web-ui-verify]"
.venv/bin/playwright install chromium   # downloads ~200MB browser binary
```

The recipe preflights `import playwright` on every run; if missing it prints the install command rooted at the consumer's project root and exits 2. So agents always get an actionable error rather than a stack trace.

## Cert envelope a web-UI LAND charter must include

Paste these three axes into your charter §6 (or paste the full snippet at [`docs/.templates/charter-template-snippet-web-ui-verify.md`](../../../docs/.templates/charter-template-snippet-web-ui-verify.md)):

1. **web-ui-verify-recipe-PASSES-on-working-bundle**: `bin/web-ui-verify <preview-url>` exits 0 against the current working bundle.
2. **web-ui-verify-recipe-FAILS-on-broken-bundle**: `bin/web-ui-verify <preview-url>` exits 1 against a deliberately-broken bundle (e.g., `git stash` the fix; run; restore).
3. **cross-agent-class-invocation-parity**: invocation of `bin/web-ui-verify <url>` by a non-CC agent (codex or antigravity, or a direct subprocess simulation) produces the same exit code + stderr shape as CC.

The three axes together prove: (a) the recipe doesn't false-PASS, (b) the recipe doesn't false-FAIL, (c) the recipe is agent-class-agnostic so the rule binds across the substrate uniformly.

## What this skill is NOT

- **NOT a CC-only convenience**. The recipe is a python script invokable from any subprocess. CC has no privileged path. The rule binds all agent classes.
- **NOT a visual-regression / screenshot diff tool**. v1 is headless-load + uncaught-error capture only.
- **NOT a mobile / responsive smoke**. Desktop Chromium only for v1.
- **NOT a PostToolUse hook**. The hook variant is a deferred follow-up (charter §3 out-of-scope), not part of cohort PW.

## See also

- [`bin/web-ui-verify`](../../../bin/web-ui-verify) — the recipe (source of truth).
- [`docs/decisions/2026-06-07-01-playwright-headless-load-smoke-verification-required-for-every-web-ui-land.md`](../../../docs/decisions/2026-06-07-01-playwright-headless-load-smoke-verification-required-for-every-web-ui-land.md) — doctrine decision establishing the rule.
- [`docs/dispatches/2026-06-07-01-playwright-web-ui-verify-substrate-fix.md`](../../../docs/dispatches/2026-06-07-01-playwright-web-ui-verify-substrate-fix.md) — standing dispatch tracking enforcement across consumer repos.
- [`docs/.templates/charter-template-snippet-web-ui-verify.md`](../../../docs/.templates/charter-template-snippet-web-ui-verify.md) — paste-ready snippet for charter §6 cert envelopes.
- [`docs/inbox/2026-06-07-cohort-PW-playwright-web-ui-verify-charter.md`](../../../docs/inbox/2026-06-07-cohort-PW-playwright-web-ui-verify-charter.md) — provenance charter for the substrate-fix that landed this skill + recipe.
