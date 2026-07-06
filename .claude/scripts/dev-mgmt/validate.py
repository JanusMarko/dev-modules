"""Advisory validator for the lightweight dev-mgmt convention.

Sprint dev-mgmt.6 (D35 subset):

1. **Sprint folder coherence**  — every ``active/sprint-X/`` has plan.md +
   tasks.md; every ``archive/sprint-X/`` adds retro.md.
2. **INDEX coherence (per-kind)** — every entity file appears as a row in
   its INDEX.md and vice versa, for decisions/sprints/handoffs/issues/
   reviews/conversations. Per-entity-type INDEX shape is honoured via a
   dispatch table (`_INDEX_PARSERS`): markdown-table parsing for the
   classical flat entities; the bespoke §8 two-section list parser for
   ``wip`` (sub-spec §8 binding shape — verifier-α HIGH #1 closure).
3. **Frontmatter well-formed** — parse via :func:`frontmatter.parse`; if
   parse fails, warn. If parse succeeds, dispatch to the per-type
   validator from :mod:`validators` and convert any
   :class:`validators.ValidationError` into a list of
   :class:`WarningRecord` (the strict ``validators`` module stays
   unchanged per D8).

D36: only check 3 (the expensive per-file path) honours ``mtime_cutoff``.
Checks 1 + 2 are cheap (directory listing + INDEX parse) and always run.

Sprint dev-mgmt.7 additions (per D35.4 + D35.5 / D43 + D44):

4. **Cross-link resolution** (D43) — for every ``linked_<kind>`` field
   on every entity, check that the referenced slug exists on disk and
   (where the target has a matching reverse field) that the back-edge
   is recorded. Plus: ``linked_msg_ids`` checked against captured
   Conversation ``verbatim_msg_range`` per the §D43 second-bucket
   check. Delegated to :mod:`cross_links`; advisory-only (D44).

5. **Status-transition coverage** (D44) — per-type allowed-transitions
   matrix. (Track A step still gated on Track B's D47.5 record.)
"""
from __future__ import annotations

import fnmatch
import re
import sys
import time
from collections import namedtuple
from pathlib import Path
from typing import Callable

import cross_links
import denial as denial_mod
import dispatch_checks
import doc_drift_lint
import frontmatter
import handoff_aging
import index as index_mod
import ledger_paths
import sprint_spec
import validators
import wip_claim_checks


# WarningRecord is a 4-tuple; the trailing ``suppressed_by`` slot defaults
# to ``None``. When the wl-rearch §4.7 validator carve-out file matches a
# (path, rule) pair, ``_apply_carveout_suppression`` rebuilds the
# matching WarningRecord with ``suppressed_by = <reason-string>``; this
# demotes the warning to INFO presentation AND removes it from the
# ``--strict`` exit-code set (the CLI counts only ``suppressed_by is
# None`` records toward non-zero exit). Default-deny per D-WL-12.
#
# Backward compatibility: every existing call site passes 3 positional
# args; the namedtuple default for ``suppressed_by`` keeps those callers
# unchanged. Hard Rule 7: the matching rule is a binary structural
# (path, rule) compare — no judgment surface, no similarity scoring.
WarningRecord = namedtuple(
    "WarningRecord",
    ("category", "path", "message", "suppressed_by"),
    defaults=(None,),
)


# docs/<kind>/*.md → per-type validator (flat layout).
_FLAT_ENTITY_TYPES: dict[str, Callable[[dict], None]] = {
    "decisions":     validators.validate_decision,
    "handoffs":      validators.validate_handoff,
    "issues":        validators.validate_issue,
    "reviews":       validators.validate_review,
    "conversations": validators.validate_conversation,
    # Phase 1 of re-arch arc: WIP-claim joins the flat-layout entities.
    "wip":           validators.validate_wip_claim,
    # Phase 2 of re-arch arc: standing-dispatch joins the flat-layout
    # entities (sub-spec §3 + §6).
    "dispatches":    validators.validate_standing_dispatch,
    # workshop-lite cohort (B) install-rollout D1 / source-issue
    # 2026-06-04-01: gate entity at docs/gates/<gate-id>.md. Per
    # PG-3-corrected ratify msg-07f27ea3b964: gates ENTITY uses the
    # standard FLAT registry shape (INDEX.md generated; mirrors
    # decisions/issues/reviews) so stale-gate detection + state-grouped
    # discovery work via the existing INDEX-coherence check. halt
    # remains singleton at top-level HALT.md (no docs/halts/, no INDEX).
    "gates":         validators.validate_gate,
    # BC1.2 — the 5 new kinds (spec §2.3). Each lands in the flat ledger
    # layout (<dir>/<id>.md + INDEX.md). Directory names per ledger_paths.
    "workflows":      validators.validate_workflow,
    "role-sets":      validators.validate_role_set,
    "block-signals":  validators.validate_block_signal,
    "resume-ledgers": validators.validate_resume_ledger,
    "pointers":       validators.validate_canonical_pointer,
    # BC2.4 — denial/degrade envelope (spec §9). Lives in the flat ledger
    # layout (denials/<id>.md + INDEX.md). Validator owned by denial.py
    # (the canonical envelope module), not validators.py.
    "denials":        denial_mod.validate_denial,
    # BC2.3 — closure record (spec §11.3). Lifecycle sub-record (NOT a built-in
    # kind); flat layout closures/<id>.md + INDEX.md.
    "closures":       validators.validate_closure_record,
}

# Sprint folders use a different layout (plan.md / retro.md within
# active/ or archive/).
_SPRINT_FILE_VALIDATORS: dict[str, Callable[[dict], None]] = {
    "plan.md":  validators.validate_sprint_plan,
    "retro.md": validators.validate_retrospective,
}


def _validate_or_warn(
    fm: dict,
    validator_fn: Callable[[dict], None],
    path: Path,
) -> list[WarningRecord]:
    """Run a strict validator; convert any ValidationError into warnings.

    Used by D35.3 to dispatch frontmatter to the per-type validator without
    forcing the (strict, raises) :mod:`validators` API to change.
    """
    try:
        validator_fn(fm)
        return []
    except validators.ValidationError as exc:
        return [
            WarningRecord(
                category="frontmatter_validate",
                path=str(path),
                message=msg,
            )
            for msg in exc.errors
        ]


# ---------- D35.1 sprint folder coherence ----------

def _check_sprint_folders(repo_root: Path) -> list[WarningRecord]:
    warnings: list[WarningRecord] = []
    sprints_dir = ledger_paths.compat_sprints_dir(repo_root)
    if not sprints_dir.exists():
        return warnings

    for sub in ("active", "archive"):
        sub_dir = sprints_dir / sub
        if not sub_dir.exists():
            continue
        for sprint_dir in sorted(sub_dir.iterdir()):
            if not sprint_dir.is_dir():
                continue
            for required in ("plan.md", "tasks.md"):
                if not (sprint_dir / required).exists():
                    warnings.append(WarningRecord(
                        category="sprint_folder",
                        path=str(sprint_dir / required),
                        message=f"missing required file: {required}",
                    ))
            if sub == "archive" and not (sprint_dir / "retro.md").exists():
                warnings.append(WarningRecord(
                    category="sprint_folder",
                    path=str(sprint_dir / "retro.md"),
                    message="archived sprint missing retro.md",
                ))
    return warnings


# ---------- D35.2 INDEX coherence ----------

def _parse_index_ids(index_path: Path) -> set[str]:
    """Extract the first-column values (IDs) from an INDEX.md table.

    Tolerant of preamble/postamble text outside the table. The table is
    detected by a header row containing pipes; the separator row
    (``|---|---|``) is skipped; rows until the first non-pipe line are
    treated as data rows.
    """
    if not index_path.exists():
        return set()
    ids: set[str] = set()
    in_table = False
    for line in index_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            in_table = False
            continue
        if not stripped.startswith("|"):
            in_table = False
            continue
        # In-table: header / separator / data.
        if not in_table:
            # First pipe-prefixed line in this group is the header.
            in_table = True
            continue
        if set(stripped.replace("|", "").strip()) <= set("-: "):
            # Separator row.
            continue
        # Data row: first cell is the ID.
        cells = [c.strip() for c in stripped.split("|")[1:-1]]
        if cells and cells[0]:
            ids.add(cells[0])
    return ids


# WIP-claim INDEX entries match the §8 list-link shape:
#   - [<id>](<id>.md) — ...
# anchored at line start (possibly after leading whitespace). Anything
# matching the pattern in either the Active or Closed sections counts.
# The summary line + rolling-collapse line do NOT match (they don't carry
# an `[id](id.md)` shape).
_WIP_INDEX_ROW_RE = re.compile(
    r"^\s*-\s*\[(?P<id>[^\]]+)\]\((?P<file>[^)]+\.md)\)"
)


def _parse_wip_index_ids(index_path: Path) -> set[str]:
    """Extract WIP-claim ids from the bespoke sub-spec §8 INDEX layout.

    The §8 layout is a two-section markdown list (``## Active`` /
    ``## Closed``) with rows of shape ``- [<id>](<id>.md) — ...``.
    We accept any line matching that pattern and harvest the id.

    Verifier-α HIGH #1 closure: the classical markdown-table parser
    in :func:`_parse_index_ids` returns empty for this layout because
    the §8 shape has no pipe-prefixed rows; that produced a false-
    positive ``index_coherence`` warning per wip-claim file. This
    parser teaches the substrate the new shape.
    """
    if not index_path.exists():
        return set()
    ids: set[str] = set()
    for line in index_path.read_text(encoding="utf-8").splitlines():
        m = _WIP_INDEX_ROW_RE.match(line)
        if m is None:
            continue
        id_val = m.group("id").strip()
        if id_val:
            ids.add(id_val)
    return ids


# Handoffs INDEX accepts EITHER the classical table shape (rolling-collapse
# OFF, the default) OR the bespoke list shape (rolling-collapse ON, wl-rearch
# §4.6). Phase 1 Cycle 2 adds the union parser so coherence stays advisory
# regardless of which shape rendered the file. The rolling-collapse line
# `- LATEST-PRE-COMPACT-STUBS (...)` does NOT match the list-row regex and
# is intentionally treated as "(N stub ids deliberately not enumerated)" —
# the underlying handoff files stay on disk; the collapsed rows are NOT
# coherence-warnings because §4.6 binds presentation-collapse, not file-
# deletion. For the §4.6 presentation-collapse case, the collapsed stubs
# are EXPECTED to be absent from INDEX by design; the
# `_index_suppressed_slugs` hook below identifies them so
# `_check_flat_index` does NOT emit a spurious
# `file present but INDEX missing row` coherence warning.
_HANDOFF_INDEX_ROW_RE = re.compile(
    r"^\s*-\s*\[(?P<id>[^\]]+)\]\((?P<file>[^)]+\.md)\)"
)


def _parse_handoffs_index_ids(index_path: Path) -> set[str]:
    """Extract handoff ids from EITHER the classical table or the list
    shape (rolling-collapse mode per wl-rearch §4.6).

    Union semantics: try both parsers, merge results. The list-shape
    rolling-collapse line `- LATEST-PRE-COMPACT-STUBS (...)` carries no
    `[id](id.md)` pattern and is intentionally NOT enumerated — the
    underlying stub files stay on disk by §4.6 rule #4 but are
    deliberately suppressed from INDEX presentation.
    """
    ids = set(_parse_index_ids(index_path))
    if not index_path.exists():
        return ids
    for line in index_path.read_text(encoding="utf-8").splitlines():
        m = _HANDOFF_INDEX_ROW_RE.match(line)
        if m is not None:
            id_val = m.group("id").strip()
            if id_val:
                ids.add(id_val)
    return ids


# Dispatches INDEX (sub-spec §8) uses markdown tables whose first cell
# is ``[<id>](<id>.md)`` — a link, not a bare id. Extract the id via the
# same regex shape used for wip-claim, since both render IDs as markdown
# links rather than bare cells.
_DISPATCH_INDEX_ROW_RE = re.compile(
    r"\|\s*\[(?P<id>[^\]]+)\]\((?P<file>[^)]+\.md)\)\s*\|"
)


def _parse_dispatches_index_ids(index_path: Path) -> set[str]:
    """Extract standing-dispatch ids from the sub-spec §8 INDEX layout.

    §8 is a markdown table whose first cell is ``[<id>](<id>.md)``. The
    classical ``_parse_index_ids`` reads the cell verbatim (would return
    the bracketed link literal); this parser harvests just the id token.
    """
    if not index_path.exists():
        return set()
    ids: set[str] = set()
    for line in index_path.read_text(encoding="utf-8").splitlines():
        m = _DISPATCH_INDEX_ROW_RE.search(line)
        if m is None:
            continue
        id_val = m.group("id").strip()
        if id_val:
            ids.add(id_val)
    return ids


# Per-entity-type INDEX-id-parser dispatch. Default for entries absent
# from this table is the classical markdown-table parser.
_INDEX_PARSERS: dict[str, Callable[[Path], set[str]]] = {
    "wip": _parse_wip_index_ids,
    "handoffs": _parse_handoffs_index_ids,
    "dispatches": _parse_dispatches_index_ids,
}


def _index_suppressed_slugs(repo_root: Path, kind: str) -> set[str]:
    """Return on-disk slugs that are intentionally omitted from INDEX.

    Currently only applies to ``handoffs`` when wl-rearch §4.6 rolling-
    collapse is enabled in ``.claude/workshop-lite-config.toml`` — the
    collapsed empty pre-compact stubs are deliberately NOT enumerated
    in INDEX. Other kinds return empty set (no suppression).
    """
    if kind != "handoffs":
        return set()
    try:
        import index as _index_mod
        cfg = _index_mod._handoffs_config(repo_root)
    except Exception:
        return set()
    if not cfg.get("rolling_collapse"):
        return set()
    handoffs_dir = ledger_paths.compat_kind_dir(repo_root, "handoffs")
    if not handoffs_dir.exists():
        return set()
    suppressed: set[str] = set()
    try:
        import index as _index_mod
        from datetime import timedelta as _td
        cutoff_dt = _index_mod._utc_now() - _td(hours=cfg["empty_stub_age_hours"])
        # Identify all stubs; per §4.6 rule #3 the most-recent stub
        # stays in INDEX (full-form), so it is NOT suppressed.
        stubs: list[tuple[str, object]] = []
        for path in sorted(handoffs_dir.glob("*.md")):
            if path.name == "INDEX.md" or path.name.startswith("INDEX-"):
                continue
            try:
                fm, body = frontmatter.parse(path)
            except Exception:
                continue
            if not isinstance(fm, dict):
                continue
            if not _index_mod.is_empty_pre_compact_stub(fm, body):
                continue
            created_dt = _index_mod._parse_handoff_created_dt(
                fm, _index_mod._utc_now(),
            )
            stubs.append((path.stem, created_dt))
        if not stubs:
            return set()
        stubs.sort(key=lambda x: x[1])
        # Newest stub kept (rule #3); others older than cutoff suppressed.
        most_recent_slug = stubs[-1][0]
        for slug, dt in stubs[:-1]:
            if dt < cutoff_dt:
                suppressed.add(slug)
        # Always re-exclude the most-recent (defensive — won't be in
        # the older-than-cutoff set anyway).
        suppressed.discard(most_recent_slug)
    except Exception:
        return set()
    return suppressed


def _check_flat_index(
    repo_root: Path, kind: str,
) -> list[WarningRecord]:
    warnings: list[WarningRecord] = []
    target_dir = ledger_paths.compat_kind_dir(repo_root, kind)
    if not target_dir.exists():
        return warnings
    on_disk = {
        p.stem for p in target_dir.glob("*.md")
        if not cross_links.is_index_file(p)
    }
    index_path = target_dir / "INDEX.md"
    if not index_path.exists():
        if on_disk:
            warnings.append(WarningRecord(
                category="index_coherence",
                path=str(index_path),
                message=f"{kind}: INDEX.md missing but {len(on_disk)} file(s) present",
            ))
        return warnings
    parser = _INDEX_PARSERS.get(kind, _parse_index_ids)
    in_index = parser(index_path)
    # wl:2026-06-05-01 defense-in-depth: drop INDEX.md + INDEX-* sibling slugs
    # if a parser accidentally surfaces them as entity IDs. Mirrors
    # cross_links.is_index_file() exclusion semantics so an INDEX-archive row
    # in INDEX.md (regression or manual edit) doesn't emit a phantom
    # "INDEX row but no file" coherence warning.
    in_index = {s for s in in_index if s != "INDEX" and not s.startswith("INDEX-")}
    # Per-kind suppression hook: §4.6 rolling-collapse intentionally
    # omits empty pre-compact stubs from the handoffs INDEX presentation
    # (rule #4: files stay on disk; only INDEX presentation collapses).
    # Without this hook, every collapsed stub would emit a spurious
    # "file present but INDEX missing row" coherence warning.
    suppressed_on_disk: set[str] = _index_suppressed_slugs(repo_root, kind)
    for slug in sorted((on_disk - in_index) - suppressed_on_disk):
        warnings.append(WarningRecord(
            category="index_coherence",
            path=str(index_path),
            message=f"{kind}: file present but INDEX missing row: {slug}",
        ))
    for slug in sorted(in_index - on_disk):
        warnings.append(WarningRecord(
            category="index_coherence",
            path=str(index_path),
            message=f"{kind}: INDEX row but no file: {slug}",
        ))
    return warnings


def _check_sprint_index(repo_root: Path) -> list[WarningRecord]:
    warnings: list[WarningRecord] = []
    sprints_dir = ledger_paths.compat_sprints_dir(repo_root)
    if not sprints_dir.exists():
        return warnings
    index_path = sprints_dir / "INDEX.md"

    on_disk: set[str] = set()
    for sub in ("active", "archive"):
        sub_dir = sprints_dir / sub
        if not sub_dir.exists():
            continue
        for sd in sub_dir.iterdir():
            if sd.is_dir() and sd.name.startswith("sprint-"):
                on_disk.add(sd.name[len("sprint-"):])

    if not index_path.exists():
        if on_disk:
            warnings.append(WarningRecord(
                category="index_coherence",
                path=str(index_path),
                message=(
                    f"sprints: INDEX.md missing but {len(on_disk)} folder(s) present"
                ),
            ))
        return warnings

    in_index = _parse_index_ids(index_path)
    for sid in sorted(on_disk - in_index):
        warnings.append(WarningRecord(
            category="index_coherence",
            path=str(index_path),
            message=f"sprints: folder present but INDEX missing row: {sid}",
        ))
    for sid in sorted(in_index - on_disk):
        warnings.append(WarningRecord(
            category="index_coherence",
            path=str(index_path),
            message=f"sprints: INDEX row but no folder: {sid}",
        ))
    return warnings


def _check_index_coherence(repo_root: Path) -> list[WarningRecord]:
    warnings: list[WarningRecord] = []
    for kind in _FLAT_ENTITY_TYPES:
        warnings.extend(_check_flat_index(repo_root, kind))
    warnings.extend(_check_sprint_index(repo_root))
    warnings.extend(_check_index_manual_row_duplication(repo_root))
    return warnings


def _check_index_manual_row_duplication(
    repo_root: Path,
) -> list[WarningRecord]:
    """Detect duplicate manual rows in CURATED INDEX.md files.

    Cohort KK (wl:2026-06-06-09) — closes the validator-coverage gap that
    allowed the ``_extract_manual_rows`` cross-section contamination bug
    to ship undetected.

    Scope: ``docs/decisions/INDEX.md`` + ``docs/reviews/INDEX.md`` (the
    two CURATED INDEX classes that use ``preserve_manual_rows=True``).

    A **real manual row** is a line satisfying ALL of:

    1. Starts with ``|`` and not ``|--`` (markdown table row, not separator).
    2. ID column (cell 1 after split + strip) is empty — the pre-convention
       operator-annotated row shape.
    3. Contains at least one non-empty, non-dash, non-whitespace cell among
       the content columns (cells 2..N-1). Closes the markdown-table-
       separator (``|---|---|...``) false-positive class per charter-
       devil-advocate review 2026-06-06-05 MED finding (Amendment 1).

    Rows passing all three are grouped by their normalized (trailing-
    whitespace-stripped) content. Any group with count > 1 emits a
    ``manual_row_duplicate`` warning. Advisory at default; non-zero
    exit under ``--strict`` per D43 (no custom suppression hook —
    fall-through to the default strict-set membership).
    """
    warnings: list[WarningRecord] = []
    for kind in ("decisions", "reviews"):
        index_path = ledger_paths.compat_kind_dir(repo_root, kind) / "INDEX.md"
        if not index_path.exists():
            continue
        try:
            lines = index_path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        groups: dict[str, list[int]] = {}
        for lineno, raw_line in enumerate(lines, start=1):
            line = raw_line.rstrip()
            if not line.startswith("|") or line.startswith("|--"):
                continue
            cells = [c.strip() for c in line.split("|")]
            if len(cells) < 3:
                continue
            if cells[1] in ("ID", "id"):
                continue
            if cells[1] != "":
                continue
            content_cells = cells[2:-1] if cells and cells[-1] == "" else cells[2:]
            has_content = any(
                c and not all(ch == "-" or ch.isspace() for ch in c)
                for c in content_cells
            )
            if not has_content:
                continue
            groups.setdefault(line, []).append(lineno)
        for normalized, line_nos in groups.items():
            if len(line_nos) <= 1:
                continue
            preview = normalized[:60]
            warnings.append(WarningRecord(
                category="manual_row_duplicate",
                path=str(index_path),
                message=(
                    f"{kind}: manual row appears {len(line_nos)}× "
                    f"at lines [{', '.join(str(n) for n in line_nos)}]: "
                    f"{preview}..."
                ),
            ))
    return warnings


# ---------- D35.3 frontmatter parse + per-type validate ----------

def _within_mtime(path: Path, mtime_cutoff: int | None, now: float) -> bool:
    if mtime_cutoff is None:
        return True
    try:
        age = now - path.stat().st_mtime
    except OSError:
        return True
    return age <= mtime_cutoff


def _check_one_frontmatter(
    path: Path,
    validator_fn: Callable[[dict], None],
) -> list[WarningRecord]:
    try:
        fm, _body = frontmatter.parse(path)
    except Exception as exc:  # malformed frontmatter
        return [WarningRecord(
            category="frontmatter_parse",
            path=str(path),
            message=f"parse failed: {exc}",
        )]
    return _validate_or_warn(fm, validator_fn, path)


def _check_frontmatter(
    repo_root: Path, mtime_cutoff: int | None,
) -> list[WarningRecord]:
    warnings: list[WarningRecord] = []
    now = time.time()

    # Flat entity types (decisions/handoffs/issues/reviews/conversations).
    for kind, validator_fn in _FLAT_ENTITY_TYPES.items():
        kind_dir = ledger_paths.compat_kind_dir(repo_root, kind)
        if not kind_dir.exists():
            continue
        for path in sorted(kind_dir.glob("*.md")):
            if cross_links.is_index_file(path):
                continue
            if not _within_mtime(path, mtime_cutoff, now):
                continue
            warnings.extend(_check_one_frontmatter(path, validator_fn))

    # Sprints (plan.md + retro.md inside each sprint folder).
    sprints_dir = ledger_paths.compat_sprints_dir(repo_root)
    if sprints_dir.exists():
        for sub in ("active", "archive"):
            sub_dir = sprints_dir / sub
            if not sub_dir.exists():
                continue
            for sprint_dir in sorted(sub_dir.iterdir()):
                if not sprint_dir.is_dir():
                    continue
                for fname, fn in _SPRINT_FILE_VALIDATORS.items():
                    fpath = sprint_dir / fname
                    if not fpath.exists():
                        continue
                    if not _within_mtime(fpath, mtime_cutoff, now):
                        continue
                    warnings.extend(_check_one_frontmatter(fpath, fn))

    return warnings


# ---------- D35.5 status-transition coverage (D44 / D47.5) ----------

# Entity-kind → frontmatter status-field name. We treat all per-type
# kinds uniformly under the key 'status' in their frontmatter; the
# mapping is here for completeness and future-proofing (if a new kind
# adopts a custom field name, it slots in without touching the check
# body).
_STATUS_KINDS: dict[str, str] = {
    "decisions":   "decision",
    "issues":      "issue",
    "reviews":     "review",
    "wip":         "wip-claim",
    "dispatches":  "standing-dispatch",
    # workshop-lite cohort (B) install-rollout D1 (source-issue
    # 2026-06-04-01): gate carries status ∈ {open, closed, resolved}
    # per ``validators.STATUS_TRANSITIONS["gate"]``. halt intentionally
    # absent — no status field; the file's existence IS the halt state.
    "gates":       "gate",
    # BC1.2 — the 4 stateful new kinds. canonical-pointer is intentionally
    # absent (mutable-head, no status field).
    "workflows":      "workflow",
    "role-sets":      "role-set",
    "block-signals":  "block-signal",
    "resume-ledgers": "resume-ledger",
    # Sprint plans live under docs/sprints/active|archive/<id>/plan.md;
    # the per-file walk below handles them separately.
}


def _check_status_transitions(repo_root: Path) -> list[WarningRecord]:
    """Walk all entities; warn when the current status isn't a known
    state for the entity's type per ``validators.STATUS_TRANSITIONS``.

    D44 / D47.5: ALWAYS advisory. The pragmatic subset implemented here
    is "current-status-is-in-the-matrix" drift detection. Real
    transition enforcement (e.g., flagging Issue jumping ``open ->
    resolved`` without an ``investigating`` step) requires a
    ``status_history`` frontmatter field which the system doesn't yet
    have; once it does, the same matrix becomes enforceable end-to-end
    and this function expands. Today it catches:

    * typo'd status values (``status: completd`` or ``status: open?``)
    * schema drift (a type extends its status enum but the matrix
      didn't update — surfaces here as an unknown state)
    * cross-entity copy-paste (``status: shipped`` on a Decision, etc.)

    Conversation, Handoff, Retrospective are skipped (no status
    transition graph; status is invariant or absent — see
    ``validators.STATUS_TRANSITIONS`` comment).
    """
    warnings: list[WarningRecord] = []

    # Flat-dir entities (decisions/issues/reviews).
    for kind_dir, kind_key in _STATUS_KINDS.items():
        kind_path = ledger_paths.compat_kind_dir(repo_root, kind_dir)
        if not kind_path.exists():
            continue
        known = validators.known_statuses_for(kind_key)
        if known is None:
            continue  # type not in matrix; skip
        for path in sorted(kind_path.glob("*.md")):
            if cross_links.is_index_file(path):
                continue
            try:
                fm, _body = frontmatter.parse(path)
            except Exception:
                continue  # parse drift already surfaced by D35.3
            status = fm.get("status")
            if status is None:
                continue
            if status not in known:
                warnings.append(WarningRecord(
                    category="status_transition_out_of_band",
                    path=str(path),
                    message=(
                        f"{kind_key} status {status!r} is not a known state "
                        f"for type; allowed: {sorted(known)}"
                    ),
                ))

    # Sprint plans (nested layout).
    sprints_dir = ledger_paths.compat_sprints_dir(repo_root)
    if sprints_dir.exists():
        known = validators.known_statuses_for("sprint-plan")
        if known is not None:
            for sub in ("active", "archive"):
                sub_dir = sprints_dir / sub
                if not sub_dir.exists():
                    continue
                for sprint_dir in sorted(sub_dir.iterdir()):
                    if not sprint_dir.is_dir():
                        continue
                    plan_path = sprint_dir / "plan.md"
                    if not plan_path.exists():
                        continue
                    try:
                        fm, _body = frontmatter.parse(plan_path)
                    except Exception:
                        continue
                    status = fm.get("status")
                    if status is None:
                        continue
                    if status not in known:
                        warnings.append(WarningRecord(
                            category="status_transition_out_of_band",
                            path=str(plan_path),
                            message=(
                                f"sprint-plan status {status!r} is not a "
                                f"known state; allowed: {sorted(known)}"
                            ),
                        ))

    return warnings


# ---------- Rec #10 evidence_obligation (issue 2026-06-10-03) ----------

#: Provenance fields a claim-bearing entity should populate to satisfy
#: the evidence_obligation (design 2026-06-10-wl-layer-c §6). A claim is
#: provenance-complete when ANY of these is non-empty — citing the
#: originating chat message, a linked decision, or an external decision
#: ref all count as evidence. ``external_decision_refs`` is the
#: PARLEY-DEV-MGMT-INTEGRATION URI-prefix bidirection field; harmless
#: when absent (HR-1 — pure-frontmatter, no parley import).
_PROVENANCE_FIELDS = (
    "linked_msg_ids",
    "linked_decisions",
    "external_decision_refs",
)

#: Persona-mediated Review evaluative verdicts (validators
#: ``_REVIEW_DECISIONS_EVAL``). A generative-mode review carries
#: ``decision: N/A`` and is NOT a claim-verdict.
_REVIEW_VERDICT_DECISIONS = {"PROCEED", "AMEND", "RETHINK"}


def _has_provenance(fm: dict) -> bool:
    """True when at least one provenance field is present + non-empty."""
    for field in _PROVENANCE_FIELDS:
        val = fm.get(field)
        if val:  # non-empty list / non-empty string
            return True
    return False


def _decision_is_claim(fm: dict) -> bool:
    """A Decision makes a claim once it has a chosen option (its
    rationale-bearing resolution). Proposed/open stubs without a chosen
    option are not yet claims, so they carry no evidence obligation.
    """
    options = fm.get("options")
    if not isinstance(options, list):
        return False
    return any(
        isinstance(opt, dict) and opt.get("chosen") is True
        for opt in options
    )


def _review_is_claim(fm: dict) -> bool:
    """A Review makes a claim when it delivers a verdict.

    Two Review sub-schemas (DISCRIMINATOR-BY-SOURCE, see
    ``validators.validate_review``):

    * Persona-mediated (``persona_used`` present): evaluative-mode
      ``decision`` ∈ {PROCEED, AMEND, RETHINK} is the verdict;
      generative-mode (``decision: N/A``) is not.
    * Existing closed-enum path: a cross-check-resolution carries
      per-seat ``findings[].verdict`` (PASS/FAIL) — any finding with a
      ``verdict`` key is a delivered verdict.
    """
    decision = fm.get("decision")
    if decision in _REVIEW_VERDICT_DECISIONS:
        return True
    findings = fm.get("findings")
    if isinstance(findings, list):
        return any(
            isinstance(f, dict) and "verdict" in f
            for f in findings
        )
    return False


def _check_evidence_obligation(repo_root: Path) -> list[WarningRecord]:
    """Advisory: claim-bearing entities should carry evidence provenance.

    Rec #10 evidence_obligation (design
    ``2026-06-10-wl-layer-c-prompt-pack-render-seam.md`` §6; issue
    ``2026-06-10-03``). The audit half of the P+A fold: a Decision that
    reached a resolution (chosen option) or a Review that delivered a
    verdict is a *claim*; its authority should follow its provenance.
    When such an entity has every provenance field
    (:data:`_PROVENANCE_FIELDS`) empty, emit an advisory warning so the
    author is reminded to cite the evidence.

    STRICTLY ADVISORY — never a gate (HR-5/D33 hooks never block; D43
    ``--strict`` is the only non-zero exit). WL records + reminds;
    par-plan's seam weights authority. Full-pass only (run_checks wires
    this behind the ``mtime_cutoff is None`` branch — it walks every
    decision/review, too expensive for the Stop fast-path).
    """
    warnings: list[WarningRecord] = []
    claim_kinds = (
        ("decisions", "decision", _decision_is_claim),
        ("reviews", "review", _review_is_claim),
    )
    for kind_dir, kind_key, is_claim in claim_kinds:
        kind_path = ledger_paths.compat_kind_dir(repo_root, kind_dir)
        if not kind_path.exists():
            continue
        for path in sorted(kind_path.glob("*.md")):
            if cross_links.is_index_file(path):
                continue
            try:
                fm, _body = frontmatter.parse(path)
            except Exception:
                continue  # parse drift already surfaced by D35.3
            if not is_claim(fm):
                continue
            if _has_provenance(fm):
                continue
            warnings.append(WarningRecord(
                category="evidence_obligation_incomplete",
                path=str(path),
                message=(
                    f"{kind_key} makes a claim but carries no provenance; "
                    f"populate at least one of "
                    f"{list(_PROVENANCE_FIELDS)} so authority follows "
                    f"evidence (advisory)"
                ),
            ))
    return warnings


# ---------- Rec #14 memory_scope curate discipline (issue 2026-06-10-04) ----------

def _check_memory_curation(repo_root: Path) -> list[WarningRecord]:
    """Advisory: WL's durable entity corpus should be *curated*, not
    append-only accreted.

    Rec #14 memory_scope (design
    ``2026-06-10-wl-layer-c-prompt-pack-render-seam.md`` §7; issue
    ``2026-06-10-04``). The curator/E half: flag un-curated accretion so
    the librarian discipline (INDEX is the curated view, not the raw
    file list) is observable. The other accretion signals —
    stale INDEX rows, orphaned cross-links — already surface via
    :func:`_check_index_coherence` + :func:`_check_cross_links`. This
    check adds the remaining one: empty pre-compact handoff stubs aged
    past the fold threshold and not folded.

    Reuses the existing curation primitive (:func:`handoff_aging.detect_stubs`
    + :func:`index._handoffs_config`) — no new substrate code, just the
    audit surface. Non-destructive thresholds (default 24h age, keep the
    3 most-recent stubs full-form). STRICTLY ADVISORY (HR-5/D33 hooks
    never block; D43 ``--strict`` is the only non-zero exit). Full-pass
    only — walks the handoffs dir, too expensive for the Stop fast-path.
    """
    warnings: list[WarningRecord] = []
    handoffs_dir = ledger_paths.compat_kind_dir(repo_root, "handoffs")
    if not handoffs_dir.exists():
        return warnings
    cfg = index_mod._handoffs_config(repo_root)
    try:
        stale = handoff_aging.detect_stubs(
            handoffs_dir,
            empty_stub_age_hours=cfg["empty_stub_age_hours"],
            keep_recent_n=cfg["keep_recent_n_stubs"],
        )
    except Exception:
        return warnings  # advisory — never let curation audit raise
    for path in stale:
        warnings.append(WarningRecord(
            category="memory_scope_uncurated_handoff",
            path=str(path),
            message=(
                "empty pre-compact handoff stub aged past "
                f"{cfg['empty_stub_age_hours']}h and not folded; run "
                "`cli.py aging` to curate (INDEX is the curated view, "
                "not the raw file list) (advisory)"
            ),
        ))
    return warnings


# ---------- D35.4 cross-link resolution ----------

def _check_cross_links(repo_root: Path) -> list[WarningRecord]:
    """Run :mod:`cross_links` checks; adapt its ``WarningRecord`` shape.

    ``cross_links.WarningRecord`` is structurally identical to the one
    defined in this module (same ``(category, path, message)`` triple)
    but it's a distinct namedtuple class to avoid an import cycle
    between ``validate`` and ``cross_links``. We rebuild instances of
    our local ``WarningRecord`` so downstream consumers (``format_warnings``,
    the CLI, the validate-state hook) see a single uniform type.
    """
    raw = cross_links.run_cross_link_checks(repo_root)
    return [WarningRecord(w.category, w.path, w.message) for w in raw]


# ---------- doc-drift lint (charter 2026-05-23 item 3) ----------

def _check_doc_drift(repo_root: Path) -> list[WarningRecord]:
    """Run :mod:`doc_drift_lint` checks; adapt its ``WarningRecord`` shape.

    Opt-in by presence of ``<repo>/.claude/doc-drift-lint.toml``; absent
    config => empty list (silent skip). Same uniform WarningRecord
    rebuild as :func:`_check_cross_links`.
    """
    raw = doc_drift_lint.run_doc_drift_checks(repo_root)
    return [WarningRecord(w.category, w.path, w.message) for w in raw]


# ---------- §4.7 validator carve-out file ----------
#
# Per master design §4.7 (binding) + D-WL-5 (consolidated config path) +
# D-WL-12 (default-deny):
#
#   [[validator.ignore]]
#   path = '<exact-repo-relative-path>'    # OR
#   path_glob = '<fnmatch glob>'           # exactly one of {path, path_glob}
#   rule = '<WarningRecord.category>'      # non-empty
#   reason = '<human-readable reason>'     # non-empty
#
# Behavior: a WarningRecord whose (path, category) matches an entry is
# DEMOTED to INFO (rebuilt with ``suppressed_by=<reason>``); it stays in
# the returned list (still surfaces in stderr) but the CLI ``--strict``
# exit-code path counts only records with ``suppressed_by is None``.
#
# Default-deny (D-WL-12): only the explicit (path, rule) pair is
# suppressed; everything else flows through unchanged. No similarity
# scoring; binary structural compare (Hard Rule 7).
#
# Robustness (Hard Rule 5): config-absent / section-absent / malformed
# TOML / malformed entry => zero-suppression silent degrade; never raise.


def _load_carveout_entries(repo_root: Path) -> list[dict]:
    """Read ``[[validator.ignore]]`` entries from the consolidated config.

    Re-uses :func:`index._load_workshop_lite_config` (Cycle 2 helper) so
    the consolidated config file at ``<repo>/.claude/workshop-lite-config.toml``
    is the single source of truth. Returns ``[]`` on any failure (Hard
    Rule 5: never block).
    """
    try:
        import index as _index_mod
        cfg = _index_mod._load_workshop_lite_config(repo_root)
    except Exception:
        return []
    if not isinstance(cfg, dict):
        return []
    validator_section = cfg.get("validator")
    if not isinstance(validator_section, dict):
        return []
    entries = validator_section.get("ignore")
    if entries is None:
        return []
    if isinstance(entries, dict):
        # TOML ``[[validator.ignore]]`` with a single entry parses as a
        # list-of-dicts; ``[validator.ignore]`` (single inline table)
        # parses as a single dict. Accept both shapes; wrap the dict.
        entries = [entries]
    if not isinstance(entries, list):
        return []
    return [e for e in entries if isinstance(e, dict)]


def _entry_matches(entry: dict, path: str, category: str) -> bool:
    """Return True iff ``entry`` matches the given (path, category) pair.

    Schema gate: entry must have EXACTLY ONE of {path, path_glob} (both
    non-empty strings), AND a non-empty ``rule`` string, AND a non-empty
    ``reason`` string. Entries failing the gate match nothing (the
    caller logs INFO + skips them; see :func:`_apply_carveout_suppression`).

    Path normalisation: forward-slash. WarningRecord paths are already
    forward-slash because they're built from ``Path`` via ``str()``
    (POSIX); we still normalise here defensively.
    """
    if not _entry_valid(entry):
        return False
    rule = entry["rule"]
    if rule != category:
        return False
    norm_path = str(path).replace("\\", "/")
    has_path = "path" in entry and isinstance(entry.get("path"), str) and entry["path"]
    has_glob = "path_glob" in entry and isinstance(entry.get("path_glob"), str) and entry["path_glob"]
    if has_path:
        return _path_endswith_match(norm_path, entry["path"])
    if has_glob:
        return _glob_endswith_match(norm_path, entry["path_glob"])
    return False


def _entry_valid(entry: dict) -> bool:
    """Schema gate per §4.7: exactly one of {path, path_glob}; non-empty
    rule + reason strings. Bool-typed presence test.
    """
    has_path = bool(isinstance(entry.get("path"), str) and entry["path"])
    has_glob = bool(isinstance(entry.get("path_glob"), str) and entry["path_glob"])
    # Exactly one of {path, path_glob}.
    if has_path == has_glob:
        return False
    rule = entry.get("rule")
    if not (isinstance(rule, str) and rule):
        return False
    reason = entry.get("reason")
    if not (isinstance(reason, str) and reason):
        return False
    return True


def _path_endswith_match(record_path: str, entry_path: str) -> bool:
    """Exact-match an entry ``path`` against a WarningRecord path.

    WarningRecord paths come from ``str(Path)`` and may be absolute (the
    repo-root-prefixed form, e.g. ``/tmp/.../docs/handoffs/foo.md``)
    while the config ``path`` is repo-root-relative
    (``docs/handoffs/foo.md``). We accept the entry path as a
    repo-root-relative SUFFIX of the record path; this matches the §4.7
    example shape exactly.
    """
    rp = record_path.replace("\\", "/")
    ep = entry_path.replace("\\", "/").lstrip("/")
    if rp == ep:
        return True
    return rp.endswith("/" + ep)


def _glob_endswith_match(record_path: str, entry_glob: str) -> bool:
    """Glob-match an entry ``path_glob`` against a WarningRecord path.

    Same repo-root-relative semantics as the exact-match form: the glob
    is applied to the trailing repo-relative segment of the record path
    (so ``docs/decisions/2026-05-17-1?-*-canonical.md`` matches the
    record's repo-relative tail). ``fnmatch.fnmatch`` is per-segment;
    ``**`` is NOT supported (out of scope per brief).
    """
    rp = record_path.replace("\\", "/")
    gp = entry_glob.replace("\\", "/").lstrip("/")
    # Direct match first (covers config-supplied absolute-style entries).
    if fnmatch.fnmatch(rp, gp):
        return True
    # Match against the repo-root-relative tail. We can't know the
    # repo_root from inside the WarningRecord, but we can match any
    # suffix of the record path that equals the glob shape.
    parts = rp.split("/")
    for i in range(len(parts)):
        suffix = "/".join(parts[i:])
        if fnmatch.fnmatch(suffix, gp):
            return True
    return False


def _apply_carveout_suppression(
    warnings: list[WarningRecord],
    entries: list[dict],
    *,
    log_stream=None,
) -> list[WarningRecord]:
    """Apply ``[[validator.ignore]]`` rules per master §4.7 (binding).

    For each :class:`WarningRecord`, check whether its ``(path,
    category)`` matches any entry. If matched, rebuild the record with
    ``suppressed_by = entry['reason']`` (demotes to INFO presentation
    AND removes from the ``--strict`` exit-code set; see
    :func:`format_warnings` + the CLI ``validate`` subcommand).

    Schema-malformed entries (both / neither of {path, path_glob}, or
    missing/empty rule/reason): log INFO to ``log_stream`` and SKIP the
    entry; do NOT raise (Hard Rule 5: validator never blocks).

    Default-deny (D-WL-12): an entry without an exact (path, rule)
    match passes through unchanged.

    Hard Rule 7: matching is BINARY STRUCTURAL — exact string compare
    or ``fnmatch.fnmatch`` glob compare. Never a judgment surface.
    """
    if log_stream is None:
        log_stream = sys.stderr
    if not entries:
        return list(warnings)
    valid_entries: list[dict] = []
    for entry in entries:
        if not _entry_valid(entry):
            # INFO log + skip; do NOT crash. Hard Rule 5.
            log_stream.write(
                "[validator-carveout-info] skipping malformed "
                "[[validator.ignore]] entry: "
                f"{entry!r}\n"
            )
            continue
        valid_entries.append(entry)
    if not valid_entries:
        return list(warnings)
    out: list[WarningRecord] = []
    for w in warnings:
        # Already-suppressed records pass through (idempotent).
        if w.suppressed_by is not None:
            out.append(w)
            continue
        matched_reason: str | None = None
        for entry in valid_entries:
            if _entry_matches(entry, w.path, w.category):
                matched_reason = entry["reason"]
                break
        if matched_reason is None:
            out.append(w)
        else:
            out.append(WarningRecord(
                category=w.category,
                path=w.path,
                message=w.message,
                suppressed_by=matched_reason,
            ))
    return out


# ---------- public entrypoint ----------

def run_checks(
    repo_root: str | Path,
    mtime_cutoff: int | None = None,
    *,
    only_check: str | None = None,
    end_sprint_id: str | None = None,
) -> list[WarningRecord]:
    """Run all Sprint 6 advisory checks against ``repo_root``.

    D35.1 (sprint folder coherence) + D35.2 (INDEX coherence) ALWAYS run —
    they're cheap and the always-on drift signal is the point.
    D35.3 (frontmatter parse + per-type validate) honours ``mtime_cutoff``
    if set (the Stop-hook fast-path; D36 default = 300s); pass ``None`` for
    full validation (the on-demand ``dev-mgmt validate`` CLI path).

    The ``strict`` knob (exit-non-zero-on-any-warning) is a CLI-layer
    concern; this function always returns the full warning list regardless.

    Phase 1 Cycle 3 (wl-rearch §4.7): after collecting all warnings, the
    ``[[validator.ignore]]`` carve-out file (consolidated
    ``<repo>/.claude/workshop-lite-config.toml``, ``[validator.ignore]``
    array-of-tables section) is applied. Matched records are DEMOTED
    via :func:`_apply_carveout_suppression` (rebuilt with
    ``suppressed_by=<reason>``); they stay in the returned list (still
    surface in output) but the CLI counts them as INFO not WARN for
    ``--strict`` exit. Config-absent => zero suppression (regression
    free; existing behavior preserved).
    """
    repo_root = Path(repo_root)
    warnings: list[WarningRecord] = []

    # Phase 3: ``--check sprint-specs`` mode runs ONLY the spec.yaml
    # validators (V1-V8) and skips every other collector. The
    # ``/end-sprint`` skill uses this path with ``--strict --sprint <id>``
    # to gate sprint-close without dragging in unrelated drift signals.
    if only_check == "sprint-specs":
        warnings.extend(
            _check_sprint_specs(repo_root, end_sprint_id=end_sprint_id)
        )
        entries = _load_carveout_entries(repo_root)
        warnings = _apply_carveout_suppression(warnings, entries)
        return warnings

    warnings.extend(_check_sprint_folders(repo_root))
    warnings.extend(_check_index_coherence(repo_root))
    warnings.extend(_check_frontmatter(repo_root, mtime_cutoff))
    # workshop-lite cohort (B) install-rollout D1 (source-issue
    # 2026-06-04-01 § "The pattern"): top-level HALT.md singleton scan.
    # The halt entity lives at the repo root (NOT under docs/) to be
    # max-discoverable on ``ls``; validator extension to scan repo-root
    # alongside the docs/**/ flat-entity scan.
    warnings.extend(_check_halt_md(repo_root, mtime_cutoff))
    # D34: cross-link walk + status-transition walk are too expensive
    # for every-Stop fast path; skip when an mtime cutoff is in play
    # (the Stop-hook passes one; on-demand ``dev-mgmt validate`` doesn't).
    if mtime_cutoff is None:
        warnings.extend(_check_cross_links(repo_root))
        warnings.extend(_check_status_transitions(repo_root))
        # Rec #10 evidence_obligation (issue 2026-06-10-03): advisory
        # provenance-completeness audit on claim-bearing entities. Full
        # pass only — walks every decision/review.
        warnings.extend(_check_evidence_obligation(repo_root))
        # Rec #14 memory_scope (issue 2026-06-10-04): advisory curate
        # audit — un-folded aged pre-compact handoff stubs. Full pass
        # only — walks the handoffs dir.
        warnings.extend(_check_memory_curation(repo_root))
        warnings.extend(_check_doc_drift(repo_root))
        warnings.extend(_check_wip_claims(repo_root))
        # Phase 3: spec.yaml checks always run in the full pass (cheap
        # — only scans active sprint folders that opted in to spec.yaml).
        warnings.extend(
            _check_sprint_specs(repo_root, end_sprint_id=end_sprint_id)
        )
        # Phase 2 Cycle 1: standing-dispatch V1-V6 checks (parley-coupled
        # inputs handed in at skill/hook layer; library-side runs with None).
        warnings.extend(_check_standing_dispatches(repo_root))
    # §4.7 carve-out application — last step, after every collector has
    # contributed. Default-deny on miss; INFO demote on match.
    entries = _load_carveout_entries(repo_root)
    warnings = _apply_carveout_suppression(warnings, entries)
    return warnings


def _check_halt_md(
    repo_root: Path, mtime_cutoff: int | None,
) -> list[WarningRecord]:
    """Top-level ``HALT.md`` singleton scan (cohort B D1 / source-issue
    2026-06-04-01 § "The pattern").

    Singleton at the repo root (NOT under ``docs/``) — max-discoverable
    on ``ls``. When present, parse frontmatter + run
    :func:`validators.validate_halt`; surface any schema-validation
    errors as ``frontmatter_validate`` warnings (uniform with the
    ``_check_frontmatter`` flat-dir handling).

    Missing ``HALT.md`` is the common case — empty list, zero overhead.

    The presence of a valid ``HALT.md`` itself is NOT a validator
    warning — that's the parley-side halt_detection_loop
    (workshop-lite:2026-06-04-02 / D2)'s job to detect + surface to
    CTO. The validator's role here is strictly schema-fit: if a halted
    agent wrote a malformed HALT.md, the validator helps the operator
    spot it before treating it as a coordination signal.
    """
    warnings: list[WarningRecord] = []
    halt_path = repo_root / "HALT.md"
    if not halt_path.exists():
        return warnings
    now = time.time()
    if not _within_mtime(halt_path, mtime_cutoff, now):
        return warnings
    warnings.extend(
        _check_one_frontmatter(halt_path, validators.validate_halt)
    )
    return warnings


def _check_wip_claims(repo_root: Path) -> list[WarningRecord]:
    """Run :mod:`wip_claim_checks` V1-V5; adapt its WarningRecord shape.

    Roster is not supplied here (lib-layer Hard Rule 1) — V1 ORPHANED
    is silently skipped. The skill / hook layer is the path that hands
    in a roster set from ``parley roster --json``.
    """
    raw = wip_claim_checks.run_wip_claim_checks(repo_root)
    return [WarningRecord(w.category, w.path, w.message) for w in raw]


def _check_sprint_specs(
    repo_root: Path,
    *,
    end_sprint_id: str | None = None,
) -> list[WarningRecord]:
    """Run :mod:`sprint_spec` V1-V8 checks; adapt its WarningRecord shape.

    Phase 3 (sub-spec ``2026-05-29-wl-sprint-spec-yaml.md``). Optional —
    only sprints with a ``spec.yaml`` sidecar contribute warnings.
    """
    raw = sprint_spec.run_sprint_spec_checks(
        repo_root, end_sprint_id=end_sprint_id,
    )
    return [WarningRecord(w.category, w.path, w.message) for w in raw]


def _check_standing_dispatches(repo_root: Path) -> list[WarningRecord]:
    """Run :mod:`dispatch_checks` V1-V6; adapt its WarningRecord shape.

    Parley-dependent inputs (roster / delivery_state / known_msg_ids)
    are NOT supplied here per Hard Rule 1 — V1 / V5 / V6 silently skip
    when their input is None. The skill / hook layer (sub-spec §10.1)
    is the path that queries parley and hands the data in.
    """
    raw = dispatch_checks.run_standing_dispatch_checks(repo_root)
    return [WarningRecord(w.category, w.path, w.message) for w in raw]


def format_warnings(warnings: list[WarningRecord]) -> str:
    """Render warnings as a multi-line human-readable block.

    Used by the CLI wrapper to write to stderr; also useful for hook
    integration tests (subprocess captures formatted stderr).

    §4.7 carve-out: records with ``suppressed_by`` set are rendered
    with an ``INFO`` prefix (instead of the implicit WARN) and the
    suppression reason inlined. They still surface — D-WL-12
    visibility — but the CLI strict-exit gate counts only the WARN
    subset.
    """
    if not warnings:
        return ""
    lines = []
    for w in warnings:
        if w.suppressed_by is not None:
            lines.append(
                f"[INFO/{w.category}] {w.path}: {w.message} "
                f"[suppressed_by: {w.suppressed_by}]"
            )
        else:
            lines.append(f"[{w.category}] {w.path}: {w.message}")
    return "\n".join(lines) + "\n"


def strict_exit_warnings(warnings: list[WarningRecord]) -> list[WarningRecord]:
    """Return the subset of warnings that contribute to ``--strict`` exit.

    §4.7: records demoted via the carve-out (``suppressed_by`` set) do
    NOT contribute to the non-zero exit code. Default-deny: everything
    else contributes.

    Phase 3 (sub-spec §4.1): ``spec-yaml-*`` warnings are advisory by
    default; only the four ERROR-severity spec-yaml categories
    (``sprint_spec.STRICT_CATEGORIES``) contribute to ``--strict`` exit.
    Non-``spec-yaml-*`` categories retain the legacy behavior (everything
    not suppressed contributes).
    """
    out: list[WarningRecord] = []
    for w in warnings:
        if w.suppressed_by is not None:
            continue
        if w.category.startswith("spec-yaml-"):
            if not sprint_spec.is_strict_category(w.category):
                continue
        out.append(w)
    return out
