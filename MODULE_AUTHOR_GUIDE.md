# Module author guide: turning a repo into a dev-modules module

> This document is written as a task brief you can hand to Claude Code
> (or any other coding agent) in a repository you want to make
> discoverable via `dev-modules`. Read the whole thing first, then
> confirm scope with the user before implementing.

## Task

Teach the tool in this repository to participate in the `dev-modules`
service-discovery convention:

1. Advertise its presence to other tools by writing a manifest file
   at `.modules/<name>/module.toml` in whatever repository the tool is
   installed into.
2. Remove that manifest when the tool is uninstalled or disabled.
3. (Optional) React to the presence of other modules at runtime by
   reading `.modules/` and adapting behavior — never hard-depending
   on them.

The full spec lives at <https://github.com/JanusMarko/dev-modules>.
You do not need to clone it; everything you need is in this document.

## Before you start — confirm with the user

Ask before implementing:

1. **Module name.** Lowercase, `[a-z][a-z0-9-]*`. Usually matches the
   tool's binary / package name. Must be globally distinct — don't
   pick generic words like `utils`.
2. **Capabilities to advertise.** Namespaced features other tools
   could feature-detect — `<name>.notify`, `<name>.journal.read`,
   `<name>.ui.sidebar`, etc. If the tool has no obviously
   feature-detectable surface, an empty list is fine; capabilities
   can be added later.
3. **Where registration should be wired in.** Installer script?
   `pyproject.toml` post-install hook? A dedicated `mytool register`
   subcommand? First-run auto-register? This depends on how the tool
   is normally installed into a repo.
4. **Whether this tool is also a consumer.** Does it want to
   integrate with other modules (Telegram notifications, workshop
   journal, ccweb UI hooks, …)? If yes, it also needs to depend on
   the `dev-modules` reader library.

Do not guess these — the user has context on the tool's purpose and
ecosystem that this document does not.

## What dev-modules is

A shared convention, not a framework. The rules:

- **Presence advertises.** `<repo>/.modules/<name>/module.toml` means
  the tool `<name>` is installed in that repo.
- **Consumers adapt.** Tools that want to integrate with others read
  `.modules/` and act on what they find. The advertising tool does
  not need to know who is listening.
- **Graceful absence.** A consumer whose integration target is not
  present MUST silently skip the integration. No exceptions, no
  warnings, no hard errors.

What dev-modules is NOT:

- Not a package manager — your tool installs itself; `.modules/` only
  advertises the result.
- Not a config store — real config lives in your tool's own
  directory (`.claude/<name>/`, `~/.config/<name>/`, etc.).
- Not an event bus — consumers call producers' public APIs directly.
- Not a plugin loader — code must already be present; `.modules/`
  only gates whether it runs.

## The manifest schema

One file per module at `<repo>/.modules/<name>/module.toml`:

```toml
schema_version = 1                     # REQUIRED; integer, currently 1
name = "<name>"                        # REQUIRED; must match directory name
version = "<your-version-string>"      # REQUIRED; display/debug only
description = "<one line, optional>"   # OPTIONAL
capabilities = [                       # OPTIONAL
  "<name>.<feature>",
  "<name>.<feature>.<sub-feature>",
]

[config]                               # OPTIONAL; free-form pass-through
# module-specific settings; dev-modules does not interpret this
```

Rules:

- `name` MUST equal the parent directory name.
- Capabilities MUST be namespaced by your module name. Do not
  advertise capabilities in another module's namespace.
- No secrets in the manifest — it's readable by anything in the repo.
- Use `[config]` sparingly; most config belongs elsewhere.

## Implementation steps

### Step 1 — Survey the repo

Understand:

- What language the tool is written in.
- How it's typically installed into a user's repository (CLI init,
  package post-install, manual setup, etc.).
- Whether it already has an install/uninstall path, or you'll need
  to add one.
- Whether it already interacts with other tools (will become a
  consumer case) or is standalone (producer-only for now).

### Step 2 — Write the registration logic

Register means: atomically write the manifest to
`<target-repo>/.modules/<name>/module.toml`. Atomic = write to a
temp file in the same directory, then rename, so readers never see a
partial file.

Pick the language matching your tool. Adapt if it's a language not
shown here — the logic is identical.

**Bash:**

```bash
register_module() {
  local target_repo="$1"
  local dir="$target_repo/.modules/<name>"
  mkdir -p "$dir"
  local tmp
  tmp="$(mktemp "$dir/.module.toml.XXXXXX")"
  cat > "$tmp" <<'EOF'
schema_version = 1
name = "<name>"
version = "<version>"
description = "<one line>"
capabilities = ["<name>.<feature>"]
EOF
  mv -f "$tmp" "$dir/module.toml"
}
```

**Python:**

```python
from pathlib import Path

def register_module(target_repo: Path, version: str) -> None:
    mdir = target_repo / ".modules" / "<name>"
    mdir.mkdir(parents=True, exist_ok=True)
    body = f'''\
schema_version = 1
name = "<name>"
version = "{version}"
description = "<one line>"
capabilities = ["<name>.<feature>"]
'''
    tmp = mdir / ".module.toml.tmp"
    tmp.write_text(body)
    tmp.replace(mdir / "module.toml")
```

**Node / TypeScript:**

```ts
import { mkdirSync, writeFileSync, renameSync } from "node:fs";
import { join } from "node:path";

export function registerModule(targetRepo: string, version: string): void {
  const dir = join(targetRepo, ".modules", "<name>");
  mkdirSync(dir, { recursive: true });
  const body = `schema_version = 1
name = "<name>"
version = "${version}"
description = "<one line>"
capabilities = ["<name>.<feature>"]
`;
  const tmp = join(dir, ".module.toml.tmp");
  writeFileSync(tmp, body);
  renameSync(tmp, join(dir, "module.toml"));
}
```

### Step 3 — Wire registration into the install path

Locate where the tool does per-repo setup and call the registration
function there. Examples:

- If the tool has `mytool init` — call `register_module` at the end
  of init.
- If the tool uses a setup script — append the registration at the
  end.
- If the tool has no per-repo setup, add a new subcommand like
  `mytool register` or `mytool enable` that the user runs once per
  repo.

Keep registration idempotent: running it multiple times must be
safe. The atomic-rename pattern already gives you this — repeated
writes just overwrite the manifest with the same content.

### Step 4 — Add an uninstall / disable step

Provide a way to unregister:

```bash
rm -rf "$target_repo/.modules/<name>"
```

```python
import shutil
shutil.rmtree(target_repo / ".modules" / "<name>", ignore_errors=True)
```

Do NOT remove the parent `.modules/` directory — it's shared.

### Step 5 — (If applicable) Become a consumer

Only do this if the tool wants to integrate with other modules. If
the tool is purely a producer for now, skip this step.

Add the reader library as a runtime dependency.

**Python** — in `pyproject.toml` / `requirements.txt`:

```toml
dependencies = [
  "dev-modules >= 0.1.0",  # once published to PyPI
]
```

For now (no PyPI release yet), install from GitHub:

```bash
pip install "git+https://github.com/JanusMarko/dev-modules.git#subdirectory=python"
```

Then feature-gate integrations:

```python
from dev_modules import is_installed, has_capability

def on_something_happens(payload):
    save_locally(payload)
    if has_capability("telegram", "telegram.notify"):
        # Only imported/called when telegram is registered here.
        from telegram_bridge import notify
        notify(payload.summary)
    if is_installed("workshop"):
        append_to_workshop_journal(payload)
```

**TypeScript / Node** — in `package.json`:

```json
{
  "dependencies": {
    "dev-modules": "github:JanusMarko/dev-modules#main:typescript"
  }
}
```

```ts
import { isInstalled, hasCapability } from "dev-modules";

if (hasCapability("telegram", "telegram.notify")) {
  // ...
}
```

Rules for consumers:

- Always check capability, not just presence, if you depend on a
  specific feature.
- Never raise / crash if a module is absent. Silent skip is the
  contract.
- Don't call into the reader library in hot paths — cache the result
  if you call it frequently.

### Worked example: integrating with another module (parley + workshop-lite)

Concrete walk-through using the parley + workshop-lite module pair.
Use this as a template for any "consumer of another module"
integration. The pattern generalizes — substitute your own module
names.

**Scenario.** Your tool wants to opt into behavior when parley is also
installed in the target repo — specifically, to:

1. Detect at SessionStart whether the current CC session is a parley
   member, and chain `parley resume <sid>` + `cat
   .parley/<sid>/members/<wid>/instructions.md` into the SessionStart
   context.
2. Record cross-system decision pointers — when your tool's records
   touch a parley conversation, both sides carry cross-references.
3. Coexist cleanly when parley is absent (the Hard Rule: never break
   a parley-less install).

**1. Presence and capability checks.**

From a shell hook:

```bash
if command -v parley >/dev/null 2>&1; then
    parley unread
fi
```

`command -v` is the simplest current-implementation check. The
canonical-going-forward check is `is_installed("parley")` via the
dev-modules reader (small shell wrapper around the Python lib, or a
`dev-modules` CLI). The shell-only path stays valid as a fallback.

From a Python consumer:

```python
import json
import subprocess
from dev_modules import has_capability

if has_capability("parley", "parley.members.read"):
    # Shell out to parley's canonical CLI surface (JSON output).
    # Survives parley source-layout changes + doesn't require
    # importing parley as a Python package.
    result = subprocess.run(
        ["parley", "members", "--session", active_sid, "--json"],
        capture_output=True, text=True, check=False,
    )
    if result.returncode == 0:
        members = json.loads(result.stdout)
```

Capability checks are stronger than presence checks for feature-gating
— they signal that a specific feature exists, not just that the
module is installed. The shell-out-to-canonical-CLI pattern is
preferred over direct Python imports for cross-module integrations:
the CLI surface is the stable contract; the package internals are not.

**2. Reading the other module's `[config]`.**

Each module's `[config]` table is free-form. The
`dev_modules.load_module()` API parses the manifest and exposes
`[config]` as a dict. Convention: a module documents which `[config]`
keys it exposes for consumers; consumers read them by name.

```python
from dev_modules import load_module

producer = load_module("some-producer-module")
if producer:
    journal_dir = producer.config.get("journal_dir")
```

**3. Graceful absence.**

Every consumer-of-another-module call must silent-skip when the
producer is absent:

```python
# Right
if is_installed("parley"):
    parley_emit_blocker(reason="compaction")

# Wrong — would raise ImportError if parley not installed
import parley.cli   # bare top-level import
```

The dev-modules reader's `is_installed()` and `has_capability()`
return `False` (never raise) when the producer's manifest is missing
or malformed. Consumers just need to gate their calls on the return
value — and keep the import scoped inside the gate, so the absent
case doesn't even load the producer code.

**4. Install ordering.**

Both modules must install correctly in either order
(parley-first-then-consumer, or consumer-first-then-parley). When
both manage hook entries in `.claude/settings.json`, each installer
should check whether the other's marker prefix is already present
and skip its own would-duplicate entry. The parley installer
demonstrates this: its `_install_claude_hook` scans existing
`SessionStart` entries for known competing markers (e.g.,
`workshop-lite-session-context`, `dev-mgmt-session-context`) and
skips the parley `SessionStart` append when one is found.
PreCompact entries dual-fire — both installers' PreCompact hooks
run independently because they serve different consumers (the
current peer agents vs. the next agent).

Document your installer's marker-scan rule in your own README so
other modules know what name strings to use.

**5. Cross-system decision pointers (URI-prefix scheme).**

When a decision spans both modules' ownership slices, carry
bidirectional pointers via a URI-prefix scheme:

- workshop-lite Decision frontmatter (per
  `LIGHTWEIGHT-DEV-MGMT-SYSTEM.md §6`) carries
  `linked_msg_ids: ['msg-...']` pointing at parley message IDs.
- parley `Kind.DECISION` records carry
  `external_decision_refs: ['workshop-lite://<slug>']` pointing at
  workshop-lite decision filenames (URI-prefix scheme; see
  `parley decision log --external-ref` flag).
- Both fields are advisory; cross-link validation is each module's
  responsibility, not dev-modules'.

For the full ownership-and-cross-link protocol see
`workshop-lite/docs/design/PARLEY-DEV-MGMT-INTEGRATION.md`. For the
multi-repo coordination convention (when agents work across
multiple repos), see
`workshop-lite/docs/design/multi-repo-coord.md`.

**6. Test the absent case.**

Add a smoke test exercising your tool with the producer module NOT
installed. Graceful skip must work — no error output, no exit-1, no
warnings the user can't act on. The parley + workshop-lite pair's
4-permutation smoke matrix (parley-only / workshop-lite-only /
both-in-either-order) is a worked example of this discipline.

### Step 6 — Document it in this repo's README

Add a short section so future readers (and future you) understand
what this tool advertises. Minimum:

```markdown
## dev-modules integration

This tool registers itself at `.modules/<name>/module.toml` in the
target repository. It advertises the capabilities:

- `<name>.<feature>` — what it does.

[If consuming others:]
It adapts its behavior when these modules are present:

- `<other-module>` / `<other-module>.<cap>` — what changes.
```

## Testing

Before marking the task done:

1. Run the install path against a clean test repo (a `tmp/` directory
   with `git init` is fine).
2. Check `cat <test-repo>/.modules/<name>/module.toml` — confirm
   fields are correct.
3. If you added the reader dep, run from that test repo:

   ```bash
   python -c "from dev_modules import installed_modules; print(installed_modules())"
   ```

   Confirm `<name>` appears in the output.
4. Run the uninstall step. Confirm the directory is gone and the
   reader no longer sees it.
5. Run the install step a second time. Confirm it succeeds (idempotency).

## Definition of done

- [ ] Installing the tool into a repo writes a valid
  `.modules/<name>/module.toml`.
- [ ] Manifest parses: `schema_version = 1`, correct `name`,
  `version`, `description`, namespaced `capabilities`.
- [ ] Write is atomic (temp + rename).
- [ ] Uninstalling the tool removes the directory.
- [ ] Repeated installs are idempotent.
- [ ] If consuming other modules, reader lib is a declared dependency
  and absent modules produce no errors.
- [ ] README documents what's advertised and what's consumed.

## Common pitfalls

- **Writing non-atomically.** Direct `open(path, "w")` can leave
  readers seeing half-written TOML during concurrent access. Always
  temp + rename.
- **Removing the parent `.modules/` directory.** It's shared with
  other modules. Only remove your own subdirectory.
- **Putting secrets in the manifest.** Anything that needs to stay
  private belongs in your tool's own config directory, not `.modules/`.
- **Hard-depending on another module.** Even if you always expect
  telegram to be installed, check for it — users will try to run the
  tool without telegram and it should not break.
- **Capability name collisions.** Keep capabilities under your own
  namespace (`<your-name>.<feature>`). Don't shadow another module.
- **Registering from the wrong directory.** When your installer runs,
  be sure it writes to the *target repo's* `.modules/`, not to your
  own tool's repo. Use an explicit `target_repo` argument / detection.

## Scope discipline

Do the minimum to satisfy the Definition of Done. Do not:

- Build a plugin loader that dynamically imports files from
  `.modules/<other>/` (not a goal of dev-modules).
- Add an event bus or observer pattern (not a goal; consumers call
  producer APIs directly).
- Invent new manifest fields beyond the schema (forward compat:
  readers will refuse unknown shapes).

## References

- Repo: <https://github.com/JanusMarko/dev-modules>
- Spec: <https://github.com/JanusMarko/dev-modules/blob/main/SPEC.md>
- Example manifest: <https://github.com/JanusMarko/dev-modules/blob/main/examples/module.toml>
- Python reader source: `python/dev_modules/` in the repo
- TypeScript reader source: `typescript/src/` in the repo
