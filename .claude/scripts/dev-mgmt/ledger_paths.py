"""Canonical workshop-lite ledger path helpers.

WL2 stores framework-owned records under ``.workshop-lite/ledger``.  V1
fixtures and older consumer repos may still only have ``docs/<kind>``; the
compat resolver keeps those repos green while letting initialized WL2 repos
write to the new store.
"""
from __future__ import annotations

from pathlib import Path


LEDGER_ROOT = Path(".workshop-lite") / "ledger"
LEGACY_ROOT = Path("docs")


_KIND_ALIASES: dict[str, str] = {
    "decision": "decisions",
    "decisions": "decisions",
    "issue": "issues",
    "issues": "issues",
    "review": "reviews",
    "reviews": "reviews",
    "handoff": "handoffs",
    "handoffs": "handoffs",
    "conversation": "conversations",
    "conversations": "conversations",
    "prd": "prds",
    "prds": "prds",
    "standing_dispatch": "dispatches",
    "dispatch": "dispatches",
    "dispatches": "dispatches",
    "wip_claim": "wip",
    "wip": "wip",
    "gate": "gates",
    "gates": "gates",
    "eval": "evals",
    "eval-corpus": "evals",
    "eval-corpora": "evals",
    "evals": "evals",
    "denial": "denials",
    "denials": "denials",
    "closure": "closures",
    "closure-record": "closures",
    "closures": "closures",
    "workflow": "workflows",
    "workflows": "workflows",
    "role-set": "role-sets",
    "role_sets": "role-sets",
    "role-sets": "role-sets",
    "block-signal": "block-signals",
    "block_signals": "block-signals",
    "block-signals": "block-signals",
    "resume-ledger": "resume-ledgers",
    "resume_ledgers": "resume-ledgers",
    "resume-ledgers": "resume-ledgers",
    "canonical-pointer": "pointers",
    "pointer": "pointers",
    "pointers": "pointers",
    "sprint": "sprints",
    "sprints": "sprints",
}


def ledger_root(repo_root: str | Path | None = None) -> Path:
    """Return the canonical WL2 ledger root for ``repo_root``."""
    repo = Path(repo_root) if repo_root is not None else Path.cwd()
    return repo / LEDGER_ROOT


def legacy_root(repo_root: str | Path | None = None) -> Path:
    """Return the legacy v1 docs root for ``repo_root``."""
    repo = Path(repo_root) if repo_root is not None else Path.cwd()
    return repo / LEGACY_ROOT


def canonical_kind_dir(repo_root: str | Path | None, kind: str) -> Path:
    """Return the WL2 canonical directory for an entity kind."""
    return ledger_root(repo_root) / kind_dir_name(kind)


def compat_kind_dir(repo_root: str | Path | None, kind: str) -> Path:
    """Return the active storage directory for an entity kind.

    A repo with ``.workshop-lite`` is treated as WL2-initialized and uses the
    ledger even before the specific kind directory exists. Older v1 test
    fixtures without that marker continue to use ``docs/<kind>``.
    """
    repo = Path(repo_root) if repo_root is not None else Path.cwd()
    if (repo / ".workshop-lite").exists():
        return repo / LEDGER_ROOT / kind_dir_name(kind)
    return repo / LEGACY_ROOT / kind_dir_name(kind)


def compat_sprints_dir(repo_root: str | Path | None = None) -> Path:
    """Return the active sprint store directory."""
    return compat_kind_dir(repo_root, "sprints")


def kind_dir_name(kind: str) -> str:
    """Normalize singular/plural public kind names to ledger directory names."""
    key = kind.strip().lower().replace("_", "-")
    try:
        return _KIND_ALIASES[key]
    except KeyError as exc:
        raise KeyError(f"unknown workshop-lite kind: {kind!r}") from exc


def display_path(path: Path, repo_root: str | Path | None = None) -> str:
    """Render a repo-relative path for user-facing pointers."""
    repo = Path(repo_root) if repo_root is not None else Path.cwd()
    try:
        return path.relative_to(repo).as_posix()
    except ValueError:
        return path.as_posix()
