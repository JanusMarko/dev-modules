<!--
charter-template-snippet-web-ui-verify.md — paste-ready Web-UI verification
section for any charter whose LAND produces or modifies a web-UI dist-artifact.

Source of truth: docs/decisions/2026-06-07-01-playwright-headless-load-smoke-
verification-required-for-every-web-ui-land.md (cohort PW substrate-fix).

USAGE: copy the body below (everything beneath the `## Web-UI verification`
header) into your charter §6 cert envelope. Edit `<preview-url>` and the
broken-bundle reproducer text to match your specific LAND surface. The three
cert axes are mandatory; the invocation pattern at the bottom is informational.
-->

## Web-UI verification (REQUIRED for any LAND touching web-UI dist-artifact-producing code)

Per doctrine [`docs/decisions/2026-06-07-01-playwright-headless-load-smoke-verification-required-for-every-web-ui-land.md`](../decisions/2026-06-07-01-playwright-headless-load-smoke-verification-required-for-every-web-ui-land.md), every web-UI LAND charter MUST include playwright headless-load smoke as a cert axis.

Cert axes (mandatory; paste into your charter §6):

- **web-ui-verify-recipe-PASSES-on-working-bundle**: `bin/web-ui-verify <preview-url>` exits 0 against the current working bundle.
- **web-ui-verify-recipe-FAILS-on-broken-bundle**: `bin/web-ui-verify <preview-url>` exits 1 against a deliberately-broken bundle (e.g., `git stash` the fix; rebuild; run the recipe; `git stash pop`).
- **cross-agent-class-invocation-parity**: invocation of `bin/web-ui-verify <url>` by a non-CC agent (codex or antigravity, or a direct subprocess simulation that mimics codex's env-less invocation pattern) produces the same exit code + stderr shape as CC.

Invocation pattern (paste into the builder / tester chunk):

```bash
workshop-lite/bin/web-ui-verify <url> [--expected-no-error <regex>] [--timeout <seconds>] [--wait-network-idle]
```

Exit codes: `0` = clean, `1` = uncaught errors (one error per stderr line + summary count), `2` = could-not-load or playwright-not-installed (install hint printed when missing).

Install prerequisite (consumer repos that opt into web-UI verification):

```bash
.venv/bin/pip install -e ".[web-ui-verify]"
.venv/bin/playwright install chromium
```

The `web-ui-verify` extra is opt-in (not part of baseline workshop-lite adopt) because the Chromium download is ~200MB. Repos that produce web-UI artifacts pay the install cost once; repos that don't are unaffected.

See [`.claude/skills/web-ui-verify/SKILL.md`](../../.claude/skills/web-ui-verify/SKILL.md) for the full invocation contract, captured-signal list, toleration discipline, and rationale.
