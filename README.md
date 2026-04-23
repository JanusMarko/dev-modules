# dev-modules

A lightweight per-repo **service discovery** layer for dev-tool integrations.

Any tool that wants to be discoverable by other tools drops a manifest at
`.modules/<name>/module.toml` in the repo root. Other tools list `.modules/`
to see who else is installed and adapt their behavior.

## What it is

A shared convention — not a framework. Three rules:

1. **Presence advertises.** `.modules/<name>/module.toml` means `<name>` is installed here.
2. **Consumers are responsible.** If tool A wants to respond to tool B being present, tool A reads `.modules/` and acts accordingly. B doesn't know A exists.
3. **Graceful absence.** Nothing ever errors because a module isn't listed — callers just skip the integration.

## What it isn't

- Not a package manager — tools install themselves; `.modules/` only advertises.
- Not a config store — module config lives in each tool's own dir (`.claude/<name>/`, `~/.config/<name>/`, …).
- Not an event bus — consumers call producers' APIs directly.
- Not a plugin loader — code must already be installed; the manifest only gates whether it runs.

## Example

```
.modules/
  workshop/module.toml     # workshop present → ccweb surfaces workshop UI
  ccweb/module.toml        # ccweb present → workshop skills use ccweb grids
  telegram/module.toml     # telegram present → notification skills notify
```

When the option-grid skill runs, it checks `is_installed("telegram")` — if
true, it sends a notification; otherwise, silently skips.

## Readers

- **Python**: `pip install -e ./python` — `from dev_modules import installed_modules, is_installed, has_capability`
- **TypeScript** (Node): `cd typescript && npm install` — `import { installedModules, isInstalled, hasCapability } from "dev-modules"`

## Registering

Each tool writes its own manifest during install. Either:

```bash
# from your tool's installer:
cat <<'EOF' | scripts/register.sh mytool
schema_version = 1
name = "mytool"
version = "0.1.0"
capabilities = ["mytool.notify"]
EOF
```

Or just write the file directly — `register.sh` is a convenience for atomic
writes and finding the repo root.

## Spec

See [SPEC.md](SPEC.md).
