"""Atomic re-render of an entity-type INDEX.md by scanning the directory.

Sprint 1 shipped a decisions-only renderer. Sprint 2 generalizes to multiple
entity types via the ``columns`` and ``scanner`` parameters; existing
decisions callers migrate to ``render(d, title=..., columns=DECISION_COLUMNS)``.
"""
from __future__ import annotations

from pathlib import Path

import frontmatter

import cross_links
import ledger_paths


def _escape_cell(value: object) -> str:
    """Escape pipe characters so they don't break the markdown table row."""
    return str(value).replace("|", "\\|")


def _default_glob(target_dir: Path) -> list[Path]:
    """Default scanner: flat ``*.md`` glob, excluding INDEX.md + INDEX-* siblings.

    Uses ``cross_links.is_index_file`` so the exclusion contract here matches
    the validator + cross-link discovery sites (wl:2026-06-05-01: prior
    ``p.name != "INDEX.md"`` filter let ``INDEX-archive.md`` leak into entity
    discovery, generating a phantom ``INDEX-archive`` data row in INDEX.md).
    """
    return [
        p for p in sorted(target_dir.glob("*.md"))
        if not cross_links.is_index_file(p)
    ]


def sprint_paths(sprints_dir: Path) -> list[Path]:
    """Scan ``sprints_dir/{active,archive}/sprint-*/`` for a row source.

    Prefers ``plan.md``; falls back to ``retro.md`` for legacy sprints that
    pre-date the ``/start-sprint`` skill and never had a plan.md written.
    Sprint folders with neither file are silently skipped.
    """
    paths: list[Path] = []
    for sub in ("active", "archive"):
        sub_dir = sprints_dir / sub
        if not sub_dir.exists():
            continue
        for sprint_dir in sorted(sub_dir.iterdir()):
            if not sprint_dir.is_dir():
                continue
            plan_path = sprint_dir / "plan.md"
            if plan_path.exists():
                paths.append(plan_path)
                continue
            retro_path = sprint_dir / "retro.md"
            if retro_path.exists():
                paths.append(retro_path)
    return paths


def _sprint_status(_v, _fm, path: Path) -> str:
    return "archived" if "archive" in path.parts else "active"


def _sprint_stage(_v, _fm, path: Path) -> str:
    retro = path.parent / "retro.md"
    if "archive" in path.parts or retro.exists():
        return "retro"
    return "execute"


def _sprint_shipped(_v, _fm, path: Path) -> str:
    retro = path.parent / "retro.md"
    if retro.exists():
        try:
            rfm, _body = frontmatter.parse(retro)
            return str(rfm.get("shipped_at") or "")[:10]
        except Exception:
            return ""
    return ""


def _plain(value: object, _fm: dict, _path: Path) -> str:
    # Resolves Issue 2026-05-14-04: handoff INDEX (which uses _plain for Sprint/Stage)
    # previously rendered "?" for missing fields, while sprint INDEX rendered blank
    # via its own dedicated transforms. Standardize blank-for-missing across all
    # INDEX renderers so a missing-field cell is visually consistent regardless of
    # entity type.
    return str(value) if value not in (None, "") else ""


def _date_only(value: object, _fm: dict, _path: Path) -> str:
    return str(value or "")[:10]


def _derive_fm_from_filename(path: Path) -> dict:
    """Best-effort frontmatter from filename for files without a parseable header.

    par:2026-06-04-13 cohort D D2 — legacy handoff files (pre-frontmatter-
    schema era, ~Sprint 1-9 of parley) have no YAML header. EXHAUSTIVE
    INDEX rendering still needs a row per file. Derives:

    - ``id`` ← filename stem (e.g. ``2026-05-08-1430-phase-1-skeleton``)
    - ``title`` ← derived from slug (date+time prefix stripped, dashes → spaces)
    - ``created_at`` ← date prefix from filename if present, else empty

    Other entity-type fields are left absent (column transforms render
    blank for missing fields). The fallback is intentionally minimal:
    it surfaces EXISTENCE in the INDEX without inventing data the file
    doesn't carry.
    """
    import re as _re_local
    stem = path.stem
    date_re = _re_local.compile(r"^(\d{4}-\d{2}-\d{2})(?:[-T]|$)")
    date_match = date_re.match(stem)
    if date_match:
        created_at = date_match.group(1)
        slug_remainder = stem[date_match.end():].lstrip("-_")
    else:
        created_at = ""
        slug_remainder = stem
    # Strip leading HHMM time component if present (older handoffs encode
    # time as 4-digit segment after date), then convert dashes to spaces.
    title_slug = _re_local.sub(r"^\d{4}-", "", slug_remainder).replace("-", " ")
    return {
        "id": stem,
        "title": title_slug or stem,
        "created_at": created_at,
    }


DECISION_COLUMNS = [
    ("ID", "id", _plain),
    ("Title", "title", _plain),
    ("Status", "status", _plain),
    ("Scope", "scope", _plain),
    ("Created", "created_at", _date_only),
]

SPRINT_COLUMNS = [
    ("ID", "sprint_id", _plain),
    ("Title", "title", _plain),
    ("Status", None, _sprint_status),
    ("Stage", None, _sprint_stage),
    ("Created", "created_at", _date_only),
    ("Shipped", None, _sprint_shipped),
]

HANDOFF_COLUMNS = [
    ("ID", "id", _plain),
    ("Title", "title", _plain),
    ("Topic", "topic", _plain),
    ("Sprint", "sprint_id", _plain),
    ("Stage", "stage", _plain),
    ("Trigger", "trigger", _plain),
    ("Created", "created_at", _date_only),
]


def _findings_count(value: object, _fm: dict, _path: Path) -> str:
    """Render a Review's findings list as its length.

    Empty list renders as ``"0"``. Used by ``REVIEW_COLUMNS``'s Findings cell
    so the INDEX shows a count rather than the literal list.
    """
    if value is None:
        return "0"
    if isinstance(value, list):
        return str(len(value))
    return "?"


ISSUE_COLUMNS = [
    ("ID", "id", _plain),
    ("Title", "title", _plain),
    ("Status", "status", _plain),
    ("Severity", "severity", _plain),
    ("Scope", "scope", _plain),
    ("Created", "created_at", _date_only),
]

REVIEW_COLUMNS = [
    ("ID", "id", _plain),
    ("Title", "title", _plain),
    ("Type", "review_type", _plain),
    ("Status", "status", _plain),
    ("Scope", "scope", _plain),
    ("Findings", "findings", _findings_count),
    ("Created", "created_at", _date_only),
]


def _participants_count(value: object, _fm: dict, _path: Path) -> str:
    """Render a Conversation's participants list as its length.

    Empty list renders as ``"0"``. Used by ``CONVERSATION_COLUMNS``'s
    Participants cell so the INDEX shows a count rather than the literal list.
    """
    if value is None:
        return "0"
    if isinstance(value, list):
        return str(len(value))
    return "?"


CONVERSATION_COLUMNS = [
    ("ID", "id", _plain),
    ("Title", "title", _plain),
    ("Topic", "topic", _plain),
    ("Zone", "zone", _plain),
    ("Sprint", "sprint_id", _plain),
    ("Participants", "participants", _participants_count),
    ("Created", "created_at", _date_only),
]

# EpicShipped INDEX columns (Phase 2 re-arch arc, sub-spec
# `docs/design/2026-05-29-wl-sync-from-parley-spec.md` §5.4).
EPIC_SHIPPED_COLUMNS = [
    ("ID", "id", _plain),
    ("Title", "title", _plain),
    ("Status", "status", _plain),
    ("Scope", "scope", _plain),
    ("Shipped", "shipped_at", _date_only),
]


def _stage_count(value: object, _fm: dict, _path: Path) -> str:
    if isinstance(value, list):
        return str(len(value))
    return "0"


# BC1.2 — INDEX columns for the 5 new kinds (spec §2.3).
WORKFLOW_COLUMNS = [
    ("ID", "id", _plain),
    ("Title", "title", _plain),
    ("Status", "status", _plain),
    ("Layer", "library_layer", _plain),
    ("Stages", "stages", _stage_count),
    ("Default", "is_default", _plain),
    ("Created", "created_at", _date_only),
]

ROLE_SET_COLUMNS = [
    ("ID", "id", _plain),
    ("Title", "title", _plain),
    ("Status", "status", _plain),
    ("Layer", "library_layer", _plain),
    ("Roles", "roles", _stage_count),
    ("Default", "is_default", _plain),
    ("Created", "created_at", _date_only),
]

BLOCK_SIGNAL_COLUMNS = [
    ("ID", "id", _plain),
    ("Subject", "blocked_subject", _plain),
    ("Class", "class", _plain),
    ("Status", "status", _plain),
    ("Waits on", "waits_on", _plain),
    ("Created", "created_at", _date_only),
]

RESUME_LEDGER_COLUMNS = [
    ("ID", "id", _plain),
    ("Worker", "worker", _plain),
    ("Status", "status", _plain),
    ("Created", "created_at", _date_only),
]

DENIAL_COLUMNS = [
    ("ID", "id", _plain),
    ("Subject", "denied_subject", _plain),
    ("Class", "denial_class", _plain),
    ("From", "from_state", _plain),
    ("Resolution", "resolution", _plain),
    ("Created", "created_at", _date_only),
]

CLOSURE_COLUMNS = [
    ("ID", "id", _plain),
    ("Task", "task_ref", _plain),
    ("Disposition", "disposition", _plain),
    ("Closed by", "closed_by", _plain),
    ("Closed", "closed_at", _date_only),
]

CANONICAL_POINTER_COLUMNS = [
    ("ID", "id", _plain),
    ("Names", "names", _plain),
    ("Points to", "points_to", _plain),
    ("Updated", "updated_at", _date_only),
]


# ---------------------------------------------------------------------------
# CURATED render — par:2026-06-04-13 cohort D D2 (C) HYBRID policy
# ---------------------------------------------------------------------------
#
# Operator-dashboard render for entity classes that benefit from active/
# archive separation (decisions, reviews, workshop-lite decisions).
#
# Policy (par-plan PG-4 ratified amend msg-a70f8f71c495):
#   - Sort by created_at DESC; tie-break by id-lex DESC (stable across
#     re-renders).
#   - INDEX.md: top (active_cap + archive_window) rows; default 30 active
#     + 10 most-recent archived = 40-row cap.
#   - INDEX-archive.md: ALL rows past the active_cap threshold, sorted
#     ASC (oldest first per convention); always written even when empty
#     (uniform substrate state).
#   - INDEX.md footer links to INDEX-archive.md.
#
# Optional features:
#   - exclude_patterns: filename globs to skip (e.g. ('*.canonical.md',)
#     for parley/docs/decisions where canonical-projection siblings are
#     silent — row per ORIGINAL only per cohort C precedent).
#   - preserve_manual_rows: parse the existing INDEX.md for rows with an
#     empty ID column (pre-frontmatter-schema operator annotations) and
#     prepend them to the regenerated INDEX. Per chunk-0 PG-3 ratified:
#     "preserve as-is; append file-backed rows alongside without
#     rewriting" — workshop-lite/docs/decisions has 5 such rows from the
#     pre-D14 era.


def _curated_sort_key(meta: tuple) -> tuple:
    """Sort key for CURATED render: (created_at DESC, id DESC) via tuple negation trick.

    Python's sorted() with reverse=True applies to ALL key components.
    For the (created_at DESC, id DESC) joint ordering we therefore just
    sort by (created_at, id) tuple with reverse=True — both components
    flip together, which is the desired tie-break direction (newer
    created_at wins; on tie, lex-greater id wins).
    """
    return (meta[0], meta[1])


def render_curated(
    target_dir,
    *,
    title: str,
    columns,
    scanner=None,
    active_cap: int = 30,
    archive_window: int = 10,
    exclude_patterns: tuple = (),
    preserve_manual_rows: bool = False,
) -> None:
    """Re-render ``target_dir/INDEX.md`` + ``INDEX-archive.md`` per CURATED policy.

    See module-level doctrine comment. Atomic via tmp+rename for each
    output file. Caller owns the column schema (same shape as
    ``render()``).
    """
    import fnmatch as _fnmatch
    target_dir = Path(target_dir)

    # Capture manual rows BEFORE re-rendering (operator-annotated
    # headerless rows from pre-frontmatter-schema era).
    manual_rows: list[str] = []
    if preserve_manual_rows:
        manual_rows = _extract_manual_rows(target_dir / "INDEX.md")

    paths = (scanner or _default_glob)(target_dir)
    if exclude_patterns:
        paths = [
            p for p in paths
            if not any(_fnmatch.fnmatch(p.name, pat) for pat in exclude_patterns)
        ]

    # Build metadata tuples: (created_at_iso, id, cells)
    metas: list[tuple[str, str, list[str]]] = []
    for path in paths:
        try:
            fm, _body = frontmatter.parse(path)
        except Exception:
            fm = _derive_fm_from_filename(path)
        if not isinstance(fm, dict):
            fm = _derive_fm_from_filename(path)
        cells: list[str] = []
        for _header, fm_field, transform in columns:
            value = fm.get(fm_field) if fm_field is not None else None
            cells.append(_escape_cell(transform(value, fm, path)))
        # Sort keys: prefer fm['created_at'], fall back to filename date.
        created_iso = str(fm.get("created_at") or "")
        if not created_iso:
            stem = path.stem
            if len(stem) >= 10 and stem[4] == "-" and stem[7] == "-":
                created_iso = stem[:10]
        entity_id = str(fm.get("id") or path.stem)
        metas.append((created_iso, entity_id, cells))

    # Sort: (created_at DESC, id DESC) — tuple sort with reverse=True
    # flips both axes (PG-4 amend tie-break direction).
    metas.sort(key=_curated_sort_key, reverse=True)

    # Partition.
    cap_total = active_cap + archive_window
    main_metas = metas[:cap_total]
    archive_metas = metas[active_cap:]  # positions 31+ go into archive file

    headers = [h for h, _, _ in columns]
    sep_line = "|" + "|".join("-" * (len(h) + 2) for h in headers) + "|"
    header_line = "| " + " | ".join(headers) + " |"

    # Write INDEX.md (top-40 + manual rows + footer link)
    main_lines = [f"# {title}", ""]
    if manual_rows:
        main_lines.append(
            "<!-- pre-convention operator-annotated rows preserved per "
            "cohort D D2 PG-3 ratify -->"
        )
        main_lines.append(header_line)
        main_lines.append(sep_line)
        main_lines.extend(manual_rows)
        main_lines.append("")
        main_lines.append("## File-backed entries (top-40 by created_at)")
        main_lines.append("")
    main_lines.append(header_line)
    main_lines.append(sep_line)
    for _, _, cells in main_metas:
        main_lines.append("| " + " | ".join(cells) + " |")
    main_lines.append("")
    main_lines.append(
        f"> Older entries archived to [INDEX-archive.md](INDEX-archive.md) "
        f"(CURATED top-{active_cap}+{archive_window} cap; "
        f"{len(metas)} total file-backed entries).",
    )
    main_lines.append("")

    target_dir.mkdir(parents=True, exist_ok=True)
    index_path = target_dir / "INDEX.md"
    tmp = index_path.with_suffix(index_path.suffix + ".tmp")
    tmp.write_text("\n".join(main_lines), encoding="utf-8")
    tmp.replace(index_path)

    # Write INDEX-archive.md (ALL rows past active_cap, oldest first)
    archive_lines = [
        f"# {title} — archive",
        "",
        f"Entries past the CURATED top-{active_cap} cap, ordered "
        "oldest-first. New entries rotate in via the auto-rotation hook "
        "on each /record-* skill invocation (par:2026-06-04-13 cohort D "
        "D2 skill-hook wires).",
        "",
    ]
    if archive_metas:
        archive_lines.append(header_line)
        archive_lines.append(sep_line)
        # Sort ASC (oldest first) for archive convention.
        for _, _, cells in sorted(
            archive_metas,
            key=_curated_sort_key,
            reverse=False,
        ):
            archive_lines.append("| " + " | ".join(cells) + " |")
    else:
        archive_lines.append("(none archived — total entries within active cap)")
    archive_lines.append("")
    archive_lines.append(
        "← Back to [INDEX.md](INDEX.md) for the active dashboard view.",
    )
    archive_lines.append("")

    archive_path = target_dir / "INDEX-archive.md"
    atmp = archive_path.with_suffix(archive_path.suffix + ".tmp")
    atmp.write_text("\n".join(archive_lines), encoding="utf-8")
    atmp.replace(archive_path)


# Prefix of the HTML comment marker that `render_curated` emits at the
# head of the pre-convention manual-row section (see line ~339). Match by
# prefix so the marker text can evolve (e.g. ratify-anchor renames) without
# breaking extraction. Cohort KK fix: section-boundary anchor.
_MANUAL_ROW_SECTION_MARKER_PREFIX = (
    "<!-- pre-convention operator-annotated rows preserved"
)


def _extract_manual_rows(index_path: Path) -> list[str]:
    """Parse existing INDEX.md + return rows from the pre-convention manual
    section.

    Pre-convention operator-annotated rows: filename-less doctrine titles
    captured in the INDEX without backing entity files. Preserved across
    re-renders per cohort D D2 PG-3 ratify (msg-a70f8f71c495).

    Cohort KK (wl:2026-06-06-09): section-boundary-aware extraction. Manual
    rows are bounded by the ``_MANUAL_ROW_SECTION_MARKER_PREFIX`` HTML comment
    and the next ``## `` markdown heading (or EOF). Lines OUTSIDE that window
    are never collected, so file-backed rows with missing-``id:`` frontmatter
    — which render with an empty ID cell and were previously
    indistinguishable from real manual rows — are correctly excluded. The
    window anchors come from ``render_curated`` itself (the comment at
    line ~339, the ``## File-backed entries`` heading at line ~346), so the
    structural contract holds round-trip: anything ``render_curated`` writes
    INTO the manual section, ``_extract_manual_rows`` reads back; anything
    written outside is never reclassified.

    Legacy fallback (wl:2026-06-11-02, CTO ratify msg-f479e6cc8030): a
    pre-cohort-KK INDEX has manual rows but no section marker; the
    marker-bounded scan alone would silently drop them on the first
    post-KK re-render. When the marker is absent ANYWHERE in the file,
    fall back to the pre-KK whole-file empty-ID-cell scan for that one
    migration render (the KK phantom-misclassification risk is accepted
    for this single legacy pass — silent data drop is never in-contract).
    Once re-rendered, the marker exists and the bounded path takes over.
    """
    if not index_path.exists():
        return []
    try:
        lines = index_path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return []
    has_marker = any(
        line.startswith(_MANUAL_ROW_SECTION_MARKER_PREFIX) for line in lines
    )
    # Legacy (pre-KK) INDEX: no marker section — scan the whole file.
    in_section = not has_marker
    manual: list[str] = []
    for line in lines:
        if not in_section:
            if line.startswith(_MANUAL_ROW_SECTION_MARKER_PREFIX):
                in_section = True
            continue
        # Inside the manual-row section. End at the next H2 heading
        # (typically "## File-backed entries (top-... by created_at)").
        # Legacy whole-file mode has no section to end (no marker, and
        # pre-KK INDEXes carry no H2 section headings to scope by).
        if has_marker and line.startswith("## "):
            break
        if not line.startswith("|") or line.startswith("|--"):
            continue
        # Skip header row (contains "ID" literal in first cell)
        cells = [c.strip() for c in line.split("|")]
        # cells: ["", id, title, ...] — outer empty strings from leading/trailing |
        if len(cells) < 3:
            continue
        if cells[1] in ("ID", "id"):
            continue
        if cells[1] == "":
            # Empty ID column = manual row to preserve
            manual.append(line)
    return manual


# ---------------------------------------------------------------------------
# EXHAUSTIVE render — flat full-list view
# ---------------------------------------------------------------------------


def render(target_dir, *, title: str, columns, scanner=None) -> None:
    """Re-render ``target_dir/INDEX.md`` from the entity files it indexes.

    ``columns`` is a list of ``(header, fm_field, transform)`` tuples where
    ``transform(value, fm, path) -> str`` produces the cell content. If
    ``fm_field`` is ``None`` the transform receives ``value=None`` and is
    expected to derive the cell from ``fm`` / ``path``.

    ``scanner`` is a callable ``(target_dir) -> list[Path]`` returning the
    entity files to index. Defaults to a flat ``*.md`` glob of ``target_dir``.
    Atomic via tmp-file + rename.
    """
    target_dir = Path(target_dir)
    paths = (scanner or _default_glob)(target_dir)

    rows: list[list[str]] = []
    for path in paths:
        try:
            fm, _body = frontmatter.parse(path)
        except Exception:
            # par:2026-06-04-13 cohort D D2 — legacy files without parseable
            # frontmatter still get an INDEX row via filename-derived
            # fallback (EXHAUSTIVE classes need file_count == row_count).
            fm = _derive_fm_from_filename(path)
        if not isinstance(fm, dict):
            fm = _derive_fm_from_filename(path)
        cells: list[str] = []
        for _header, fm_field, transform in columns:
            value = fm.get(fm_field) if fm_field is not None else None
            cells.append(_escape_cell(transform(value, fm, path)))
        rows.append(cells)

    rows.sort(key=lambda c: c[0])

    headers = [h for h, _, _ in columns]
    lines = [
        f"# {title}",
        "",
        "| " + " | ".join(headers) + " |",
        "|" + "|".join("-" * (len(h) + 2) for h in headers) + "|",
    ]
    for cells in rows:
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")
    content = "\n".join(lines)

    target_dir.mkdir(parents=True, exist_ok=True)
    index_path = target_dir / "INDEX.md"
    tmp = index_path.with_suffix(index_path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(index_path)


# ---------------------------------------------------------------------------
# INDEX rolling-collapse (Phase 1 Cycle 2 of the workshop-lite re-arch arc)
# ---------------------------------------------------------------------------
#
# Per master design `docs/inbox/2026-05-29-workshop-lite-rearch-master-design.md`
# §4.6 (binding): `docs/handoffs/INDEX.md` accumulates pre-compact stubs over
# time (maxai empirical: 47+ entries, 80% empty boilerplate). The rolling-
# collapse mode:
#
#   1. Preserves substantive handoff entries verbatim (full INDEX row).
#   2. Collapses empty pre-compact stubs older than `empty_stub_age_hours`
#      into a single rolling line:
#        - LATEST-PRE-COMPACT-STUBS (N entries collapsed, oldest <date>, newest <date>)
#   3. Most-recent pre-compact stub stays full-form (actionable resume cursor).
#   4. Underlying handoff files stay on disk; only INDEX presentation collapses.
#
# Opt-in via `<repo>/.claude/workshop-lite-config.toml` (Hard Rule 3 prefix).
# Default OFF — when config absent OR `rolling_collapse=false`, the existing
# `render(..., HANDOFF_COLUMNS)` table path runs unchanged. Regression-free.
#
# Empty-stub detection is BINARY + STRUCTURAL (Hard Rule 7). No similarity
# scoring; no fuzzy match. A handoff counts as an empty stub iff ALL of:
#   (a) frontmatter `trigger` == 'pre_compact'
#   (b) frontmatter `author` == '@cc-hook'
#   (c) body matches the auto-generated boilerplate signature (see
#       `_BOILERPLATE_STUB_MARKERS` below — exact-string anchor lines that
#       `entities._auto_handoff_body` emits when the handoff is hook-fired
#       with no sprint + null next_action + no sibling indices).
#
# This is the V3-analog deterministic rule (cf. wip_claim sub-spec §5 V3):
# the surface NEVER emits a graded judgment. It either matches exactly or
# does not.

import re as _re
from datetime import datetime, timedelta, timezone

# Structural anchor lines emitted by `entities._auto_handoff_body` for the
# canonical empty pre-compact stub. The detector treats a handoff as an
# empty stub iff (a) + (b) + (c) above, AND its body — after stripping
# leading/trailing whitespace and any leading H1 title line — meets two
# binary + structural conditions:
#   - contains EVERY required anchor (section headings + closing notes)
#   - has ZERO non-empty body lines that aren't in the boilerplate
#     allow-set (closes the verifier-α MED #1 substring false-positive:
#     append-style user edits inject lines that aren't markers → fail)
#
# The H1 title is ignored because `record_handoff` overrides the auto-
# body's title with the caller-supplied `title` (e.g. "Pre-compact
# snapshot"); the body's structural sections (Current state / Since
# last handoff / What's next / Notes) remain stable across stub
# instances.
#
# Verifier-α HIGH #1 closure: the "Current state" section has THREE
# branches in `entities._auto_handoff_body` (no-sprint / sprint-only /
# sprint+stage). The detector accepts ANY ONE of the three via the
# `_CURRENT_STATE_ANCHORS` set/regex; it matches anchor STRUCTURE,
# never interpolated `<id>` / `<stage>` values. Per Hard Rule 7 the
# rule remains binary + structural — no similarity scoring.
_BOILERPLATE_REQUIRED_MARKERS: tuple[str, ...] = (
    "## Current state",
    "## Since last handoff",
    "## What's next",
    "TBD",
    "## Notes",
    "(auto-generated handoff body; replace with hand-authored content as needed)",
)

# Fixed-literal lines (no interpolation) allowed inside a canonical stub
# body. Used by the line-whitelist gate that closes MED #1.
_BOILERPLATE_ALLOWED_FIXED_LINES: frozenset[str] = frozenset({
    "## Current state",
    "No active sprint at handoff time.",
    "## Since last handoff",
    "- Recent decisions: see `docs/decisions/INDEX.md`",
    "- Open issues: see `docs/issues/INDEX.md`",
    "(no sibling indices found; body to be filled by author or caller)",
    "## What's next",
    "TBD",
    "## Notes",
    "(auto-generated handoff body; replace with hand-authored content as needed)",
})

# Structural anchors that vary by interpolated value. Each regex matches
# the anchor SKELETON exactly; the interpolated id/stage values inside
# backticks are wildcards `[^`]+`. No similarity scoring (Hard Rule 7).
_BOILERPLATE_ALLOWED_LINE_REGEXES: tuple[_re.Pattern[str], ...] = (
    # Current state, sprint-only branch: ``Active sprint: `<id>`.``
    _re.compile(r"^Active sprint: `[^`]+`\.$"),
    # Current state, sprint+stage branch: ``Active sprint: `<id>` at stage `<stage>`.``
    _re.compile(r"^Active sprint: `[^`]+` at stage `[^`]+`\.$"),
    # Sprint-tasks pointer (when sprint_id is populated):
    # ``- Sprint tasks: see `docs/sprints/active/sprint-<id>/tasks.md```
    _re.compile(
        r"^- Sprint tasks: see `docs/sprints/active/sprint-[^`/]+/tasks\.md`$"
    ),
)

# Backwards-compat alias retained for any external reader; the new
# detector uses `_BOILERPLATE_REQUIRED_MARKERS` (the anchor set) plus
# the line-whitelist gate. External tests / sub-spec citations that
# reference `_BOILERPLATE_STUB_MARKERS` continue to resolve to the
# required-anchor set.
_BOILERPLATE_STUB_MARKERS: tuple[str, ...] = _BOILERPLATE_REQUIRED_MARKERS


def _load_workshop_lite_config(
    repo_root: Path,
    config_path: Path | None = None,
) -> dict:
    """Read the consolidated workshop-lite config file.

    Per master design §4.6 + composite-audit MED #5: the consolidated
    config lives at ``<repo>/.claude/workshop-lite-config.toml`` (Hard
    Rule 3 ``workshop-lite-`` prefix). Each section is OPTIONAL +
    ADDITIVE; absent file / absent section / malformed TOML all degrade
    to empty dict (Hard Rule 5 robustness — never block).
    """
    if config_path is None:
        config_path = Path(repo_root) / ".claude" / "workshop-lite-config.toml"
    if not config_path.exists():
        return {}
    try:
        import tomllib
        return tomllib.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _handoffs_config(repo_root: Path, config_path: Path | None = None) -> dict:
    """Extract the ``[handoffs]`` section with defaults applied.

    Defaults per master §4.6: ``rolling_collapse=False`` (opt-in),
    ``empty_stub_age_hours=24``.

    Cohort W (wl:2026-06-03-06) extends the schema with file-side aging
    policy fields. Defaults non-destructive: archive strategy, keep 3
    most-recent stubs, cadence 0 (manual-only). See
    ``.claude/workshop-lite-config.toml`` `[handoffs]` block for field
    semantics.
    """
    cfg = _load_workshop_lite_config(repo_root, config_path)
    section = cfg.get("handoffs") if isinstance(cfg, dict) else None
    rolling = False
    age_hours = 24
    strategy = "archive"
    keep_recent_n = 3
    cadence = 0
    if isinstance(section, dict):
        val = section.get("rolling_collapse")
        if isinstance(val, bool):
            rolling = val
        age = section.get("empty_stub_age_hours")
        if isinstance(age, int) and age >= 0:
            age_hours = age
        strat = section.get("stub_collapse_strategy")
        if isinstance(strat, str) and strat in (
            "archive", "merge-into-prev", "delete",
        ):
            strategy = strat
        kn = section.get("keep_recent_n_stubs")
        if isinstance(kn, int) and kn >= 0:
            keep_recent_n = kn
        cad = section.get("collapse_cadence_stub_writes")
        if isinstance(cad, int) and cad >= 0:
            cadence = cad
    return {
        "rolling_collapse": rolling,
        "empty_stub_age_hours": age_hours,
        "stub_collapse_strategy": strategy,
        "keep_recent_n_stubs": keep_recent_n,
        "collapse_cadence_stub_writes": cadence,
    }


def _strip_h1_title(body: str) -> str:
    """Drop a leading ``# ...`` title line if present, return the rest.

    The `_auto_handoff_body` writes ``# {title}`` as the first body
    line; `record_handoff` lets the caller supply ``title``, so the
    H1 varies across stub instances but the structural sections below
    do not. We strip the H1 before marker-matching so the detector is
    title-agnostic.
    """
    lines = body.splitlines()
    # Skip leading blank lines.
    idx = 0
    while idx < len(lines) and not lines[idx].strip():
        idx += 1
    if idx < len(lines) and lines[idx].lstrip().startswith("# "):
        # Drop the H1 line + any following blank line.
        idx += 1
        while idx < len(lines) and not lines[idx].strip():
            idx += 1
    return "\n".join(lines[idx:])


def _line_matches_boilerplate_allow(line: str) -> bool:
    """Return True iff a single body line belongs to the boilerplate allow-set.

    Binary structural match against a fixed-literal set OR a small tuple
    of anchor regexes. The regexes match anchor SKELETON only — the
    interpolated values (sprint_id, stage) are wildcards. Per Hard
    Rule 7: no similarity scoring; no fuzzy match.
    """
    if line in _BOILERPLATE_ALLOWED_FIXED_LINES:
        return True
    for pat in _BOILERPLATE_ALLOWED_LINE_REGEXES:
        if pat.match(line):
            return True
    return False


def is_empty_pre_compact_stub(fm: dict, body: str) -> bool:
    """Return True iff the handoff is a default-boilerplate pre-compact stub.

    BINARY + STRUCTURAL per Hard Rule 7. Detection rule (all must hold):

    1. ``fm['trigger'] == 'pre_compact'``
    2. ``fm['author'] == '@cc-hook'``
    3. The body — after stripping leading whitespace + a leading H1
       title line — contains EVERY anchor in
       ``_BOILERPLATE_REQUIRED_MARKERS`` as an exact substring AND
       every non-empty body line is in the boilerplate allow-set
       (fixed-literal set or anchor-regex match).

    Verifier-α HIGH #1 closure: the active-sprint branches of
    ``entities._auto_handoff_body`` are accepted via the
    ``_BOILERPLATE_ALLOWED_LINE_REGEXES`` patterns (sprint-only +
    sprint+stage). The detector matches anchor structure, never
    interpolated ``<id>`` / ``<stage>`` values.

    Verifier-α MED #1 closure: append-style user edits (e.g. extending
    ``TBD`` to ``TBD - actually run pytest then commit``) now fail
    detection because the appended line is NOT in the boilerplate
    allow-set. Substantive content is preserved verbatim.

    No similarity scoring. No partial credit. Exact substring/regex
    match against a documented allow-set.
    """
    if not isinstance(fm, dict):
        return False
    if fm.get("trigger") != "pre_compact":
        return False
    if fm.get("author") != "@cc-hook":
        return False
    if not isinstance(body, str):
        return False
    stripped = _strip_h1_title(body)

    # Anchor presence check (every required marker must appear).
    for marker in _BOILERPLATE_REQUIRED_MARKERS:
        if marker not in stripped:
            return False

    # Line-whitelist gate (MED #1 closure): every non-empty body line
    # must be in the boilerplate allow-set. A single non-allowed line
    # (e.g. an append-edit) flips detection to False, preserving the
    # edited handoff verbatim per §4.6 rule #1.
    for raw_line in stripped.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if not _line_matches_boilerplate_allow(line):
            return False

    return True


# Verifier-α HIGH #2 closure: a stub whose `created_at` is null or
# unparseable was falling back to `cutoff_now` (real-time now), which
# sorted it to the MOST-RECENT slot — displacing the legitimate fresh
# stub from §4.6 rule #3's actionable-resume-cursor position. The
# tiebreak is now MAXIMALLY OLD (UTC epoch sentinel): null/unparseable
# stubs sort to the front of the collapse population and never steal
# the most-recent slot. The `fallback` parameter is retained for
# call-site compatibility but is IGNORED for null/unparseable values;
# callers that still pass `cutoff_now` see no behavioral change for
# valid `created_at` values.
_EPOCH_UTC: datetime = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _parse_handoff_created_dt(fm: dict, fallback: datetime) -> datetime:
    """Parse ``fm['created_at']`` to a UTC datetime.

    Null / empty / unparseable ``created_at`` → ``_EPOCH_UTC`` (sorts as
    OLDEST, never wins the §4.6 rule #3 most-recent slot). The
    ``fallback`` parameter is accepted for API stability with the
    Phase 1 Cycle 2 initial release but is ignored on null/unparseable
    per the verifier-α HIGH #2 closure direction.
    """
    raw = fm.get("created_at")
    if not raw:
        return _EPOCH_UTC
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return _EPOCH_UTC
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _format_handoff_row(fm: dict, slug: str) -> str:
    """Render a single full-form handoff entry as a markdown list row.

    Shape mirrors the WIP-claim §8 INDEX row shape so the validator's
    list-shape parser (``_parse_handoffs_index_ids`` in
    :mod:`validate`) can extract the id by a uniform regex.

    Verifier-α MED #3 closure: ``sprint_id`` and ``stage`` are emitted
    when populated, so toggling ``rolling_collapse=true`` does NOT
    drop the sprint/stage cursor on substantive non-collapsed rows
    (no information-density regression vs classical HANDOFF_COLUMNS).
    """
    title = fm.get("title") or slug
    trigger = fm.get("trigger") or ""
    created = str(fm.get("created_at") or "")[:10]
    author = fm.get("author") or ""
    sprint_id = fm.get("sprint_id") or ""
    stage = fm.get("stage") or ""
    bits = [f"[{slug}]({slug}.md)"]
    if title and title != slug:
        bits.append(_escape_cell(str(title)))
    if trigger:
        bits.append(f"trigger=`{trigger}`")
    if author:
        bits.append(f"author=`{author}`")
    if sprint_id:
        bits.append(f"sprint=`{sprint_id}`")
    if stage:
        bits.append(f"stage=`{stage}`")
    if created:
        bits.append(f"created={created}")
    return "- " + " — ".join(bits)


def render_handoffs_index_with_rolling_collapse(
    *,
    repo_root: Path,
    config_path: Path | None = None,
    _now: datetime | None = None,
) -> str:
    """Render ``docs/handoffs/INDEX.md`` with rolling-collapse applied.

    Per master design §4.6 (binding). Public API.

    Behavior gated on ``[handoffs].rolling_collapse`` in
    ``<repo>/.claude/workshop-lite-config.toml``:

    - **OFF (default)**: delegates to ``render(handoffs_dir,
      title='Handoffs', columns=HANDOFF_COLUMNS)`` — the existing
      flat-table path; zero regression risk; returns the rendered text
      for callers that want it (matching the file's contents on disk).
    - **ON**: bespoke list-shape render — substantive entries preserved
      verbatim, empty pre-compact stubs older than ``empty_stub_age_hours``
      collapsed into a single rolling line; most-recent pre-compact stub
      stays full-form per rule #3 of §4.6.

    Returns the rendered INDEX content as a string (also written to
    ``docs/handoffs/INDEX.md`` atomically via tmp+rename). When the
    handoffs directory does not exist, returns the empty string and
    writes nothing.

    ``_now`` is a TEST-ONLY clock-injection seam (leading underscore
    per Python convention for non-public API). Verifier-α MED #2
    closure: the validator's ``_index_suppressed_slugs`` always uses
    real-time ``_utc_now()``, so any production caller passing a
    non-real clock would silently desync from the suppression path —
    use of ``_now=`` outside tests is unsupported.
    """
    import frontmatter as _fm

    repo = Path(repo_root)
    handoffs_dir = ledger_paths.compat_kind_dir(repo, "handoffs")
    if not handoffs_dir.exists():
        return ""

    cfg = _handoffs_config(repo, config_path)
    if not cfg["rolling_collapse"]:
        # Default path — preserve existing behavior exactly. Delegates
        # to the classical flat-table renderer.
        render(handoffs_dir, title="Handoffs", columns=HANDOFF_COLUMNS)
        idx = handoffs_dir / "INDEX.md"
        return idx.read_text(encoding="utf-8") if idx.exists() else ""

    age_threshold = timedelta(hours=cfg["empty_stub_age_hours"])
    cutoff_now = _now or _utc_now()
    cutoff = cutoff_now - age_threshold

    substantive: list[tuple[str, dict, datetime]] = []
    stubs: list[tuple[str, dict, datetime]] = []

    for path in sorted(handoffs_dir.glob("*.md")):
        if path.name == "INDEX.md" or path.name.startswith("INDEX-"):
            continue
        try:
            fm, body = _fm.parse(path)
        except Exception:
            continue
        if not isinstance(fm, dict):
            continue
        created_dt = _parse_handoff_created_dt(fm, cutoff_now)
        slug = path.stem
        if is_empty_pre_compact_stub(fm, body):
            stubs.append((slug, fm, created_dt))
        else:
            substantive.append((slug, fm, created_dt))

    # Determine which stubs collapse vs stay full-form.
    # Rule #3 of §4.6: most-recent pre-compact stub stays full-form.
    # Rule #2 of §4.6: stubs OLDER than threshold collapse.
    # Stubs newer-than-threshold also stay full-form.
    collapse_stubs: list[tuple[str, dict, datetime]] = []
    keep_stubs: list[tuple[str, dict, datetime]] = []
    if stubs:
        stubs_sorted = sorted(stubs, key=lambda x: x[2])  # oldest first
        most_recent = stubs_sorted[-1]
        for entry in stubs_sorted[:-1]:
            # Comparison: strictly older than cutoff → collapse.
            # Newer-or-equal → keep full-form.
            if entry[2] < cutoff:
                collapse_stubs.append(entry)
            else:
                keep_stubs.append(entry)
        keep_stubs.append(most_recent)

    # Build the list-shape INDEX. Substantive entries first (sorted by
    # created_at desc → newest at top), then kept stubs (same ordering),
    # then the rolling-collapse line for the collapsed remainder.
    lines: list[str] = ["# Handoffs", ""]

    keep_all = substantive + keep_stubs
    keep_all.sort(key=lambda x: x[2], reverse=True)
    if keep_all:
        for slug, fm, _dt in keep_all:
            lines.append(_format_handoff_row(fm, slug))
    else:
        lines.append("(none)")

    if collapse_stubs:
        collapse_stubs.sort(key=lambda x: x[2])
        oldest = collapse_stubs[0][2].strftime("%Y-%m-%d")
        newest = collapse_stubs[-1][2].strftime("%Y-%m-%d")
        n = len(collapse_stubs)
        # Verifier-α LOW #1 closure: singular/plural + dedupe identical
        # oldest/newest dates so n=1 reads cleanly.
        noun = "entry" if n == 1 else "entries"
        if oldest == newest:
            range_part = f"date {oldest}"
        else:
            range_part = f"oldest {oldest}, newest {newest}"
        lines.append(
            f"- LATEST-PRE-COMPACT-STUBS "
            f"({n} {noun} collapsed, {range_part})"
        )
    lines.append("")
    content = "\n".join(lines)

    handoffs_dir.mkdir(parents=True, exist_ok=True)
    index_path = handoffs_dir / "INDEX.md"
    tmp = index_path.with_suffix(index_path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(index_path)
    return content
