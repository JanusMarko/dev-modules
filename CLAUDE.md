# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

`dev-modules` is a **specification plus two parallel reader libraries** (Python and TypeScript) for a per-repo service-discovery convention. Tools in a repo advertise themselves by writing `.modules/<name>/module.toml`; other tools enumerate that directory to adapt behavior. There is no runtime, no event bus, no plugin loader — just a file-based convention.

Because it's a convention, `SPEC.md` is the canonical source of truth. The two reader libraries exist to make the convention ergonomic to consume; they MUST agree on schema/validation behavior.

## The two parallel implementations

The Python (`python/dev_modules/`) and TypeScript (`typescript/src/index.ts`) libraries intentionally mirror each other. They expose the same three-function surface:

- `installed_modules()` / `installedModules()` — enumerate; silently skip invalid manifests
- `is_installed(name)` / `isInstalled(name)` — presence check
- `has_capability(name, cap)` / `hasCapability(name, cap)` — feature check

Plus `load_module()` / `loadModule()` which raises on invalid manifests (use for diagnostics, not enumeration). **Any change to validation rules, error classes, or the public API surface must be made to both implementations in the same PR** — drift between them breaks the convention.

The `installed_modules()` enumeration path is deliberately lenient (skips bad manifests); the `load_module()` single-item path is strict. Preserve this dual-path design.

## Spec-change workflow

When `SPEC.md` changes, four files must be updated in lockstep (called out in `README.md` under "Updating the spec"):

1. `SPEC.md` itself
2. `python/dev_modules/schema.py` — `SCHEMA_VERSION` const + validation in `parse_manifest`
3. `typescript/src/index.ts` — `SCHEMA_VERSION` const + validation in `parseManifest`
4. `python/tests/test_reader.py` — add coverage for the new rule

Backward-compatible changes (new optional fields) keep `schema_version = 1`. Breaking changes bump `schema_version`; readers MUST refuse unknown versions (returning "not installed" is the safe default — do not guess).

## Commands

### Python

```bash
cd python
pip install -e .
pip install pytest
pytest tests/ -q              # full suite
pytest tests/test_reader.py::test_is_installed_and_has_capability -q   # single test
```

Lint config is in `python/pyproject.toml` under `[tool.ruff]` (line-length 100, select `E F I UP B`).

### TypeScript

```bash
cd typescript
npm install       # `prepare` script auto-builds dist/
npm run typecheck # tsc --noEmit
npm run build     # emit dist/
```

Note: `npm test` runs `node --test dist/*.test.js` but there are no TS tests yet — test coverage currently lives entirely in the Python suite.

### Manifest register/unregister (shell)

```bash
cat module.toml | scripts/register.sh <name>   # atomic write (tmp file + rename)
scripts/unregister.sh <name>
```

Both scripts walk upward from `$PWD` to find an existing `.modules/` directory; `register.sh` creates one in `$PWD` if none is found. Atomicity matters — concurrent enumeration must never see a torn file.

## Key invariants to preserve

- **Graceful absence.** No consumer function ever raises because a module isn't installed. Missing `.modules/` → empty result. Invalid manifest during enumeration → skip silently.
- **Directory name == manifest `name` field.** `parse_manifest` rejects mismatches; this is load-bearing for discovery integrity.
- **Atomic writes.** Install = write to `.module.toml.XXXXXX` temp file, then `mv` into place. Never write `module.toml` directly.
- **Discovery walks upward** from cwd to find the nearest ancestor `.modules/` — matches git's behavior for repo-root detection.

## MODULE_AUTHOR_GUIDE.md

This is a standalone task brief intended to be handed to Claude Code running in a **different** repository (one that wants to become a dev-modules module). It is not guidance for working in *this* repo. Don't treat it as project documentation to extend — treat it as a deliverable whose audience is an agent elsewhere.

<!-- BEGIN parley-managed -->
## Parley membership

When you are a member of a parley session, your per-member context lives at
`<repo>/.parley/<sid>/members/<window-id>/instructions.md` (sidecar-managed).
Run `parley whoami` to discover your session + member id + tier + policy.

The full participation reference is the project skill at
`<repo>/.claude/skills/parley/SKILL.md`. Claude Code auto-loads project
skills on session start.

**Nudge-and-pull delivery**: parley does NOT paste chat record bodies into
your pane. When new content arrives you receive a short NUDGE like
`[parley · 3 new for @<id>] run parley read --since msg-abc`. Run the
printed `parley read` command (a bash tool call) to fetch content; the
bash result is your window into the chat. Reply via `parley say`.
<!-- END parley-managed -->

<!-- workshop-lite-start -->

## Workshop-Lite substrate

This repository carries the workshop-lite dev-management substrate
(`.claude/scripts/dev-mgmt/` helper lib + `.claude/skills/` skills +
`.claude/hooks/` hooks + `docs/conventions/` Tier-1 rules +
`docs/.templates/` entity templates + `bin/` entry-point shims).
Refreshed via `wl install-workshop-lite-content --target <this-repo>`.

### Cross-session gates and HALT.md

**Cross-session gates.** Before any non-trivial work (LAND, push,
schema change, cross-repo substrate sync, etc.) check `docs/gates/`.
If any gate has `status: open`, respect its `what_you_cannot_do`
list. Surface to the value in `gated_by:` if you need to override or
believe the gate is stale. If a gate is past its `ttl_until` and you
can't reach the gater, surface to your operator. Discovery is by-
convention only — the substrate does not auto-enforce; the discipline
is yours. See `docs/design/LIGHTWEIGHT-DEV-MGMT-SYSTEM.md` §6 for the
schema.

**HALT.md.** If you reach a state where you cannot make progress — an
unresolvable gate, an environment you can't fix, a recurring failure
you can't diagnose, ambiguous scope you can't disambiguate — write a
top-level `HALT.md` describing your state (using the frontmatter shape
in `docs/.templates/halt.md`), print
`HALT.md WRITTEN - AGENT HALTED, NEEDS OPERATOR` to stdout, and STOP.
Do not retry. Do not loop. Wait until either (a) the `HALT.md` file
is deleted, or (b) an operator types "continue" in your pane.

### Reference

- Comprehensive design: `docs/design/LIGHTWEIGHT-DEV-MGMT-SYSTEM.md`
  (refreshed from the workshop-lite upstream as needed)
- Tier-1 conventions index: `docs/conventions/INDEX.md`
- Entity templates: `docs/.templates/`
- Bootstrap deps: `pip install -r .claude/scripts/dev-mgmt/requirements-workshop-lite.txt`

<!-- workshop-lite-end -->
