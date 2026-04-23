# dev-modules

A lightweight per-repo **service discovery** layer for dev-tool integrations.

Any tool that wants to be discoverable by other tools drops a manifest at
`.modules/<name>/module.toml` in the repo root. Other tools list `.modules/`
to see who else is installed and adapt their behavior.

---

## Why this exists

Multi-tool dev ecosystems (coding agents like Claude Code / Codex, plus
supporting systems — notification bridges, workflow journals, web UIs)
keep running into the same integration problem:

- **Tool A** wants to do something nice when **Tool B** is present, but
  shouldn't require B to be installed.
- **Tool B** has no way to advertise its presence or its capabilities
  without forcing a hard dependency or building a custom plugin system.
- Each pair of tools reinvents an opt-out flag, a registry, or a config
  convention — and they conflict.

Concrete case this was built for:

- `workshop` keeps a per-repo journal of decisions and skills.
- `ccweb` is a web UI for Claude Code sessions.
- `telegram` is a notification bridge.
- A "present me options" skill wants to notify via Telegram **only if
  the user uses Telegram**, surface in a ccweb grid **only if ccweb is
  running**, and record to workshop's journal **only if workshop is
  installed**. Without a shared convention, every skill grows three
  feature flags and hardcoded paths.

`dev-modules` is the smallest shared convention that solves this:
tools advertise themselves via `.modules/<name>/module.toml`; consumers
check presence + capabilities before wiring in the integration; absence
is graceful by default.

## What it is

A shared convention — not a framework. Three rules:

1. **Presence advertises.** `.modules/<name>/module.toml` means `<name>`
   is installed in this repo.
2. **Consumers are responsible.** If tool A wants to respond to tool B
   being present, A reads `.modules/` and acts. B doesn't know A exists.
3. **Graceful absence.** Nothing ever errors because a module isn't
   listed — callers just skip the integration.

## What it isn't

- Not a package manager — tools install themselves; `.modules/` only
  advertises.
- Not a config store — module config lives in each tool's own directory
  (`.claude/<name>/`, `~/.config/<name>/`, …).
- Not an event bus — consumers call producers' APIs directly.
- Not a plugin loader — code must already be installed; the manifest
  only gates whether it runs.

---

## Quick example

**Producer** — the `telegram` tool registers itself during install:

```bash
cat <<'EOF' | scripts/register.sh telegram
schema_version = 1
name = "telegram"
version = "1.2.0"
description = "Telegram bot notifications"
capabilities = ["telegram.notify", "telegram.notify.inline_buttons"]
EOF
```

This writes `.modules/telegram/module.toml` atomically, creating
`.modules/` if needed.

**Consumer** — the `option-grid` skill uses Telegram only when it's
present:

```python
from dev_modules import is_installed

def present_grid(items):
    write_grid_file(items)
    if is_installed("telegram"):
        from telegram_bridge import notify
        notify("Grid ready for review.")
```

No Telegram? The skill runs exactly the same, minus the notification.
No exceptions, no config flags, no branching dead code.

## Layout

```
<repo-root>/
  .modules/
    workshop/module.toml     # workshop is installed here
    ccweb/module.toml
    telegram/module.toml
```

See [SPEC.md](SPEC.md) for the full `module.toml` schema and discovery
rules.

---

## Repo structure

```
dev-modules/
  README.md               # this file
  SPEC.md                 # the module.toml schema
  examples/               # canonical module.toml
  python/                 # pip-installable reader library
    dev_modules/          # package source
    tests/                # pytest suite
    pyproject.toml
  typescript/             # npm-publishable reader library
    src/                  # TS source
    tsconfig.json
    package.json
  scripts/                # install helpers (bash)
    register.sh           # atomic write of a module manifest
    unregister.sh         # remove a module manifest
```

---

## Installing the reader library

The reader library is what **consumers** (tools that want to adapt to
other tools' presence) use at runtime to query `.modules/`. It ships as
a Python package and a TypeScript package; pick whichever your tool is
written in.

### Python

From a published release (once available on PyPI):

```bash
pip install dev-modules
```

From the git repo (for now, and for local development):

```bash
# Direct from GitHub
pip install "git+https://github.com/JanusMarko/dev-modules.git#subdirectory=python"

# Or if you've cloned locally
git clone https://github.com/JanusMarko/dev-modules.git
pip install -e ./dev-modules/python
```

Import:

```python
from dev_modules import installed_modules, is_installed, has_capability
```

### TypeScript / Node

From a published release (once available on npm):

```bash
npm install dev-modules
```

From the git repo:

```bash
# Add as a git dependency in package.json
npm install "github:JanusMarko/dev-modules#main:typescript"

# Or local editable install
git clone https://github.com/JanusMarko/dev-modules.git
cd dev-modules/typescript && npm install   # builds dist/ via `prepare`
```

Import:

```ts
import { installedModules, isInstalled, hasCapability } from "dev-modules";
```

---

## Deploying dev-modules into an existing repo

You don't "install" dev-modules into a repo in any heavyweight sense —
the only thing that lives in the repo itself is the `.modules/`
directory, which tools create on-demand. The actual reader library is
installed into each consuming **tool's** environment, not the repo.

Typical adoption steps for an existing codebase:

### 1. As a tool maintainer (producer side)

If your tool wants to be discoverable, add a step to your installer
that registers your manifest:

```bash
# Somewhere in your tool's install / setup script:
cat <<'EOF' | /path/to/dev-modules/scripts/register.sh mytool
schema_version = 1
name = "mytool"
version = "0.3.1"
description = "Brief one-line description"
capabilities = ["mytool.feature1", "mytool.feature2"]
EOF
```

Or, if you'd rather not depend on the script, write the file directly
(must be atomic to avoid torn reads):

```bash
mkdir -p .modules/mytool
cat > .modules/mytool/module.toml.tmp <<'EOF'
schema_version = 1
name = "mytool"
version = "0.3.1"
capabilities = ["mytool.feature1"]
EOF
mv .modules/mytool/module.toml.tmp .modules/mytool/module.toml
```

On uninstall, remove the directory:

```bash
rm -rf .modules/mytool
```

### 2. As a tool maintainer (consumer side)

Add the reader library as a dependency of your tool:

```toml
# pyproject.toml
dependencies = [
  "dev-modules >= 0.1.0",
]
```

Then check for other modules at the points where you'd conditionally
integrate:

```python
from dev_modules import is_installed, has_capability

def on_grid_submitted(grid_result):
    save_result(grid_result)
    if has_capability("telegram", "telegram.notify"):
        send_telegram_notification(grid_result)
    if is_installed("workshop"):
        append_to_journal(grid_result)
```

### 3. As a repo user

You don't need to do anything. `.modules/` appears when the first tool
installs itself, grows as more tools register, and shrinks when they
uninstall. You can inspect it with `ls .modules/` to see what's
registered.

If you want a module-aware tool to **skip** a specific integration,
remove the target module's entry:

```bash
rm -rf .modules/telegram   # ccweb and skills stop trying to notify
```

No tool should break from a missing module.

---

## Development

### Python

```bash
cd python
pip install -e .
pip install pytest
pytest tests/ -q
```

### TypeScript

```bash
cd typescript
npm install       # `prepare` builds dist/ automatically
npm run typecheck
npm run build     # emits dist/
```

### Updating the spec

If you change `SPEC.md`, update:

- `python/dev_modules/schema.py` (`SCHEMA_VERSION`, validation in
  `parse_manifest`)
- `typescript/src/index.ts` (`SCHEMA_VERSION`, validation in
  `parseManifest`)
- `python/tests/test_reader.py` (add coverage)

If the change is backward-compatible (new optional field), keep
`schema_version = 1`. Breaking changes bump `schema_version`; readers
must refuse unknown versions.

---

## Status

**v0.1.0** — initial scaffold. The schema is intentionally tiny and
should be stable; watch for the first real consumers (workshop, ccweb,
telegram bridge) before locking the API.

## License

MIT — see the `license` field in `python/pyproject.toml`. A full
`LICENSE` file will be added with the first tagged release.

## Spec

See [SPEC.md](SPEC.md) for the full manifest schema, discovery rules,
capability naming conventions, and non-goals.
