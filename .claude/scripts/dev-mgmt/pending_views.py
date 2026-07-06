"""Pending-view helpers for the §4.8 CLI verbs (Sprint workshop-lite.14).

Read-side filters over decision + standing-dispatch entities that surface
"what does this seat still owe?" — list entries whose `recipients[]`
names the queried seat AND that have NOT been marked acted-on per the
"when present" §4.8 semantic.

Master design §4.8:

> A read-side view that lists workshop-lite decisions whose `recipients`
> (when present) name the queried seat AND that have not been marked
> acted-on. Composes with parley primitive #3 (reboot recovery): when
> a seat respawns, it queries this view to discover decisions delivered
> while it was dark.

Forward-compatible by design — if/when decision entities adopt
`recipients[]` + `acted_on_by[]` fields, the verbs surface those
entries naturally. Today (2026-05-31) no shipped decision uses these
fields; verb returns empty against this repo, which is the right
"no pending work for any seat" answer.

For standing-dispatch entities the shipped reality is `recipients[]` +
`status: standing | satisfied | superseded` + `satisfied_by: <fqid>`
(single-seat). Map "acted-on" = (a) seat ∈ `acted_on_by` (future-compat
multi-seat), OR (b) `status == satisfied` AND `satisfied_by == seat`
(current shipped single-seat semantic), OR (c) `status == superseded`
(whole-dispatch terminal — no recipient needs to act on a superseded
dispatch).

Parley-agnostic per CLAUDE.md Hard Rule 1 — pure frontmatter walk +
filter.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import frontmatter
import ledger_paths
from cross_links import is_index_file


def _safe_parse(path: Path) -> dict | None:
    """Best-effort frontmatter parse; None on malformed input."""
    try:
        fm, _body = frontmatter.parse(path)
    except Exception:
        return None
    if not isinstance(fm, dict):
        return None
    return fm


def _iter_entities(dir_: Path) -> list[tuple[Path, dict]]:
    """Yield (path, frontmatter) for each non-INDEX `*.md` in dir_."""
    if not dir_.is_dir():
        return []
    out: list[tuple[Path, dict]] = []
    for path in sorted(dir_.glob("*.md")):
        if is_index_file(path):
            continue
        fm = _safe_parse(path)
        if fm is None:
            continue
        out.append((path, fm))
    return out


def _string_list(fm: dict, key: str) -> list[str]:
    """Coerce a frontmatter field to a list of non-empty strings.

    Tolerates None / single-string / non-list inputs so a typo in one
    entity doesn't crash the whole filter.
    """
    v = fm.get(key)
    if v is None:
        return []
    if isinstance(v, str):
        v = [v]
    if not isinstance(v, (list, tuple)):
        return []
    return [s for s in v if isinstance(s, str) and s]


def _seat_in_recipients(fm: dict, seat: str) -> bool:
    """Exact-string match against any element of `recipients[]`.

    No prefix / substring matching — `seat:wl-plan` matches only
    `seat:wl-plan`, not `seat:wl-plan-2` (substring-collision guard).
    """
    return seat in _string_list(fm, "recipients")


def _seat_acted_on_decision(fm: dict, seat: str) -> bool:
    """For decision entities: "acted on by seat" iff seat ∈ `acted_on_by[]`.

    Forward-compatible: today no shipped decision uses this field;
    schema additions surface naturally.
    """
    return seat in _string_list(fm, "acted_on_by")


def _seat_acted_on_dispatch(fm: dict, seat: str) -> bool:
    """For standing-dispatch entities: "acted on" maps the current
    shipped single-seat `satisfied_by` semantic + the forward-compat
    multi-seat `acted_on_by` field + the whole-dispatch terminal
    `status: superseded`.
    """
    if seat in _string_list(fm, "acted_on_by"):
        return True
    status = fm.get("status")
    if status == "satisfied" and fm.get("satisfied_by") == seat:
        return True
    if status == "superseded":
        return True
    return False


def _by_created_at(fm: dict) -> str:
    """Stable sort key — `created_at` ISO string, empty when absent."""
    v = fm.get("created_at")
    return v if isinstance(v, str) else ""


def list_pending_decisions(repo_root: str | Path, seat: str) -> list[dict]:
    """Return decision frontmatter dicts pending for `seat`.

    A decision is "pending for seat" iff:
    - it has a `recipients` field that's a non-empty list,
    - `seat` is an element of that list,
    - AND `seat` is NOT an element of `acted_on_by[]` (per §4.8 "when
      present" semantic — absence means no acts).

    Returned list sorted by `created_at` ASC (stable; absent values
    sort to the front).
    """
    if not seat:
        return []
    repo = Path(repo_root)
    decisions_dir = ledger_paths.compat_kind_dir(repo, "decisions")
    out: list[dict] = [
        fm for _p, fm in _iter_entities(decisions_dir)
        if _seat_in_recipients(fm, seat)
        and not _seat_acted_on_decision(fm, seat)
    ]
    out.sort(key=_by_created_at)
    return out


def list_pending_dispatches(repo_root: str | Path, seat: str) -> list[dict]:
    """Return standing-dispatch frontmatter dicts pending for `seat`.

    A dispatch is "pending for seat" iff:
    - it has a `recipients` field that's a non-empty list,
    - `seat` is an element of that list,
    - AND `seat` has NOT acted on it per `_seat_acted_on_dispatch`
      (single-seat `satisfied_by` + multi-seat `acted_on_by` +
      whole-dispatch `superseded` terminal).

    Returned list sorted by `created_at` ASC. Empty result when
    `docs/dispatches/` doesn't exist (degrade-clean).
    """
    if not seat:
        return []
    repo = Path(repo_root)
    dispatches_dir = ledger_paths.compat_kind_dir(repo, "dispatches")
    out: list[dict] = [
        fm for _p, fm in _iter_entities(dispatches_dir)
        if _seat_in_recipients(fm, seat)
        and not _seat_acted_on_dispatch(fm, seat)
    ]
    out.sort(key=_by_created_at)
    return out


# ---------------------------------------------------------------------------
# Render — text + JSON
# ---------------------------------------------------------------------------

_TEXT_COLUMNS = ("id", "title", "recipients", "acted_on_by")


def _short(value: Any, max_len: int = 60) -> str:
    """Truncate long strings for the text-table column."""
    s = str(value) if value is not None else "-"
    if not s:
        s = "-"
    if len(s) <= max_len:
        return s
    return s[: max_len - 1] + "…"


def format_text(entries: list[dict], *, kind_label: str, seat: str) -> str:
    """4-column human-readable table.

    Empty cells render as `-`. Multi-value fields (`recipients`,
    `acted_on_by`) render as comma-joined.
    """
    header = f"{kind_label} pending for {seat}:"
    if not entries:
        return f"{header}\n  (none)\n"
    rows: list[list[str]] = [list(_TEXT_COLUMNS)]
    for fm in entries:
        recipients = ", ".join(_string_list(fm, "recipients")) or "-"
        acted = ", ".join(_string_list(fm, "acted_on_by")) or "-"
        rows.append([
            _short(fm.get("id"), 50),
            _short(fm.get("title"), 60),
            _short(recipients, 40),
            _short(acted, 30),
        ])
    widths = [max(len(r[i]) for r in rows) for i in range(len(_TEXT_COLUMNS))]
    lines = [header, ""]
    for i, row in enumerate(rows):
        lines.append("  " + "  ".join(
            cell.ljust(widths[col_i]) for col_i, cell in enumerate(row)
        ))
        if i == 0:
            lines.append("  " + "  ".join("-" * w for w in widths))
    lines.append("")
    return "\n".join(lines)
