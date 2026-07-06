"""Advisory drift checks for standing-dispatch entities (sub-spec §6).

Six rules, all ADVISORY (same convention as ``wip_claim_checks.py``):

  - V1 UNRECOGNIZED-RECIPIENT — recipient FQID not in roster (WARN; --strict ERROR).
  - V2 EXPIRED-NOT-CLOSED      — status=standing past expires_at + 24h grace
                                 (WARN; --strict ERROR).
  - V3 DEADLINE-MISSED         — status=standing past deadline (INFO).
  - V4 SUPERSEDES-CANDIDATE    — newer dispatch w/ same scope + overlapping
                                 recipients exists (INFO).
  - V5 ALL-RECIPIENTS-ACKED    — every recipient acted_on per parley primitive #1
                                 (INFO; SKIPs when parley absent).
  - V6 ORPHAN-MSG-ID           — linked_msg_id not found in any session (WARN).

PARLEY-AGNOSTIC (CLAUDE.md Hard Rule 1): this module never imports or
shells out to parley. Roster (V1), delivery-state (V5), and msg-id
resolution (V6) are all caller-supplied — the skill / hook layer
queries parley and hands the data in. When absent, those rules SKIP
silently.

HOOKS-NEVER-BLOCK (Hard Rule 5 / D33): advisory, non-fatal. ``--strict``
upgrades V1 + V2 + V6 to errors at the CLI layer. V3 + V4 + V5 stay INFO
regardless of strict.

NOT A JUDGMENT COMPONENT (Hard Rule 7): each rule is a binary structural
check — set-membership, timestamp compare, exact-string compare.
"""
from __future__ import annotations

from collections import namedtuple
from datetime import datetime, timedelta, timezone
from pathlib import Path

import cross_links
import frontmatter
import ledger_paths

WarningRecord = namedtuple("WarningRecord", ("category", "path", "message"))


_ACTIVE_STATE = "standing"
# Sub-spec §6 V2: 24h grace post-expiry before WARN fires.
_EXPIRED_GRACE = timedelta(hours=24)


def _safe_parse(path: Path) -> dict | None:
    try:
        fm, _body = frontmatter.parse(path)
    except Exception:
        return None
    return fm if isinstance(fm, dict) else None


def _iter_dispatches(repo_root: Path):
    """Yield ``(path, fm)`` for every standing_dispatch entity under
    ``docs/dispatches/``. Index files + parse failures + non-dispatch
    types are silently skipped.
    """
    dispatches_dir = ledger_paths.compat_kind_dir(repo_root, "dispatches")
    if not dispatches_dir.exists():
        return
    for path in sorted(dispatches_dir.glob("*.md")):
        if cross_links.is_index_file(path):
            continue
        fm = _safe_parse(path)
        if fm is None:
            continue
        if fm.get("type") != "standing_dispatch":
            continue
        yield path, fm


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso_utc(value: object) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _format_delta(delta: timedelta) -> str:
    secs = int(delta.total_seconds())
    sign = "" if secs >= 0 else "-"
    secs = abs(secs)
    hours, rem = divmod(secs, 3600)
    minutes = rem // 60
    if hours and minutes:
        return f"{sign}{hours}h{minutes}m"
    if hours:
        return f"{sign}{hours}h"
    return f"{sign}{minutes}m"


# ---------------------------------------------------------------------------
# V1 UNRECOGNIZED-RECIPIENT
# ---------------------------------------------------------------------------

def _check_unrecognized_recipients(
    repo_root: Path,
    *,
    roster: set[str] | None,
) -> list[WarningRecord]:
    """V1 UNRECOGNIZED-RECIPIENT — recipient FQID not in roster.

    ``roster`` is the set of FQID member strings believed to be live.
    When ``None`` (parley absent or roster not supplied), V1 is silently
    SKIPPED — Hard Rule 1 parley-agnostic-at-base.
    """
    if roster is None:
        return []
    warnings: list[WarningRecord] = []
    for path, fm in _iter_dispatches(repo_root):
        if fm.get("status") != _ACTIVE_STATE:
            continue
        for r in (fm.get("recipients") or []):
            if not isinstance(r, str) or not r:
                continue
            if r not in roster:
                warnings.append(WarningRecord(
                    category="standing_dispatch_unrecognized_recipient",
                    path=str(path),
                    message=(
                        f"standing_dispatch {fm.get('id')!r} recipient "
                        f"{r!r} not in roster"
                    ),
                ))
    return warnings


# ---------------------------------------------------------------------------
# V2 EXPIRED-NOT-CLOSED
# ---------------------------------------------------------------------------

def _check_expired_not_closed(
    repo_root: Path,
    *,
    now: datetime | None = None,
) -> list[WarningRecord]:
    """V2 EXPIRED-NOT-CLOSED — status=standing AND now > expires_at + 24h grace.

    Per sub-spec §5.1: 24h grace-window post-expiry before WARN fires
    (allows a short actionable window before declaring drift).
    """
    if now is None:
        now = _utc_now()
    warnings: list[WarningRecord] = []
    for path, fm in _iter_dispatches(repo_root):
        if fm.get("status") != _ACTIVE_STATE:
            continue
        exp = _parse_iso_utc(fm.get("expires_at"))
        if exp is None:
            continue
        cutoff = exp + _EXPIRED_GRACE
        if now > cutoff:
            delta = now - exp
            warnings.append(WarningRecord(
                category="standing_dispatch_expired_not_closed",
                path=str(path),
                message=(
                    f"standing_dispatch {fm.get('id')!r} expired "
                    f"(past expires_at by {_format_delta(delta)}); "
                    f"recommend flip to status: expired or extend expires_at"
                ),
            ))
    return warnings


# ---------------------------------------------------------------------------
# V3 DEADLINE-MISSED
# ---------------------------------------------------------------------------

def _check_deadline_missed(
    repo_root: Path,
    *,
    now: datetime | None = None,
) -> list[WarningRecord]:
    """V3 DEADLINE-MISSED — status=standing AND now > deadline.

    Per sub-spec §5.1: deadlines are process signals, not structural —
    always INFO, never WARN, never strict-promotes.
    """
    if now is None:
        now = _utc_now()
    warnings: list[WarningRecord] = []
    for path, fm in _iter_dispatches(repo_root):
        if fm.get("status") != _ACTIVE_STATE:
            continue
        deadline = _parse_iso_utc(fm.get("deadline"))
        if deadline is None:
            continue
        if now > deadline:
            delta = now - deadline
            warnings.append(WarningRecord(
                category="standing_dispatch_deadline_missed",
                path=str(path),
                message=(
                    f"INFO: standing_dispatch {fm.get('id')!r} past "
                    f"deadline by {_format_delta(delta)}; recipient "
                    f"state may need attention"
                ),
            ))
    return warnings


# ---------------------------------------------------------------------------
# V4 SUPERSEDES-CANDIDATE
# ---------------------------------------------------------------------------

def _check_supersedes_candidate(
    repo_root: Path,
) -> list[WarningRecord]:
    """V4 SUPERSEDES-CANDIDATE — newer dispatch with same scope + overlapping
    recipients exists.

    Per sub-spec §4.2: a newer dispatch with the same scope AND
    overlapping recipients is a structural supersede-candidate.
    Always INFO; the actual flip is author-driven.
    """
    warnings: list[WarningRecord] = []
    standing: list[tuple[Path, dict, datetime, set[str], str]] = []
    for path, fm in _iter_dispatches(repo_root):
        if fm.get("status") != _ACTIVE_STATE:
            continue
        created = _parse_iso_utc(fm.get("created_at"))
        if created is None:
            continue
        scope = fm.get("scope")
        if not isinstance(scope, str):
            continue
        recipients = set(
            r for r in (fm.get("recipients") or [])
            if isinstance(r, str) and r
        )
        standing.append((path, fm, created, recipients, scope))

    # For each pair (older, newer) where scope matches AND recipients
    # overlap, surface the older as a supersede-candidate.
    seen: set[tuple[str, str]] = set()
    for i in range(len(standing)):
        for j in range(len(standing)):
            if i == j:
                continue
            a_path, a_fm, a_created, a_recipients, a_scope = standing[i]
            b_path, b_fm, b_created, b_recipients, b_scope = standing[j]
            if a_scope != b_scope:
                continue
            if not (a_recipients & b_recipients):
                continue
            if a_created >= b_created:
                continue
            # `a` is older than `b`; `a` is the supersede-candidate.
            a_id = str(a_fm.get("id") or a_path.stem)
            b_id = str(b_fm.get("id") or b_path.stem)
            if (a_id, b_id) in seen:
                continue
            seen.add((a_id, b_id))
            warnings.append(WarningRecord(
                category="standing_dispatch_supersedes_candidate",
                path=str(a_path),
                message=(
                    f"INFO: standing_dispatch {a_id!r} may be superseded "
                    f"by {b_id!r} (same scope + overlapping recipients)"
                ),
            ))
    return warnings


# ---------------------------------------------------------------------------
# V5 ALL-RECIPIENTS-ACKED (parley primitive #1 query)
# ---------------------------------------------------------------------------

def _check_all_recipients_acked(
    repo_root: Path,
    *,
    delivery_state: dict[tuple[str, str], str] | None = None,
) -> list[WarningRecord]:
    """V5 ALL-RECIPIENTS-ACKED — every recipient ``acted_on`` per parley
    primitive #1 query.

    ``delivery_state`` is caller-supplied: a mapping
    ``(msg_id, recipient_fqid) -> state_string`` (e.g.
    ``{("msg-abc", "wl-rearch:wl-plan"): "acted_on"}``). When ``None``
    (parley absent or query unavailable), V5 SKIPs silently — Hard Rule
    1 parley-agnostic-at-base.

    Per sub-spec §10 + D-WL-20 element 1: composition is one-way READ
    (WL reads primitive #1 state). The query API call shape lives at
    the skill / hook layer (the brief's adapter location); this lib
    receives the pre-resolved mapping.

    Multi-recipient (sub-spec §4.3): default semantics are
    all-recipients (every recipient ack'd). When ``satisfy_quorum: N``
    is declared on a dispatch, we also surface V5-QUORUM at N (sub-spec
    Q-SD-3 proposed resolution: TWO distinct INFO variants, author
    chooses).
    """
    if delivery_state is None:
        return []
    warnings: list[WarningRecord] = []
    for path, fm in _iter_dispatches(repo_root):
        if fm.get("status") != _ACTIVE_STATE:
            continue
        msg_ids = [
            m for m in (fm.get("linked_msg_ids") or [])
            if isinstance(m, str) and m
        ]
        if not msg_ids:
            continue
        recipients = [
            r for r in (fm.get("recipients") or [])
            if isinstance(r, str) and r
        ]
        if not recipients:
            continue
        # Union across linked msg-ids: a recipient is acted_on if ANY
        # of the linked msg-ids registers acted_on for that recipient.
        acked: set[str] = set()
        for r in recipients:
            for mid in msg_ids:
                if delivery_state.get((mid, r)) == "acted_on":
                    acked.add(r)
                    break
        if not acked:
            continue
        dispatch_id = fm.get("id")
        quorum = fm.get("satisfy_quorum")
        if isinstance(quorum, int) and quorum >= 1:
            # Sub-spec Q-SD-3 proposed: V5-QUORUM at N (separate INFO).
            if len(acked) >= quorum:
                warnings.append(WarningRecord(
                    category="standing_dispatch_quorum_acked",
                    path=str(path),
                    message=(
                        f"INFO: standing_dispatch {dispatch_id!r} quorum "
                        f"reached ({len(acked)}/{quorum} recipients "
                        f"acted_on); recommend flip to status: satisfied"
                    ),
                ))
        if len(acked) == len(set(recipients)):
            warnings.append(WarningRecord(
                category="standing_dispatch_all_recipients_acked",
                path=str(path),
                message=(
                    f"INFO: standing_dispatch {dispatch_id!r} all "
                    f"recipients acted_on; recommend flip to status: "
                    f"satisfied"
                ),
            ))
    return warnings


# ---------------------------------------------------------------------------
# V6 ORPHAN-MSG-ID
# ---------------------------------------------------------------------------

def _check_orphan_msg_ids(
    repo_root: Path,
    *,
    known_msg_ids: set[str] | None = None,
) -> list[WarningRecord]:
    """V6 ORPHAN-MSG-ID — linked_msg_ids entry doesn't resolve.

    ``known_msg_ids`` is caller-supplied: the set of all parley msg-ids
    visible across sessions' chat.jsonl. When ``None`` (parley absent
    or resolution unavailable), V6 SKIPs silently — Hard Rule 1.
    """
    if known_msg_ids is None:
        return []
    warnings: list[WarningRecord] = []
    for path, fm in _iter_dispatches(repo_root):
        msg_ids = fm.get("linked_msg_ids") or []
        for mid in msg_ids:
            if not isinstance(mid, str) or not mid:
                continue
            if mid not in known_msg_ids:
                warnings.append(WarningRecord(
                    category="standing_dispatch_orphan_msg_id",
                    path=str(path),
                    message=(
                        f"standing_dispatch {fm.get('id')!r} "
                        f"linked_msg_id {mid!r} not found in any session"
                    ),
                ))
    return warnings


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_standing_dispatch_checks(
    repo_root: str | Path,
    *,
    roster: set[str] | None = None,
    delivery_state: dict[tuple[str, str], str] | None = None,
    known_msg_ids: set[str] | None = None,
    now: datetime | None = None,
) -> list[WarningRecord]:
    """Run all six V1-V6 advisory checks against ``repo_root``.

    Returns a flat list of warnings; the caller concatenates with its
    own. Advisory-only; the ``--strict`` CLI flag is the only path to
    non-zero exit, and only V1 + V2 + V6 promote under strict (V3 / V4
    / V5 stay INFO).

    Parley-dependent inputs (roster / delivery_state / known_msg_ids)
    are all optional — when None, the respective rule SKIPs silently
    (Hard Rule 1 parley-agnostic-at-base).
    """
    repo_root = Path(repo_root)
    warnings: list[WarningRecord] = []
    warnings.extend(_check_unrecognized_recipients(repo_root, roster=roster))
    warnings.extend(_check_expired_not_closed(repo_root, now=now))
    warnings.extend(_check_deadline_missed(repo_root, now=now))
    warnings.extend(_check_supersedes_candidate(repo_root))
    warnings.extend(
        _check_all_recipients_acked(repo_root, delivery_state=delivery_state)
    )
    warnings.extend(
        _check_orphan_msg_ids(repo_root, known_msg_ids=known_msg_ids)
    )
    return warnings


# Categories that --strict promotes to ERROR.
# Per sub-spec §6: V1 + V2 + V6 promote; V3 + V4 + V5 stay INFO.
STRICT_PROMOTING_CATEGORIES: frozenset[str] = frozenset({
    "standing_dispatch_unrecognized_recipient",
    "standing_dispatch_expired_not_closed",
    "standing_dispatch_orphan_msg_id",
})
