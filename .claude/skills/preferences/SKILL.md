---
name: preferences
description: The Workshop-Lite user-scoped preference mechanism — a modular, abstraction-first per-user preference system (Storage + ScopeResolver + PreferenceProvider behind interfaces) living at .claude/scripts/dev-mgmt/preferences.py, plus its skill/hook-layer adapters and the consumer-consult convention. Reference home, not an agent-invoked verb. Read when configuring or consuming user-scoped preferences such as autonomy_level or abstraction_first.
---

# preferences — the Workshop-Lite user-scoped preference mechanism

Not an agent-invoked verb. This is the **home of the general per-user
preference mechanism** (Kris priority item 2) + its skill/hook-layer
adapters + the consumer-consult convention. The pure mechanism is the
lib module `.claude/scripts/dev-mgmt/preferences.py`.

## What it is

A general, modular, **user-scoped** preference system — abstraction-first
/ meta-consistent: three decoupled components behind interfaces, each
independently swappable so a second backend or consumer reuses them.

- `Storage` (path-agnostic interface) — default `FilePreferenceStorage`
  reads `<repo>/.claude/preferences.toml`; `EnvPreferenceStorage` (this
  dir) is a real second backend.
- `ScopeResolver` — resolves *who is the user* (the **human operator**,
  not the agent member). Lib default `DefaultScopeResolver`
  (parley-agnostic: `WSL_PREFS_USER` env > cwd-fallback > `"default"`).
  `ParleyHumanScopeResolver` (this dir) is the skill/hook-layer adapter
  that reads the live parley human id; **parley-coupling lives here,
  never in the lib** (Hard Rule 1, D27).
- `PreferenceProvider` — composes the two; resolves through ONE
  precedence function: caller `default` < `[defaults.<ns>]` <
  `[users.<resolved-user>.<ns>]`.

Preferences are **out-of-band of Workshop §6** (config, not an entity).
`schema_version` is in-file for forward migration.

## How a skill / instruction / hook consults it

ONE path for skills AND hooks (never two impls):

```python
import sys; sys.path.insert(0, ".claude/scripts/dev-mgmt")
from preferences import get_preference

# default MUST be the safe/off value — opt-in only, no global enable:
abstraction_first = get_preference(
    "planning", "abstraction_first", default=False,
    # skills/hooks inject the parley-aware human resolver:
    #   from adapters import ParleyHumanScopeResolver
    #   resolver=ParleyHumanScopeResolver()
)
if abstraction_first:
    # emit the abstraction-first lens section/checklist into the
    # plan/artifact this skill is producing.
    ...
```

`get_preference` never raises: a missing/malformed store, unknown or
unresolved user → the passed `default`. The lib default resolver is
parley-agnostic; pass `ParleyHumanScopeResolver()` from this dir when a
live parley human scope is wanted (it degrades to the lib default if
parley is absent).

## Preference #2 — autonomy-level (Sprint wl.15)

`planning.autonomy_level` is the **second** rider on the general
mechanism. String enum: `"forward-motion"` (Hard Rule #8 binds; the
SessionStart hook emits the forward-motion reminder for
`role_kind=="scrum_master"` seats) | `"prompt"` (no reminder;
ask-before-dispatch posture) | absent → `"prompt"` default
(opt-in / off-by-default per the "modular not hardcoded global"
principle). Consumed in `.claude/hooks/session-context.sh:1a`.

## Preference #1 — abstraction-first (the reference rider)

`planning.abstraction_first` is the **first** preference riding the
general mechanism (it is *just a rider* — the mechanism is the
deliverable). It is **opt-IN, Kris-scoped only**: shipped solely as
`[users.kris.planning] abstraction_first = true` in
`.claude/preferences.toml`. There is intentionally **NO `[defaults.*]`
enable** — other users, the absent-file case, and unresolved-user all
get `False`. This is the literal point of Kris's "modular, not a
hardcoded global": when enabled, abstraction is a first-class concern
in all planning + writing (code AND docs/skills) — build
adapters/interfaces, do not tightly couple, unless honoring it would
break the system.

## Adding a preference / a second backend

- New preference: pick/extend a namespace; add `[users.<uid>.<ns>]`
  (or, if a genuine repo-wide default is wanted, `[defaults.<ns>]` —
  but NEVER use `[defaults]` to enable an opt-in stance like
  abstraction-first).
- Second Storage/ScopeResolver: implement the Protocol shape and inject
  it; the lib is never modified (see `adapters.py` for two worked
  examples).
