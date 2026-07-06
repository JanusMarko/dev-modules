"""Cohort W (wl:2026-06-03-06) — handoff aging / rolling-collapse policy.

File-side mover/archiver/merger/destructor + orchestrator. Pairs with
the INDEX-side rolling-collapse renderer already shipped in
``index.render_handoffs_index_with_rolling_collapse`` + the INDEX-
coherence suppression already shipped in
``validate._index_suppressed_slugs``.

Charter: ``docs/inbox/2026-06-05-cohort-W-2026-06-03-06-handoffs-aging-
rolling-collapse-policy-charter.md``.
Source issue: ``docs/issues/2026-06-03-06-handoffs-aging-rolling-collapse-
policy-charter-4-4-deferred-ship.md``.
Master design: ``docs/inbox/2026-05-29-workshop-lite-rearch-master-
design.md`` §4.6 + ``docs/design/LIGHTWEIGHT-DEV-MGMT-SYSTEM.md`` §10.1.

Prior-art reused (NOT reimplemented):

- ``index.is_empty_pre_compact_stub(fm, body)`` — binary+structural
  stub detector (Hard Rule 7); single source of truth for "what counts
  as a stub". Detection is exact-substring against a documented marker
  set with line-whitelist gate; never similarity-scored.
- ``index._handoffs_config(repo_root)`` — config reader with defaults
  (cohort W extended with the file-side aging fields).
- ``index.render_handoffs_index_with_rolling_collapse(repo_root=...)``
  — main-INDEX renderer (substantive + kept-stubs + rolling-collapse
  line). Called after a file-side run to re-stabilize the main INDEX.
- ``cross_links._handoff_slugs_including_archive(repo_root)`` —
  cursor-chain resolver already unions ``docs/handoffs/`` with
  ``docs/handoffs/archive/`` (wl.17 / Check #4), so an archived stub
  remains a valid ``since_handoff_id`` resolution target.

Cursor-chain integrity by strategy:

- ``archive`` (default): file relocates to
  ``docs/handoffs/archive/<id>.md``. The cross_links resolver already
  walks the archive dir, so ``since_handoff_id: <archived-id>``
  resolves transparently. An ``archived_to:`` + ``archived_at:`` field
  pair lands on the moved file as a breadcrumb.
- ``merge-into-prev``: cursor-chain fields (``since_handoff_id``,
  ``since_msg_id``, ``linked_msg_ids``) fold into the previous non-
  stub handoff. A ``merged_in: [<stub-id>, ...]`` list field on the
  receiving handoff tracks every absorbed stub. The source then
  archives (so resolution still works if anything pointed at it).
- ``delete``: destructive; cursor-chain into the deleted target
  breaks. Documented risk; operator must opt in explicitly via
  ``stub_collapse_strategy = "delete"``.

Parley-agnostic by construction (CLAUDE.md Hard Rule 1): pure file
I/O via the workshop-lite helper lib.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import frontmatter
import index
import ledger_paths


_VALID_STRATEGIES = ("archive", "merge-into-prev", "delete")


# ---------------------------------------------------------------------------
# Stub detection (age + keep-recent-n filtering on top of the §4.6 detector)
# ---------------------------------------------------------------------------


def detect_stubs(
    handoffs_dir: Path,
    *,
    empty_stub_age_hours: int,
    keep_recent_n: int,
    now: datetime | None = None,
) -> list[Path]:
    """Return paths to handoff stubs eligible for file-side collapse.

    A stub is eligible iff ALL hold:

    1. ``index.is_empty_pre_compact_stub(fm, body)`` is True (binary+
       structural — Hard Rule 7; the §4.6 detector is the single source
       of truth).
    2. ``created_at`` is strictly older than
       ``now - empty_stub_age_hours``.
    3. The stub is NOT among the ``keep_recent_n`` most-recent stubs
       (mirrors INDEX-side rule #3: most-recent stub stays full-form
       so the cursor-chain has an actionable resume target).

    Returns paths sorted oldest-first. Empty list when the dir doesn't
    exist OR no stubs are eligible.

    ``now`` is a test-only clock-injection seam.
    """
    if not handoffs_dir.exists():
        return []
    if now is None:
        now = index._utc_now()
    cutoff = now - timedelta(hours=empty_stub_age_hours)

    stubs: list[tuple[Path, datetime]] = []
    for path in sorted(handoffs_dir.glob("*.md")):
        if path.name == "INDEX.md" or path.name.startswith("INDEX-"):
            continue
        try:
            fm, body = frontmatter.parse(path)
        except Exception:
            continue
        if not isinstance(fm, dict):
            continue
        if not index.is_empty_pre_compact_stub(fm, body):
            continue
        created_dt = index._parse_handoff_created_dt(fm, now)
        stubs.append((path, created_dt))

    if not stubs:
        return []

    # Sort newest-first; the top `keep_recent_n` are unconditionally retained.
    stubs.sort(key=lambda x: x[1], reverse=True)
    keep_set: set[Path] = set()
    if keep_recent_n > 0:
        keep_set = {p for p, _dt in stubs[:keep_recent_n]}

    eligible = [
        (path, dt)
        for path, dt in stubs
        if path not in keep_set and dt < cutoff
    ]
    eligible.sort(key=lambda x: x[1])  # oldest first
    return [p for p, _dt in eligible]


# ---------------------------------------------------------------------------
# Collapse strategies (single-stub primitives)
# ---------------------------------------------------------------------------


def collapse_archive(stub: Path, *, archive_dir: Path) -> Path:
    """Move ``stub`` to ``archive_dir/<filename>``; stamp a breadcrumb.

    Non-destructive: file content preserved; only relocates + adds
    ``archived_to`` / ``archived_at`` frontmatter fields documenting
    the move. Returns the new path.

    Cursor-chain integrity: cross_links resolution already includes
    ``docs/handoffs/archive/``, so a ``since_handoff_id: <archived-id>``
    elsewhere still resolves (wl.17 / Check #4).
    """
    archive_dir.mkdir(parents=True, exist_ok=True)
    fm, body = frontmatter.parse(stub)
    if not isinstance(fm, dict):
        fm = {}
    target = archive_dir / stub.name
    fm["archived_to"] = f"docs/handoffs/archive/{stub.name}"
    fm["archived_at"] = (
        datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    )
    frontmatter.write(target, fm, body)
    stub.unlink()
    return target


def collapse_merge_into_prev(stub: Path) -> Path | None:
    """Fold ``stub``'s cursor-chain into the previous non-stub handoff,
    then archive the stub file.

    "Previous" = the chronologically immediately-preceding NON-stub
    handoff in the same ``docs/handoffs/`` directory. When no such
    predecessor exists (e.g., the stub is the oldest file or every
    older file is itself a stub), falls back to archive-only and
    returns ``None``.

    Cursor-chain fields folded onto prev (each only when prev's value
    is empty AND stub's value is non-empty — prev wins on conflict so
    we never silently overwrite hand-authored cursor metadata):

    - ``since_handoff_id``
    - ``since_msg_id``

    ``linked_msg_ids`` from stub APPENDS to prev's list (deduped),
    since msg-id lists are additive by nature.

    A ``merged_in: [<stub-id>, ...]`` list field on prev records every
    stub absorbed into it.

    Returns the path to prev (after rewrite) when a merge happened,
    OR ``None`` when no prev was found (archive-only fallback fired).
    """
    handoffs_dir = stub.parent
    fm_stub, _body_stub = frontmatter.parse(stub)
    if not isinstance(fm_stub, dict):
        fm_stub = {}

    stub_created = index._parse_handoff_created_dt(fm_stub, index._utc_now())
    candidates: list[tuple[Path, dict, datetime]] = []
    for path in handoffs_dir.glob("*.md"):
        if path == stub:
            continue
        if path.name == "INDEX.md" or path.name.startswith("INDEX-"):
            continue
        try:
            fm_other, body_other = frontmatter.parse(path)
        except Exception:
            continue
        if not isinstance(fm_other, dict):
            continue
        if index.is_empty_pre_compact_stub(fm_other, body_other):
            continue
        dt = index._parse_handoff_created_dt(fm_other, index._utc_now())
        if dt < stub_created:
            candidates.append((path, fm_other, dt))

    if not candidates:
        archive_dir = handoffs_dir / "archive"
        collapse_archive(stub, archive_dir=archive_dir)
        return None

    candidates.sort(key=lambda x: x[2], reverse=True)  # newest non-stub first
    prev_path, prev_fm, _prev_dt = candidates[0]

    if fm_stub.get("since_handoff_id") and not prev_fm.get("since_handoff_id"):
        prev_fm["since_handoff_id"] = fm_stub["since_handoff_id"]
    if fm_stub.get("since_msg_id") and not prev_fm.get("since_msg_id"):
        prev_fm["since_msg_id"] = fm_stub["since_msg_id"]

    stub_msgs = fm_stub.get("linked_msg_ids") or []
    if isinstance(stub_msgs, list) and stub_msgs:
        prev_msgs = prev_fm.get("linked_msg_ids") or []
        if not isinstance(prev_msgs, list):
            prev_msgs = []
        merged = list(prev_msgs)
        for m in stub_msgs:
            if isinstance(m, str) and m and m not in merged:
                merged.append(m)
        prev_fm["linked_msg_ids"] = merged

    merged_in = prev_fm.get("merged_in") or []
    if not isinstance(merged_in, list):
        merged_in = []
    stub_id = fm_stub.get("id") or stub.stem
    if stub_id not in merged_in:
        merged_in.append(stub_id)
    prev_fm["merged_in"] = merged_in

    # Re-read prev body (we only modified the fm dict in place; the body
    # stays as on disk).
    _orig_fm, prev_body = frontmatter.parse(prev_path)
    frontmatter.write(prev_path, prev_fm, prev_body)

    archive_dir = handoffs_dir / "archive"
    collapse_archive(stub, archive_dir=archive_dir)
    return prev_path


def collapse_delete(stub: Path) -> None:
    """Destructive: remove ``stub`` from disk.

    Cursor-chain into the deleted target BREAKS. Operator MUST
    explicitly opt in via ``stub_collapse_strategy = "delete"``. The
    orchestrator gates this strategy behind that explicit config.
    """
    stub.unlink()


# ---------------------------------------------------------------------------
# Archive INDEX renderer + main-INDEX refresh
# ---------------------------------------------------------------------------


def _render_archive_index(archive_dir: Path) -> str:
    """Render ``docs/handoffs/archive/INDEX.md`` as a flat table.

    Reuses ``index.render`` with ``HANDOFF_COLUMNS`` so archived stubs
    stay discoverable with the same column shape as the main INDEX
    (default-OFF path). Returns the rendered content; empty string
    when the archive dir doesn't exist.
    """
    if not archive_dir.exists():
        return ""
    index.render(
        archive_dir,
        title="Handoffs (archive)",
        columns=index.HANDOFF_COLUMNS,
    )
    idx = archive_dir / "INDEX.md"
    return idx.read_text(encoding="utf-8") if idx.exists() else ""


def update_index_after_collapse(repo_root: Path) -> dict[str, str]:
    """Re-render both INDEX files after a file-side aging run.

    - Main ``docs/handoffs/INDEX.md`` via the rolling-collapse-aware
      renderer (substantive + kept-stubs + collapsed line when config
      ON; flat-table when config OFF).
    - Archive ``docs/handoffs/archive/INDEX.md`` via the flat-table
      renderer.

    Returns ``{"main": "<text>", "archive": "<text>"}``.
    """
    main_idx = index.render_handoffs_index_with_rolling_collapse(
        repo_root=repo_root,
    )
    archive_dir = ledger_paths.compat_kind_dir(repo_root, "handoffs") / "archive"
    archive_idx = _render_archive_index(archive_dir)
    return {"main": main_idx, "archive": archive_idx}


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def run_aging_policy(
    repo_root: Path,
    *,
    config: dict[str, Any] | None = None,
    dry_run: bool = False,
    strategy_override: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Run the handoff aging policy end-to-end.

    Loads config from ``.claude/workshop-lite-config.toml`` when
    ``config`` is None. ``strategy_override`` (when non-None) replaces
    ``stub_collapse_strategy`` from config — the CLI ``--strategy`` flag
    routes through this.

    Returns a summary dict::

        {
            "detected": int,    # stubs eligible for collapse
            "archived": int,    # moved to docs/handoffs/archive/
            "merged":   int,    # cursor-chain folded into prev
            "deleted":  int,    # destructively removed
            "strategy": str,    # strategy in effect
            "dry_run":  bool,
        }

    ``dry_run=True`` reports ``detected`` only; never touches disk.
    """
    if config is None:
        config = index._handoffs_config(repo_root)

    handoffs_dir = ledger_paths.compat_kind_dir(repo_root, "handoffs")
    strategy = strategy_override or config["stub_collapse_strategy"]
    if strategy not in _VALID_STRATEGIES:
        raise ValueError(
            f"unknown stub_collapse_strategy: {strategy!r} "
            f"(expected one of {list(_VALID_STRATEGIES)})"
        )

    eligible = detect_stubs(
        handoffs_dir,
        empty_stub_age_hours=config["empty_stub_age_hours"],
        keep_recent_n=config["keep_recent_n_stubs"],
        now=now,
    )

    summary: dict[str, Any] = {
        "detected": len(eligible),
        "archived": 0,
        "merged": 0,
        "deleted": 0,
        "strategy": strategy,
        "dry_run": dry_run,
    }

    if dry_run or not eligible:
        return summary

    archive_dir = handoffs_dir / "archive"
    for stub in eligible:
        if strategy == "archive":
            collapse_archive(stub, archive_dir=archive_dir)
            summary["archived"] += 1
        elif strategy == "merge-into-prev":
            prev = collapse_merge_into_prev(stub)
            if prev is not None:
                summary["merged"] += 1
            else:
                summary["archived"] += 1  # archive-only fallback
        elif strategy == "delete":
            collapse_delete(stub)
            summary["deleted"] += 1

    update_index_after_collapse(repo_root)
    return summary
