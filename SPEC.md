# dev-modules spec

Schema version: **1**

## Layout

```
<repo-root>/.modules/<name>/module.toml
```

`.modules/<name>/module.toml` is the authoritative record for a module named
`<name>`. No root index file; discovery is "list `.modules/`, validate each
subdirectory's `module.toml`." Each tool manages only its own subdirectory.

## module.toml schema

```toml
schema_version = 1               # required
name = "<module-name>"           # required; MUST equal parent directory name
version = "<semver>"             # required; display/debug only

description = "<one-line text>"  # optional
capabilities = ["<cap>", "..."]  # optional

[config]                         # optional; module-specific; NOT read by dev-modules
# arbitrary keys ignored by the spec
```

### Field rules

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `schema_version` | int | yes | Readers MUST refuse unknown values. |
| `name` | str | yes | `[a-z][a-z0-9-]*`, matches parent directory name. |
| `version` | str | yes | Semver or similar; not validated. |
| `description` | str | no | One line. |
| `capabilities` | list[str] | no | Namespaced (`<module>.<feature>`). See below. |
| `[config]` | table | no | Free-form; consumers may read it but dev-modules doesn't interpret. |

### Capabilities

Capability strings are **namespaced by module**:

```
<module-name>.<dotted-feature>
```

Examples:

- `workshop.journal.read`
- `workshop.grid.intake`
- `telegram.notify`
- `telegram.notify.inline_buttons`
- `ccweb.ui.sidebar`

A module SHOULD only advertise capabilities under its own namespace. Consumers
check capabilities before using a feature:

```python
if has_capability("workshop", "workshop.journal.read"):
    ...
```

## Discovery rules

A module `<name>` is **installed** iff **both**:

1. `<repo>/.modules/<name>/` exists and is a directory.
2. `<repo>/.modules/<name>/module.toml` parses successfully with a compatible
   `schema_version` and a `name` field matching the directory name.

Either condition failing → not installed. Consumers MUST gracefully handle
absence — no exceptions, just a `False` / empty return.

### Finding the repo root

Readers walk upward from the starting directory (default: `cwd`) and use the
**nearest ancestor** containing a `.modules/` directory. If none is found,
they return an empty result.

## Install / uninstall

Each tool writes/removes its own manifest during install/uninstall:

- **Install**: write `.modules/<name>/module.toml` **atomically** (write to a
  temp file, then rename). This avoids torn reads if another process is
  enumerating simultaneously.
- **Uninstall**: remove `.modules/<name>/`.

Multiple tools installing concurrently is safe because each touches a
different subdirectory.

## Non-goals

- **No event bus.** Consumers call producers' public APIs directly.
- **No config store.** Module config lives wherever the module normally
  stores it.
- **No runtime code loading.** The manifest only gates behavior of
  already-installed code.
- **No version negotiation.** Use capabilities (feature flags) for API
  contracts; `version` is display-only.

## Forward compatibility

- `schema_version = 1` is the current version.
- Future versions MUST add new optional fields only, or bump
  `schema_version` and require a reader update.
- Readers MUST refuse unknown `schema_version` values rather than
  guess — returning "not installed" is the safe default.
