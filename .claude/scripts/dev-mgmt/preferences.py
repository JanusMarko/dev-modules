"""User-scoped preferences — the GENERAL per-user preference mechanism
for Workshop-Lite (Kris priority item 2; @plan ruling msg-8194eb9c441f).

ABSTRACTION-FIRST / META-CONSISTENT BY CONSTRUCTION: three DECOUPLED
components behind interfaces, each independently swappable so a second
backend or consumer reuses them without touching this module:

  - ``Storage``        — where preferences live (load/save). Interface
                         is PATH-AGNOSTIC; the default file path is the
                         default adapter's literal, never the interface's.
  - ``ScopeResolver``  — answers "who is the user" => a stable user-id
                         string. Acquisition is the adapter's concern.
  - ``PreferenceProvider`` — composes a Storage + a ScopeResolver and
                         resolves an effective value through ONE
                         precedence function (eliminate-by-construction:
                         precedence cannot drift across call sites).

PARLEY-AGNOSTIC (CLAUDE.md Hard Rule 1): this module NEVER imports or
shells parley. The lib default resolver is config/cwd-only. A
parley-human-id ScopeResolver is a SKILL/HOOK-layer adapter (D27)
injected from outside — never here.

OUT-OF-BAND of Workshop §6 (@plan ruling (c)): preferences are
config, NOT decision/issue/history entities — deliberately not
frontmatter-importable. ``schema_version`` is carried in-file for
forward migration.

MODULAR, NOT A HARDCODED GLOBAL (@plan ruling (f)/(g), load-bearing):
there is NO built-in/global enable for any preference. ``planning.
abstraction_first`` is opt-IN — True ONLY via a user-scoped value
(Kris's section). Absent file / unknown user / unresolved user =>
the caller's ``default`` (False at the abstraction-first call sites).
Graceful-absence is mandatory: a missing or malformed store yields
defaults and NEVER raises.

Schema (the default file-backed adapter's TOML; any backend may carry
the same logical shape)::

    schema_version = 1
    [defaults.<namespace>]            # optional repo-wide defaults
    <key> = <value>
    [users.<user-id>.<namespace>]     # user-scoped
    <key> = <value>

Precedence (the single resolution function): caller ``default``
< ``defaults.<ns>.<key>`` < ``users.<resolved-user>.<ns>.<key>``.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

SCHEMA_VERSION = 1

# The default file-backed adapter's literal — lives HERE in the adapter
# layer, NEVER in the Storage interface (ruling (c): path-agnostic
# interface; a parley-substrate/env/in-memory backend rides the same
# interface with no path at all).
_DEFAULT_REL_PATH = ".claude/preferences.toml"


# ---------------------------------------------------------------------------
# Interfaces (structural Protocols — a 2nd impl needs only the shape)
# ---------------------------------------------------------------------------


@runtime_checkable
class Storage(Protocol):
    """Where preferences live. PATH-AGNOSTIC: nothing about a filesystem
    path is in this contract. Returns the logical document
    ``{schema_version, defaults: {ns: {k: v}}, users: {uid: {ns: {k:
    v}}}}``; a missing/empty store returns ``{}`` (never raises — the
    provider degrades to defaults).
    """

    def load(self) -> dict[str, Any]: ...

    def save(self, doc: dict[str, Any]) -> None: ...


@runtime_checkable
class ScopeResolver(Protocol):
    """Resolves "who is the user" to a STABLE user-id string. The
    terminal/safe value is ``"default"`` (=> built-in defaults only).
    Acquisition (env, parley, cwd, ...) is entirely the adapter's
    concern; the contract is just: return a str, never raise.
    """

    def resolve_user(self) -> str: ...


# ---------------------------------------------------------------------------
# Default adapters (parley-agnostic — Hard Rule 1)
# ---------------------------------------------------------------------------


class FilePreferenceStorage:
    """Default Storage: a TOML file. The default location
    (``<repo>/.claude/preferences.toml``) is THIS adapter's literal —
    constructable with ANY path; the interface knows no path.
    Graceful: missing/unreadable/malformed => ``{}`` (never raises).
    """

    def __init__(self, path: str | Path | None = None,
                 *, repo_root: str | Path | None = None) -> None:
        if path is not None:
            self._path = Path(path)
        else:
            root = Path(repo_root) if repo_root is not None else Path.cwd()
            self._path = root / _DEFAULT_REL_PATH

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> dict[str, Any]:
        try:
            with open(self._path, "rb") as fh:
                return tomllib.load(fh)
        except (FileNotFoundError, IsADirectoryError, PermissionError,
                tomllib.TOMLDecodeError, OSError):
            return {}  # graceful-absence: degrade to defaults

    def save(self, doc: dict[str, Any]) -> None:
        # Minimal deterministic TOML writer for the fixed schema
        # (schema_version + [defaults.<ns>] / [users.<uid>.<ns>] scalar
        # tables). Operator-managed files may be richer; this round-trips
        # the schema this module owns.
        lines: list[str] = [
            f"schema_version = {int(doc.get('schema_version', SCHEMA_VERSION))}",
            "",
        ]

        def _emit(prefix: str, tables: dict[str, Any]) -> None:
            for outer in sorted(tables):
                ns_map = tables[outer]
                if not isinstance(ns_map, dict):
                    continue
                for ns in sorted(ns_map):
                    kv = ns_map[ns]
                    if not isinstance(kv, dict):
                        continue
                    lines.append(f"[{prefix}.{outer}.{ns}]"
                                 if prefix == "users"
                                 else f"[{prefix}.{ns}]")
                    for k in sorted(kv):
                        lines.append(f"{k} = {_toml_scalar(kv[k])}")
                    lines.append("")

        defaults = doc.get("defaults", {})
        if isinstance(defaults, dict) and defaults:
            for ns in sorted(defaults):
                kv = defaults[ns]
                if not isinstance(kv, dict):
                    continue
                lines.append(f"[defaults.{ns}]")
                for k in sorted(kv):
                    lines.append(f"{k} = {_toml_scalar(kv[k])}")
                lines.append("")
        users = doc.get("users", {})
        if isinstance(users, dict) and users:
            _emit("users", users)

        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        tmp.replace(self._path)


def _toml_scalar(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    return '"' + str(v).replace("\\", "\\\\").replace('"', '\\"') + '"'


class DefaultScopeResolver:
    """Default ScopeResolver — PARLEY-AGNOSTIC (Hard Rule 1). Precedence
    chain (ruling (b)): explicit env ``WSL_PREFS_USER`` > cwd-fallback
    (a best-effort heuristic — the cwd basename; documented as NOT
    identity, only a convenience) > ``"default"`` (safe terminal). The
    parley-human-id resolver is a SEPARATE skill/hook-layer adapter,
    never this class.
    """

    def __init__(self, *, env: dict[str, str] | None = None,
                 cwd: str | Path | None = None) -> None:
        import os
        self._env = os.environ if env is None else env
        self._cwd = Path(cwd) if cwd is not None else Path.cwd()

    def resolve_user(self) -> str:
        explicit = (self._env.get("WSL_PREFS_USER") or "").strip()
        if explicit:
            return explicit
        # cwd-fallback: best-effort, NOT identity (documented). Used
        # only so a single-user repo "just works"; collisions across
        # users in the same cwd are expected and acceptable.
        base = self._cwd.name.strip()
        if base:
            return f"cwd:{base}"
        return "default"


# ---------------------------------------------------------------------------
# Provider — the single precedence-resolution point
# ---------------------------------------------------------------------------


def _resolve_effective(doc: dict[str, Any], user: str, namespace: str,
                       key: str, caller_default: Any) -> Any:
    """THE single precedence function (ruling (e),
    eliminate-by-construction — no scattered checks anywhere else):

      caller_default
        < doc["defaults"][namespace][key]
        < doc["users"][user][namespace][key]

    Any missing layer is skipped; unknown user / absent doc => the
    most-default available. There is intentionally NO built-in/global
    table here — "no hardcoded global" (ruling f/g) is enforced by
    construction: the only enable path is the user-scoped layer.
    """
    value = caller_default
    defaults = doc.get("defaults")
    if isinstance(defaults, dict):
        ns = defaults.get(namespace)
        if isinstance(ns, dict) and key in ns:
            value = ns[key]
    users = doc.get("users")
    if isinstance(users, dict):
        u = users.get(user)
        if isinstance(u, dict):
            ns = u.get(namespace)
            if isinstance(ns, dict) and key in ns:
                value = ns[key]
    return value


class PreferenceProvider:
    """Composes a Storage + a ScopeResolver. The ONLY object that
    resolves effective values, and it does so through the single
    ``_resolve_effective`` function.
    """

    def __init__(self, storage: Storage, resolver: ScopeResolver) -> None:
        self._storage = storage
        self._resolver = resolver

    def get(self, namespace: str, key: str, *, default: Any) -> Any:
        try:
            doc = self._storage.load()
        except Exception:
            doc = {}  # graceful-absence is mandatory, never raises
        if not isinstance(doc, dict):
            doc = {}
        try:
            user = self._resolver.resolve_user() or "default"
        except Exception:
            user = "default"
        return _resolve_effective(doc, user, namespace, key, default)

    def all_for(self, namespace: str) -> dict[str, Any]:
        """Bulk: the effective namespace map (defaults overlaid by the
        resolved user's section). Resolves the user/store ONCE."""
        try:
            doc = self._storage.load()
        except Exception:
            doc = {}
        if not isinstance(doc, dict):
            doc = {}
        try:
            user = self._resolver.resolve_user() or "default"
        except Exception:
            user = "default"
        out: dict[str, Any] = {}
        d = doc.get("defaults")
        if isinstance(d, dict) and isinstance(d.get(namespace), dict):
            out.update(d[namespace])
        u = doc.get("users")
        if isinstance(u, dict) and isinstance(u.get(user), dict):
            uns = u[user].get(namespace)
            if isinstance(uns, dict):
                out.update(uns)
        return out


# ---------------------------------------------------------------------------
# Public consumer API — ONE path for skills AND hooks (ruling (d)/(f))
# ---------------------------------------------------------------------------


def _provider(resolver: ScopeResolver | None,
              storage: Storage | None,
              repo_root: str | Path | None) -> PreferenceProvider:
    return PreferenceProvider(
        storage if storage is not None
        else FilePreferenceStorage(repo_root=repo_root),
        resolver if resolver is not None
        else DefaultScopeResolver(),
    )


def get_preference(namespace: str, key: str, *, default: Any,
                   resolver: ScopeResolver | None = None,
                   storage: Storage | None = None,
                   repo_root: str | Path | None = None) -> Any:
    """The single consumer read API (skills AND hooks use THIS, one
    path, never two impls). ``resolver``/``storage`` are injectable —
    skills/hooks pass a parley-aware ScopeResolver adapter; the lib
    default is config/cwd-only (parley-agnostic). Missing store / key
    / user => ``default``; NEVER raises.
    """
    return _provider(resolver, storage, repo_root).get(
        namespace, key, default=default)


def load_preferences(namespace: str, *,
                      resolver: ScopeResolver | None = None,
                      storage: Storage | None = None,
                      repo_root: str | Path | None = None) -> dict[str, Any]:
    """Bulk ergonomic (resolve store+user ONCE for a multi-key
    consumer). Same single path; same graceful-absence guarantee.
    """
    return _provider(resolver, storage, repo_root).all_for(namespace)
