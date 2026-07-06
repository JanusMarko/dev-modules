"""Sync-from-parley library (Phase 2 Cycle 2 of the workshop-lite re-arch arc).

Per the binding sub-spec at
``docs/design/2026-05-29-wl-sync-from-parley-spec.md``: subscribe to parley
`chat.jsonl` for the current session and idempotently record durable
Kinds as workshop-lite entities. Closes the manual-recording gap; the
three-way pattern (parley emits / WL records / seat queries) becomes
operational.

PARLEY-AGNOSTIC (CLAUDE.md Hard Rule 1): this module NEVER imports or
shells out to parley. The CALLER (sidecar invocation layer at
``.claude/hooks/session-context.sh`` or ``pre-compact.sh``) runs
``parley get --kind decision,blocker_raised,blocker_resolved --since
<cursor> --json``, parses the JSON, and passes the pre-parsed records
into :func:`sync_chat_jsonl`. The library does the idempotent per-Kind
dispatch; the parley shell-out lives at the hook layer only.

EPIC_SHIPPED auto-sync DEFERRED (D-WL-22, 2026-05-30): the EpicShipped
entity TYPE + manual writer (:func:`record_epic_shipped`) remain in
this library so direct callers can file EpicShipped entities by hand,
but the AUTO-SYNC path from a parley ``Kind.EPIC_SHIPPED`` chat record
is DEFERRED to a follow-up cycle. Per the closure cert at
``docs/reviews/2026-05-30-wl-phase2-syncfromparley-cross-check.md``
HIGH-2, parley's substrate (as of 2026-05-30) does NOT actually emit a
``Kind.EPIC_SHIPPED`` chat event — ``parley ship-epic`` emits a
different Kind enum chain (``SHIP_EPIC_REQUESTED → LANDED → LOADED →
SHIPPED | ABORTED``), none of which are valid ``parley get --kind``
filter values yet. Open question Q-SFP-N tracks the un-gate criterion:
parley primitive #6 publishes its actual emit-Kind enum binding and
the binding lands in this module's ``_SYNCED_KINDS`` frozenset.

NOT A JUDGMENT COMPONENT (Hard Rule 7): the dispatch is a deterministic
Kinds-to-entity mapping; ``BLOCKER_RAISED`` severity is HARD-CODED to
``medium`` per sub-spec §2 + audit HIGH #1 (no inference). Phantom
``GOVERNANCE_INPUT`` mapping fully removed per audit HIGH #3.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import entities
import ledger_paths
import frontmatter as _fm
import index
import validators


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CURSOR_SCHEMA_VERSION = 1
_CURSOR_RECENT_LIMIT = 50  # sub-spec §3: defense-in-depth rolling window
_CURSOR_REL = ".claude/scripts/dev-mgmt/.sync_cursor.json"
_LOG_REL = ".claude/scripts/dev-mgmt/.sync_log.jsonl"

# Sub-spec §2: Kinds the daemon WILL sync (everything else is silently
# dropped). Match against parley `kind` field case-insensitively — the
# parley API emits Python-enum names (e.g. `Kind.DECISION` or `DECISION`
# depending on `--json` shape). We normalize to upper-case bare-name.
#
# EPIC_SHIPPED intentionally EXCLUDED per D-WL-22 (2026-05-30): the
# parley substrate does not emit ``Kind.EPIC_SHIPPED`` yet; auto-sync is
# deferred until parley primitive #6 publishes its emit-Kind enum
# binding (open question Q-SFP-N). The entity type + manual writer
# (:func:`record_epic_shipped`) remain in this library.
_SYNCED_KINDS = frozenset({
    "DECISION",
    "BLOCKER_RAISED",
    "BLOCKER_RESOLVED",
})


# ---------------------------------------------------------------------------
# SyncResult dataclass — surface what happened to the caller
# ---------------------------------------------------------------------------


@dataclass
class SyncResult:
    """Summary of one ``sync_chat_jsonl`` call.

    Fields surface what the caller (hook layer) needs to log / decide
    whether to advance any external counter. The library itself updates
    the cursor file in place; this dataclass is the in-memory mirror.
    """

    session_id: str
    processed: int = 0  # records actually consumed (recorded or skipped)
    recorded: int = 0   # records that resulted in an entity write
    skipped: int = 0    # records that hit idempotency / conflict skip
    dropped: int = 0    # records of un-synced Kinds (silently dropped)
    failed: int = 0     # records where entity-write raised; cursor NOT advanced
    entity_paths: list[Path] = field(default_factory=list)
    last_msg_id: str | None = None
    log_entries: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers — cursor read/write
# ---------------------------------------------------------------------------


def _utc_now_iso() -> str:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    return now.strftime("%Y-%m-%dT%H:%M:%SZ")


def _default_cursor_path(repo_root: Path) -> Path:
    return Path(repo_root) / _CURSOR_REL


def _default_log_path(repo_root: Path) -> Path:
    return Path(repo_root) / _LOG_REL


def load_cursor(cursor_path: Path) -> dict:
    """Read the cursor file. Return an empty default shape on any failure.

    Per sub-spec §9 failure-mode #2: a corrupted cursor file is backed
    up to ``.sync_cursor.json.bak`` + reinitialized. We surface the
    corruption to the CALLER (hook layer) which decides whether to log
    + reinit. This pure-library function returns the empty default on
    corruption — never raises.
    """
    if not cursor_path.exists():
        return {"schema_version": _CURSOR_SCHEMA_VERSION, "sessions": {}}
    try:
        data = json.loads(cursor_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"schema_version": _CURSOR_SCHEMA_VERSION, "sessions": {}}
    if not isinstance(data, dict):
        return {"schema_version": _CURSOR_SCHEMA_VERSION, "sessions": {}}
    # Normalize missing keys (forward-compat).
    data.setdefault("schema_version", _CURSOR_SCHEMA_VERSION)
    sessions = data.get("sessions")
    if not isinstance(sessions, dict):
        data["sessions"] = {}
    return data


def _save_cursor(cursor_path: Path, cursor: dict) -> None:
    """Atomic write of the cursor file (tmp + rename).

    Per sub-spec §3: cursor is updated AFTER successful entity-write,
    never before. The library guarantees atomicity at the file level;
    the per-msg-id ordering is the caller's responsibility (we process
    records in the order the caller passes them).
    """
    cursor_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = cursor_path.with_suffix(cursor_path.suffix + ".tmp")
    tmp.write_text(json.dumps(cursor, indent=2), encoding="utf-8")
    tmp.replace(cursor_path)


def backup_corrupted_cursor(cursor_path: Path) -> Path | None:
    """Per sub-spec §9 failure-mode #2: rename corrupted cursor to .bak.

    The caller (hook layer) detects corruption via :func:`load_cursor`
    returning an empty default + the file existing on disk being
    non-empty. Returns the backup path on success, ``None`` if the
    rename itself fails. Pure-library: no parley imports.
    """
    if not cursor_path.exists():
        return None
    bak = cursor_path.with_suffix(cursor_path.suffix + ".bak")
    try:
        os.replace(cursor_path, bak)
    except OSError:
        return None
    return bak


# ---------------------------------------------------------------------------
# Helpers — Kinds normalization
# ---------------------------------------------------------------------------


def _normalize_kind(raw: object) -> str | None:
    """Normalize a parley `kind` field to upper-case bare name.

    Parley `--json` may emit `Kind.DECISION` or `DECISION` or
    `decision`. We strip any `Kind.` prefix and upper-case. Returns
    ``None`` for non-string input.
    """
    if not isinstance(raw, str):
        return None
    s = raw.strip()
    if s.startswith("Kind."):
        s = s[len("Kind."):]
    return s.upper() or None


# ---------------------------------------------------------------------------
# Helpers — idempotency checks (file-level defense, sub-spec §3.1 rule 3)
# ---------------------------------------------------------------------------


def _decision_for_msg_id(
    repo_root: Path, msg_id: str
) -> Path | None:
    """Return the path of an existing Decision file with this msg-id
    in ``linked_msg_ids``, or ``None``.
    """
    decisions_dir = ledger_paths.compat_kind_dir(repo_root, "decisions")
    if not decisions_dir.exists():
        return None
    for path in sorted(decisions_dir.glob("*.md")):
        if path.name == "INDEX.md":
            continue
        try:
            fm, _body = _fm.parse(path)
        except Exception:
            continue
        if not isinstance(fm, dict):
            continue
        linked = fm.get("linked_msg_ids") or []
        if isinstance(linked, list) and msg_id in linked:
            return path
    return None


def _issue_for_msg_id(
    repo_root: Path, msg_id: str, *, status_filter: set[str] | None = None
) -> Path | None:
    """Return the path of an Issue whose ``linked_msg_ids`` references
    this msg-id. Optional status filter (e.g. ``{"open", "investigating"}``).
    """
    issues_dir = ledger_paths.compat_kind_dir(repo_root, "issues")
    if not issues_dir.exists():
        return None
    for path in sorted(issues_dir.glob("*.md")):
        if path.name == "INDEX.md":
            continue
        try:
            fm, _body = _fm.parse(path)
        except Exception:
            continue
        if not isinstance(fm, dict):
            continue
        linked = fm.get("linked_msg_ids") or []
        if not isinstance(linked, list) or msg_id not in linked:
            continue
        if status_filter is not None:
            status = fm.get("status")
            if status not in status_filter:
                continue
        return path
    return None


def _epic_for_msg_id(
    repo_root: Path, msg_id: str
) -> Path | None:
    """Return the path of an existing EpicShipped file with this msg-id
    in ``parley_ship_epic_msg_id`` or ``linked_msg_ids``.
    """
    epics_dir = repo_root / "docs" / "epics"
    if not epics_dir.exists():
        return None
    for path in sorted(epics_dir.glob("*.md")):
        if path.name == "INDEX.md":
            continue
        try:
            fm, _body = _fm.parse(path)
        except Exception:
            continue
        if not isinstance(fm, dict):
            continue
        if fm.get("parley_ship_epic_msg_id") == msg_id:
            return path
        linked = fm.get("linked_msg_ids") or []
        if isinstance(linked, list) and msg_id in linked:
            return path
    return None


# ---------------------------------------------------------------------------
# EpicShipped entity writer (sub-spec §5)
# ---------------------------------------------------------------------------


def _next_epic_counter(epics_dir: Path, date_str: str) -> int:
    """Per-day NN counter for ``<date>-<NN>-<slug>.md``. Mirrors
    ``entities._next_counter`` so the id-format stays homogenous."""
    import re
    pattern = re.compile(rf"^{re.escape(date_str)}-(\d{{2}})-")
    max_n = 0
    if epics_dir.exists():
        for path in epics_dir.glob(f"{date_str}-*.md"):
            m = pattern.match(path.name)
            if m:
                max_n = max(max_n, int(m.group(1)))
    return max_n + 1


def record_epic_shipped(
    *,
    repo_root: Path,
    title: str,
    scope: str,
    shipped_at: str,
    shipped_by_seat: str,
    parley_ship_epic_msg_id: str,
    sprint_id: str | None = None,
    charter_ref: str | None = None,
    land_commit: str | None = None,
    load_artifacts: list[str] | None = None,
    broadcast_msg_id: str | None = None,
    linked_decisions: list[str] | None = None,
    linked_msg_ids: list[str] | None = None,
    owner_user: str = "user/local",
    created_by: str = "@sync-daemon",
    created_by_source: str = "sync-daemon",
    supersedes_msg_id: str | None = None,
) -> Path:
    """Write a new EpicShipped entity per sub-spec §5.1.

    File location: ``docs/epics/<date>-<NN>-<slug>.md``.
    Frontmatter schema validated by ``validators.validate_epic_shipped``.

    If ``supersedes_msg_id`` is provided AND a matching prior
    EpicShipped exists with that ``parley_ship_epic_msg_id``, the prior
    file is updated to ``status: superseded`` BEFORE the new file is
    written. This is the only mutation the daemon performs on existing
    epic files; the lifecycle (§5.2) permits exactly this one transition.
    """
    repo = Path(repo_root)
    epics_dir = repo / "docs" / "epics"

    # Form id from shipped_at date (UTC) — falls back to today if parse fails.
    try:
        ship_dt = datetime.fromisoformat(
            str(shipped_at).replace("Z", "+00:00")
        )
        if ship_dt.tzinfo is None:
            ship_dt = ship_dt.replace(tzinfo=timezone.utc)
        date_str = ship_dt.astimezone(timezone.utc).strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    counter = _next_epic_counter(epics_dir, date_str)
    slug = entities._slugify(title)
    prefix = f"{date_str}-{counter:02d}-"
    epic_id = prefix + entities._cap_slug(slug, prefix)

    # Compose linked_msg_ids — always include the parley ship-epic msg-id.
    composed_links = list(linked_msg_ids or [])
    if parley_ship_epic_msg_id and parley_ship_epic_msg_id not in composed_links:
        composed_links.insert(0, parley_ship_epic_msg_id)

    fm = {
        "id": epic_id,
        "type": "epic_shipped",
        "title": title,
        "status": "shipped",
        "scope": scope,
        "sprint_id": sprint_id,
        "charter_ref": charter_ref,
        "shipped_at": shipped_at,
        "shipped_by_seat": shipped_by_seat,
        "parley_ship_epic_msg_id": parley_ship_epic_msg_id,
        "land_commit": land_commit,
        "load_artifacts": list(load_artifacts or []),
        "broadcast_msg_id": broadcast_msg_id,
        "created_at": _utc_now_iso(),
        "created_by": created_by,
        "created_by_source": created_by_source,
        "linked_decisions": list(linked_decisions or []),
        "linked_msg_ids": composed_links,
        "owner_user": owner_user,
    }

    validators.validate_epic_shipped(fm)

    # If this ship supersedes a prior one, flip the prior's status.
    if supersedes_msg_id:
        prior = _epic_for_msg_id(repo, supersedes_msg_id)
        if prior is not None:
            try:
                prior_fm, prior_body = _fm.parse(prior)
                if isinstance(prior_fm, dict):
                    prior_fm["status"] = "superseded"
                    _fm.write(prior, prior_fm, prior_body)
            except Exception:
                pass  # advisory mutation; never block primary write

    body = _epic_body(
        title=title,
        scope=scope,
        shipped_at=shipped_at,
        shipped_by_seat=shipped_by_seat,
        land_commit=land_commit,
        load_artifacts=list(load_artifacts or []),
    )

    target = epics_dir / f"{epic_id}.md"
    _fm.write(target, fm, body)
    index.render(
        epics_dir, title="Epic-shipped", columns=index.EPIC_SHIPPED_COLUMNS,
    )
    return target


def _epic_body(
    *,
    title: str,
    scope: str,
    shipped_at: str,
    shipped_by_seat: str,
    land_commit: str | None,
    load_artifacts: list[str],
) -> str:
    artifacts_block = (
        "\n".join(f"- `{p}`" for p in load_artifacts)
        if load_artifacts
        else "(none recorded)"
    )
    lines = [
        f"# {title}",
        "",
        "## Ship",
        "",
        f"- **Scope:** `{scope}`",
        f"- **Shipped at:** {shipped_at}",
        f"- **Shipped by seat:** `{shipped_by_seat}`",
        f"- **Land commit:** `{land_commit or '(unrecorded)'}`",
        "",
        "## Loaded artifacts",
        "",
        artifacts_block,
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Per-Kind dispatchers (sub-spec §2)
# ---------------------------------------------------------------------------


def _record_decision_from_kind(
    *, repo_root: Path, record: dict
) -> tuple[Path | None, str, str | None]:
    """Dispatch DECISION → entities.record_decision.

    Returns ``(entity_path, action, reason)`` where action ∈
    {"recorded", "skipped"} and reason is a brief description for the
    skip case (None for recorded).
    """
    msg_id = record.get("id")
    if not isinstance(msg_id, str):
        return None, "skipped", "msg_id_missing"

    # File-level idempotency (sub-spec §3.1 rule 3 + §4 conflict handling).
    existing = _decision_for_msg_id(repo_root, msg_id)
    if existing is not None:
        return None, "skipped", "existing_decision_matches_linked_msg_ids"

    title, status = _extract_decision_title(record)
    rationale = _extract_decision_rationale(record)
    body = _extract_body(record)
    author = _extract_author(record)

    path = entities.record_decision(
        title=title,
        rationale=rationale or (body or "(no rationale provided)"),
        options=[],  # parley-emitted decisions: no structured options
        scope=record.get("scope") or "repo:parley-synced",
        author=author,
        repo_root=repo_root,
        linked_msg_ids=[msg_id],
        status=status,
    )
    return path, "recorded", None


def _extract_decision_title(record: dict) -> tuple[str, str]:
    """Per sub-spec §12 Q-SFP-3: when the body lacks structure, record a
    minimal Decision with ``title = first 80 chars`` + ``status = proposed``.

    Returns ``(title, status)``. Structured input ("Decision: <title>"
    marker) yields ``status='accepted'``; free-form prose yields
    ``status='proposed'``.
    """
    body = _extract_body(record)
    # Look for an explicit Decision: marker.
    for line in body.splitlines():
        s = line.strip()
        if s.lower().startswith("decision:"):
            title = s.split(":", 1)[1].strip() or "(untitled decision)"
            return title[:200], "accepted"
    # Fallback: first 80 chars of the first non-empty line.
    # Sub-spec §12 Q-SFP-3: unstructured Decision → status='proposed'
    # (NOT 'accepted' — the human must accept). Validator enum extended
    # to include 'proposed' as part of the MED-1 closure (2026-05-30).
    for line in body.splitlines():
        s = line.strip()
        if s:
            return s[:80] or "(untitled decision)", "proposed"
    return "(untitled decision)", "proposed"


def _extract_decision_rationale(record: dict) -> str | None:
    body = _extract_body(record)
    capture: list[str] = []
    capturing = False
    for line in body.splitlines():
        s = line.strip()
        if s.lower().startswith("rationale:"):
            tail = s.split(":", 1)[1].strip()
            if tail:
                capture.append(tail)
            capturing = True
            continue
        if capturing:
            if s.lower().startswith(("decision:", "options:", "chosen:")):
                break
            capture.append(line)
    text = "\n".join(capture).strip()
    return text or None


def _extract_body(record: dict) -> str:
    """Pull the message body. Parley records use ``raw`` (verbatim) or
    ``body``; either works. Empty string fallback."""
    raw = record.get("raw") or record.get("body") or ""
    return str(raw)


def _extract_author(record: dict) -> str:
    """Normalize a parley sender to a workshop-lite author string.

    Sender is the ``from`` field on a record. We prefix with ``@`` if
    absent so the value matches workshop-lite's author conventions.
    """
    sender = record.get("from") or record.get("sender") or "unknown"
    s = str(sender).strip()
    if not s:
        s = "unknown"
    if not s.startswith("@"):
        s = f"@{s}"
    return s


def _record_blocker_raised_from_kind(
    *, repo_root: Path, record: dict
) -> tuple[Path | None, str, str | None]:
    """Dispatch BLOCKER_RAISED → entities.record_issue.

    Sub-spec §2 + audit HIGH #1: severity is HARD-CODED to ``medium``.
    No inference; no parsing of body for severity hints. Human edit is
    required to upgrade severity before action.
    """
    msg_id = record.get("id")
    if not isinstance(msg_id, str):
        return None, "skipped", "msg_id_missing"

    existing = _issue_for_msg_id(repo_root, msg_id)
    if existing is not None:
        return None, "skipped", "existing_issue_matches_linked_msg_ids"

    title = _extract_blocker_title(record)
    body = _extract_body(record)
    reporter = _extract_author(record)

    path = entities.record_issue(
        title=title,
        severity="medium",  # HARD-CODED per sub-spec §2 + HIGH #1
        scope=record.get("scope") or "repo:parley-synced",
        reporter=reporter,
        status="open",
        body=body or None,
        repo_root=repo_root,
        linked_msg_ids=[msg_id],
    )
    return path, "recorded", None


def _extract_blocker_title(record: dict) -> str:
    body = _extract_body(record)
    for line in body.splitlines():
        s = line.strip()
        if s.lower().startswith("blocker:"):
            return (s.split(":", 1)[1].strip() or "(unspecified blocker)")[:200]
    for line in body.splitlines():
        s = line.strip()
        if s:
            return s[:80]
    return "(unspecified blocker)"


def _record_blocker_resolved_from_kind(
    *, repo_root: Path, record: dict
) -> tuple[Path | None, str, str | None]:
    """Dispatch BLOCKER_RESOLVED → update existing Issue file.

    Sub-spec §2: locate the open Issue matching the BLOCKER_RAISED
    msg-id chain and flip status → ``resolved``.

    v1 (MED-2 closure 2026-05-30): resolution-link is via the explicit
    ``resolves_msg_id`` (or legacy ``resolves``) field ONLY. Body-scan
    for embedded msg-id references is NOT implemented in v1; a record
    with no explicit ``resolves_msg_id`` is skipped with reason
    ``no_matching_open_issue``. The substrate-level "msg-id chain"
    semantics (per sub-spec §2) collapse to "explicit field" in v1;
    body-scan is a follow-up cycle if usage demands it.

    Sub-spec §4: if no matching open Issue is found, skip + INFO log.
    """
    msg_id = record.get("id")
    if not isinstance(msg_id, str):
        return None, "skipped", "msg_id_missing"

    # Locate the open issue this resolves via the explicit field only.
    # v1 contract: NO body-scan fallback (see docstring above).
    resolves_msg_id = record.get("resolves_msg_id") or record.get("resolves")
    target = None
    if isinstance(resolves_msg_id, str):
        target = _issue_for_msg_id(
            repo_root, resolves_msg_id,
            status_filter={"open", "investigating"},
        )

    if target is None:
        return None, "skipped", "no_matching_open_issue"

    # Already-resolved idempotency: if THIS msg-id already in target's
    # linked_msg_ids, skip — we've processed this resolution before.
    try:
        fm, body = _fm.parse(target)
    except Exception:
        return None, "skipped", "issue_unreadable"
    if not isinstance(fm, dict):
        return None, "skipped", "issue_frontmatter_invalid"

    existing_links = list(fm.get("linked_msg_ids") or [])
    if msg_id in existing_links:
        return None, "skipped", "resolution_already_recorded"

    fm["status"] = "resolved"
    fm["linked_msg_ids"] = existing_links + [msg_id]
    validators.validate_issue(fm)

    # Append a resolution paragraph to the body.
    res_body = _extract_body(record).strip()
    if res_body:
        appended = body.rstrip() + "\n\n## Resolution\n\n" + res_body + "\n"
    else:
        appended = body.rstrip() + "\n\n## Resolution\n\n(no body)\n"

    _fm.write(target, fm, appended)
    issues_dir = ledger_paths.compat_kind_dir(repo_root, "issues")
    index.render(issues_dir, title="Issues", columns=index.ISSUE_COLUMNS)
    return target, "recorded", None


def _record_epic_shipped_from_kind(
    *, repo_root: Path, record: dict
) -> tuple[Path | None, str, str | None]:
    """Dispatch EPIC_SHIPPED → record_epic_shipped (this module).

    NOTE (D-WL-22, 2026-05-30): this helper is intentionally NOT wired
    into the ``sync_chat_jsonl`` dispatch table — auto-sync of
    EPIC_SHIPPED is DEFERRED until parley primitive #6 publishes its
    emit-Kind enum binding (Q-SFP-N). The helper is preserved here so
    the un-gate cycle is a 1-line ``_SYNCED_KINDS`` add + a dispatch
    branch + a hook ``--kind`` filter token — no schema or glue
    redesign. Direct callers should use the public ``record_epic_shipped``
    function instead.
    """
    msg_id = record.get("id")
    if not isinstance(msg_id, str):
        return None, "skipped", "msg_id_missing"

    existing = _epic_for_msg_id(repo_root, msg_id)
    if existing is not None:
        return None, "skipped", "existing_epic_matches_msg_id"

    body = _extract_body(record)
    meta = record.get("meta") if isinstance(record.get("meta"), dict) else {}

    title = _extract_epic_title(record)
    shipped_at = (
        record.get("shipped_at")
        or meta.get("shipped_at")
        or _utc_now_iso()
    )
    shipped_by_seat = (
        record.get("shipped_by_seat")
        or meta.get("shipped_by_seat")
        or _extract_author(record).lstrip("@")
        or "unknown"
    )
    scope = (
        record.get("scope")
        or meta.get("scope")
        or "repo:parley-synced"
    )
    sprint_id = record.get("sprint_id") or meta.get("sprint_id")
    charter_ref = record.get("charter_ref") or meta.get("charter_ref")
    land_commit = record.get("land_commit") or meta.get("land_commit")
    load_artifacts = (
        record.get("load_artifacts")
        or meta.get("load_artifacts")
        or []
    )
    broadcast_msg_id = (
        record.get("broadcast_msg_id")
        or meta.get("broadcast_msg_id")
        or msg_id
    )
    supersedes_msg_id = (
        record.get("supersedes_msg_id") or meta.get("supersedes_msg_id")
    )

    path = record_epic_shipped(
        repo_root=repo_root,
        title=title,
        scope=scope,
        shipped_at=shipped_at,
        shipped_by_seat=shipped_by_seat,
        parley_ship_epic_msg_id=msg_id,
        sprint_id=sprint_id,
        charter_ref=charter_ref,
        land_commit=land_commit,
        load_artifacts=list(load_artifacts)
        if isinstance(load_artifacts, list) else [],
        broadcast_msg_id=broadcast_msg_id,
        linked_msg_ids=[msg_id],
        supersedes_msg_id=supersedes_msg_id,
    )
    return path, "recorded", None


def _extract_epic_title(record: dict) -> str:
    body = _extract_body(record)
    for line in body.splitlines():
        s = line.strip()
        if s.lower().startswith(("epic:", "shipped:")):
            return (s.split(":", 1)[1].strip() or "(unspecified epic)")[:200]
    for line in body.splitlines():
        s = line.strip()
        if s:
            return s[:80]
    return "(unspecified epic)"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def sync_chat_jsonl(
    *,
    repo_root: Path,
    session_id: str,
    chat_records: list[dict],
    cursor_path: Path | None = None,
    log_path: Path | None = None,
    write_log: bool = True,
) -> SyncResult:
    """Idempotently record durable parley Kinds as workshop-lite entities.

    Parameters
    ----------
    repo_root
        Repo root path (the parent of ``.claude/`` and ``docs/``).
    session_id
        The parley session id whose cursor / state is keyed under
        ``cursor['sessions'][session_id]``.
    chat_records
        Pre-parsed parley records (CALLER ran ``parley get --kind ...
        --since <cursor> --json``). The library does NOT shell out to
        parley (Hard Rule 1). Each record is a dict with at minimum
        ``id`` (msg-id) and ``kind``; ``raw``/``body``/``from``/``ts``
        and Kind-specific metadata are consumed when present.
    cursor_path
        Override the default cursor location
        (``.claude/scripts/dev-mgmt/.sync_cursor.json``).
    log_path
        Override the default log location
        (``.claude/scripts/dev-mgmt/.sync_log.jsonl``).
    write_log
        When True (default), append a row per record to the log file.

    Returns
    -------
    SyncResult
        Per-call summary. The cursor file is updated in place; the
        caller can use ``result.recorded`` / ``result.failed`` for
        downstream metrics.

    Idempotency
    -----------
    Three layers per sub-spec §3:

    1. **Cursor primary**: ``last_msg_id`` advances monotonically. The
       caller is responsible for passing only records ``--since
       <last_msg_id>``.
    2. **Cursor defense-in-depth**: ``synced_msg_ids_recent_50`` filters
       out msg-ids re-presented out-of-order (chat.jsonl rewrite, parley
       replay).
    3. **File-level**: every per-Kind dispatcher checks
       ``linked_msg_ids`` of existing entity files of the same type
       before writing.

    Cursor update timing
    --------------------
    Per sub-spec §3 + §9 failure-mode #3: the cursor advances ONLY
    after a successful entity-write OR an explicit skip-with-reason.
    A raised exception during write does NOT advance the cursor for
    that msg-id; the next run retries.
    """
    repo = Path(repo_root)
    if cursor_path is None:
        cursor_path = _default_cursor_path(repo)
    else:
        cursor_path = Path(cursor_path)
    if log_path is None:
        log_path = _default_log_path(repo)
    else:
        log_path = Path(log_path)

    cursor = load_cursor(cursor_path)
    sessions = cursor.setdefault("sessions", {})
    session_state = sessions.setdefault(session_id, {
        "last_msg_id": None,
        "last_sync_ts": None,
        "synced_msg_ids_recent_50": [],
    })
    recent_seen: list[str] = list(
        session_state.get("synced_msg_ids_recent_50") or []
    )
    recent_seen_set = set(recent_seen)

    result = SyncResult(session_id=session_id)

    for record in chat_records:
        if not isinstance(record, dict):
            result.dropped += 1
            continue

        msg_id = record.get("id")
        kind = _normalize_kind(record.get("kind"))

        # Defense-in-depth idempotency (§3.1 rule 2): already-processed
        # msg-id → skip silently, do NOT count as dropped/failed.
        if isinstance(msg_id, str) and msg_id in recent_seen_set:
            result.skipped += 1
            result.processed += 1
            if write_log:
                result.log_entries.append({
                    "ts": _utc_now_iso(),
                    "session": session_id,
                    "msg_id": msg_id,
                    "kind": kind,
                    "action": "skipped",
                    "reason": "synced_msg_ids_recent_50_hit",
                })
            continue

        # Sub-spec §2 — un-synced Kinds dropped silently.
        if kind not in _SYNCED_KINDS:
            result.dropped += 1
            if write_log:
                result.log_entries.append({
                    "ts": _utc_now_iso(),
                    "session": session_id,
                    "msg_id": msg_id,
                    "kind": kind,
                    "action": "dropped",
                    "reason": "kind_not_synced",
                })
            continue

        # Dispatch by Kind.
        # NOTE: EPIC_SHIPPED is intentionally absent — auto-sync deferred
        # per D-WL-22; entity type + manual writer remain in this module.
        try:
            if kind == "DECISION":
                path, action, reason = _record_decision_from_kind(
                    repo_root=repo, record=record,
                )
            elif kind == "BLOCKER_RAISED":
                path, action, reason = _record_blocker_raised_from_kind(
                    repo_root=repo, record=record,
                )
            elif kind == "BLOCKER_RESOLVED":
                path, action, reason = _record_blocker_resolved_from_kind(
                    repo_root=repo, record=record,
                )
            else:  # pragma: no cover — defensive
                path, action, reason = None, "skipped", "unknown_kind"
        except Exception as exc:
            # Write failure: cursor NOT advanced for this msg-id.
            result.failed += 1
            if write_log:
                result.log_entries.append({
                    "ts": _utc_now_iso(),
                    "session": session_id,
                    "msg_id": msg_id,
                    "kind": kind,
                    "action": "failed",
                    "error": f"{type(exc).__name__}: {exc}",
                })
            continue

        # Successful record OR skip-with-reason: advance the cursor.
        result.processed += 1
        if action == "recorded" and path is not None:
            result.recorded += 1
            result.entity_paths.append(path)
        else:
            result.skipped += 1

        if isinstance(msg_id, str):
            result.last_msg_id = msg_id
            recent_seen.append(msg_id)
            recent_seen_set.add(msg_id)
            session_state["last_msg_id"] = msg_id

        if write_log:
            log_row = {
                "ts": _utc_now_iso(),
                "session": session_id,
                "msg_id": msg_id,
                "kind": kind,
                "action": action,
            }
            if reason:
                log_row["reason"] = reason
            if path is not None:
                try:
                    log_row["entity_path"] = str(
                        path.relative_to(repo)
                    )
                except (ValueError, AttributeError):
                    log_row["entity_path"] = str(path)
            result.log_entries.append(log_row)

    # Trim recent-seen list to last N (sub-spec §3.1 rule 2).
    if len(recent_seen) > _CURSOR_RECENT_LIMIT:
        recent_seen = recent_seen[-_CURSOR_RECENT_LIMIT:]
    session_state["synced_msg_ids_recent_50"] = recent_seen
    session_state["last_sync_ts"] = _utc_now_iso()

    _save_cursor(cursor_path, cursor)
    if write_log and result.log_entries:
        _append_log(log_path, result.log_entries)

    return result


def _append_log(log_path: Path, entries: list[dict]) -> None:
    """Append JSONL rows to the sync log. Per sub-spec §8.1 + §9
    failure-mode #3: never raise from the log path; an unwritable log
    is silent (the cursor + entity files are the source of truth)."""
    if not entries:
        return
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as fp:
            for entry in entries:
                fp.write(json.dumps(entry, default=str) + "\n")
    except OSError:
        # Hard Rule 5: never block. Caller already has the result in
        # memory via SyncResult.log_entries.
        return


# ---------------------------------------------------------------------------
# Config loader (sub-spec §7)
# ---------------------------------------------------------------------------


def load_sync_config(repo_root: Path) -> dict:
    """Read the ``[sync_from_parley]`` section of the consolidated
    ``.claude/workshop-lite-config.toml``.

    Per master design §4.4 + MED #5: the consolidated config lives at
    ``<repo>/.claude/workshop-lite-config.toml`` (Hard Rule 3 prefix).
    Each section is OPTIONAL + ADDITIVE; absent file / absent section /
    malformed TOML all degrade to the documented defaults (Hard Rule 5
    — never block).

    Defaults (sub-spec §7):
      ``enabled = False``
      ``sessions = []``
      ``cursor_path = '.claude/scripts/dev-mgmt/.sync_cursor.json'``
      ``log_path = '.claude/scripts/dev-mgmt/.sync_log.jsonl'``
      ``log_retention_days = 30``
    """
    defaults = {
        "enabled": False,
        "sessions": [],
        "cursor_path": _CURSOR_REL,
        "log_path": _LOG_REL,
        "log_retention_days": 30,
    }
    cfg_path = Path(repo_root) / ".claude" / "workshop-lite-config.toml"
    if not cfg_path.exists():
        return defaults
    try:
        import tomllib
        data = tomllib.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception:
        return defaults
    section = data.get("sync_from_parley") if isinstance(data, dict) else None
    if not isinstance(section, dict):
        return defaults

    out = dict(defaults)
    val = section.get("enabled")
    if isinstance(val, bool):
        out["enabled"] = val
    val = section.get("sessions")
    if isinstance(val, list):
        out["sessions"] = [str(s) for s in val if isinstance(s, str)]
    val = section.get("cursor_path")
    if isinstance(val, str) and val:
        out["cursor_path"] = val
    val = section.get("log_path")
    if isinstance(val, str) and val:
        out["log_path"] = val
    val = section.get("log_retention_days")
    if isinstance(val, int) and val >= 0:
        out["log_retention_days"] = val
    return out


def is_enabled(repo_root: Path) -> bool:
    """Convenience: return True iff sync-from-parley is opted in per
    ``.claude/workshop-lite-config.toml`` ``[sync_from_parley] enabled``.

    Default OFF (sub-spec §7). Failures degrade to False (silent no-op).
    """
    return bool(load_sync_config(repo_root).get("enabled"))
