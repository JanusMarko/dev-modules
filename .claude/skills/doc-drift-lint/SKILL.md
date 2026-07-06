---
name: doc-drift-lint
description: Run the doc-drift lint — surface spec/design docs whose enumerated tags (e.g. "F2", "F3") have diverged from the matching code directories. Opt-in via `.claude/doc-drift-lint.toml`; warnings, never errors. Use when the user types `/doc-drift-lint` or asks to check for spec-vs-code drift.
---

# /doc-drift-lint

When the user invokes `/doc-drift-lint`, run this flow.

## What this catches

The **F1-spec-§6 class-mismatch pattern**: a spec or design doc enumerates a structural set (e.g. `F1 = login screen`, `F2 = ...`, `F3 = ...`) that the actual code directory layout (e.g. `web/components/screens/F1/`, `F2/`, `F4/`) has silently diverged from — either a spec tag without a matching code dir, or a code dir without a matching spec entry. Charter: `docs/inbox/2026-05-23-stop-stopping-priority-backlog.md` item 3.

The lint is **opt-in**: it runs only when `<repo>/.claude/doc-drift-lint.toml` exists. Absent config => silent skip.

## 1. Confirm opt-in config exists

```bash
ls -la .claude/doc-drift-lint.toml
```

If the file is absent, ask the user whether to create one. The `EXAMPLE-CONFIG.toml` next to this SKILL.md is the annotated reference.

## 2. Run the lint

From the repo root:

```bash
.venv/bin/python3 .claude/scripts/dev-mgmt/cli.py validate --repo-root .
```

If the repo doesn't have a `.venv/`, fall back to `python3` (PyYAML must be available).

This runs the **full** advisory validator pass (sprint folder coherence + INDEX coherence + frontmatter + cross-links + status-transition + **doc-drift**). The doc-drift portion only runs when `--mtime-cutoff` is **not** set (i.e. on the full on-demand pass, not the Stop-hook fast path).

To run only the doc-drift check programmatically:

```bash
.venv/bin/python3 -c "
import sys; sys.path.insert(0, '.claude/scripts/dev-mgmt')
import doc_drift_lint
for w in doc_drift_lint.run_doc_drift_checks('.'):
    print(f'[{w.category}] {w.path}: {w.message}')
"
```

## 3. Read the output

Warnings are emitted to stderr in the standard `[category] path: message` shape:

```
[doc_drift_lint] docs/design/F1-spec.md:42: rule 'maxai-F-screens': spec tag 'F4' has no matching code dir at web/components/screens/F4/
[doc_drift_lint] web/components/screens/F7/: rule 'maxai-F-screens': code dir 'F7' has no matching spec tag in docs/design/F*-spec*.md
```

Two warning categories:

- `doc_drift_lint` — an actual drift detection (a tag in one side without the other side present)
- `doc_drift_lint_config` — the config file itself has a problem (malformed TOML, bad rule, missing required field). Other rules still run; this one is skipped.

## 4. Report back

Tell the user:

- the number of warnings emitted, split by category (drift vs config)
- the first 5-10 individual warnings (full list if ≤10)
- where the config file lives (`.claude/doc-drift-lint.toml`) if they want to tune the rules
- the `--strict` flag if they want CI to fail on drift: `cli.py validate --strict`

## Config schema (quick reference)

```toml
schema_version = 1

[[rules]]
name = "maxai-F-screens"                           # provenance label
spec_glob = "docs/design/F*-spec*.md"              # docs to scan
identifier_pattern = '^F(\d+)\b'                   # tag regex; group(1) is the tag
code_dir_template = "web/components/screens/F{n}/" # {n} = the tag
mode = "bidirectional"                             # default; or spec_only | code_only | report_only

[[rules]]
name = "decision-numbering"
spec_glob = "docs/design/LIGHTWEIGHT-DEV-MGMT-SYSTEM.md"
identifier_pattern = '\bD(\d+)\b'
mode = "report_only"                               # no 1:1 code dir; just enumerate
```

Modes:

- `bidirectional` (default) — warn for spec tags without code dirs AND code dirs without spec tags
- `spec_only` — only flag spec tags missing from code (i.e. spec is canonical)
- `code_only` — only flag code dirs missing from spec (i.e. code is canonical, spec must catch up)
- `report_only` — no drift check; only emit a config warning if the glob matched zero tags (sanity check that the rule is wired right)

The `{n}` token in `code_dir_template` is substituted with the matched tag string. If `identifier_pattern` has a capture group, group(1) is the tag; otherwise the entire regex match is the tag.

## Hard rules honored

- **Hard Rule 1** (parley-agnostic at lib tier): `doc_drift_lint.py` never imports or shells parley.
- **Hard Rule 5** (advisory by default): warnings only; `--strict` is the sole path to non-zero exit.
- **Hard Rule 6** (hooks never block): the Stop-hook integration runs only on the on-demand full pass, not the per-Stop fast subset; the hook itself never blocks.

## See also

- Module: `.claude/scripts/dev-mgmt/doc_drift_lint.py`
- Example config: `EXAMPLE-CONFIG.toml` (next to this SKILL.md)
- Runbook: `docs/inbox/2026-05-23-doc-drift-lint-runbook.md`
- Charter: `docs/inbox/2026-05-23-stop-stopping-priority-backlog.md` item 3
