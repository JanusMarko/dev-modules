"""WIP-claim entity writer (Phase 1 of the workshop-lite re-arch arc).

Per the binding sub-spec at
``docs/design/2026-05-29-wl-wip-claim-spec.md``: codify a first-class
entity for "this seat is mid-work on these paths, with this declared
scope, until this expiry." Closes the empirical pain at
maxai (charter §4 failure #2 / MAI-PM xreq-f21116ddb9fb finding #2):
N-file uncommitted working tree with no machine-readable per-seat
ownership record.

PARLEY-AGNOSTIC (CLAUDE.md Hard Rule 1): this module NEVER imports
or shells out to parley. The ``seat`` value is supplied by the
caller — the skill layer (``.claude/skills/record-wip/``) computes
it from ``parley whoami`` and hands it in. Roster lookups for the
V1 ORPHANED validator advisory live in the skill / hook layer too;
the library only accepts a pre-built roster set.

WORKSHOP-IMPORTABLE (CLAUDE.md Hard Rule 2): the §3 frontmatter
schema maps 1:1 to a future Workshop ``WipClaim`` entity (until then
it imports as ``metadata_`` JSONB on the parent Sprint/Decision per
sub-spec §3 mapping).

Status / token_state isomorphism (composite-audit HIGH #1, sub-spec
§3 amendment): both fields use the SAME enum
``{claimed, committed, released, abandoned}`` and stay 1:1 by
name. ``claimed`` is the active-state name (NOT ``active``).
``status`` interops with Workshop's entity-status column;
``token_state`` carries the WL-internal precise semantics.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import cross_links
import frontmatter as _fm
import index
import ledger_paths
import validators


# ---------------------------------------------------------------------------
# Slug / id helpers (mirror entities.py conventions to stay homogenous)
# ---------------------------------------------------------------------------

_FILENAME_LIMIT = 255
_TMP_SUFFIX = ".md.tmp"


class WipClaimCollisionError(RuntimeError):
    """Raised when a wip-claim filename collision would silently clobber
    a distinct existing claim.

    Per verifier-α HIGH #2 closure: ``_flatten_seat`` collapses ``:`` →
    ``-`` losslessly, so two distinct seat strings (e.g.
    ``wl-rearch:wl-plan`` vs ``wl-rearch-wl-plan``) at the same
    ``created_at`` minute + same slug resolve to the same filename. The
    original implementation called ``frontmatter.write(target, ...)``
    with no exists-check and silently overwrote the prior file. We now
    refuse: if the resolved target exists AND its ``seat`` field
    differs from the incoming seat, raise this exception. Same-seat
    idempotency (§6 of sub-spec) is preserved — `_find_idempotent_match`
    handles that path before this check fires.
    """



def _slugify(text: str) -> str:
    text = (text or "").lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text or "untitled"


def _cap_slug(slug: str, prefix: str) -> str:
    """Cap slug so ``<prefix><slug>.md.tmp`` fits the 255-byte filename limit.

    Mirrors ``entities._cap_slug`` so wip-claim ids carry the same
    by-construction overflow guarantee as Decision / Handoff / Issue.
    """
    budget = _FILENAME_LIMIT - len(prefix) - len(_TMP_SUFFIX)
    if budget <= 0 or len(slug) <= budget:
        return slug if len(slug) <= budget else slug[: max(budget, 0)]
    head = slug[:budget]
    cut = head.rfind("-")
    return (head[:cut] if cut > 0 else head).strip("-") or "untitled"


def _flatten_seat(seat: str) -> str:
    """Per sub-spec §3: FQID seats colon-separated; flatten to hyphens.

    Bare ``wl-plan`` stays ``wl-plan``; FQID ``wl-rearch:wl-plan``
    flattens to ``wl-rearch-wl-plan``. Used for the id's seat-component
    so colons (filesystem-hostile on some shells / Windows) never
    appear in filenames.
    """
    return (seat or "").replace(":", "-")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _iso(ts: datetime) -> str:
    """ISO 8601 with trailing Z, second precision."""
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _format_id(*, created_at: datetime, seat: str, slug: str) -> str:
    date_str = created_at.strftime("%Y-%m-%d")
    hhmm = created_at.strftime("%H%M")
    seat_flat = _flatten_seat(seat) or "unknown"
    prefix = f"{date_str}-{hhmm}-{seat_flat}-"
    return prefix + _cap_slug(slug, prefix)


# ---------------------------------------------------------------------------
# Lifecycle constants (parallel to validators._WIP_*)
# ---------------------------------------------------------------------------

_TERMINAL_STATES = frozenset({"committed", "released", "abandoned"})
_ACTIVE_STATE = "claimed"


# ---------------------------------------------------------------------------
# Idempotency helpers
# ---------------------------------------------------------------------------

def _canonicalize_path(p: str) -> str:
    """Canonicalize a single path string for exact-string comparison.

    Per verifier-α MED #2 closure: V3 PATH-COLLISION + the idempotency
    probe both compare path strings via exact match. ``./foo`` vs
    ``foo`` vs ``foo/`` are the most common everyday agent-divergence
    forms; without canonicalization the collision detector falls silent
    on them. We apply :func:`os.path.normpath` (deterministic, no glob,
    no fuzzy match — stays Hard-Rule-7-clean as a structural normalize,
    not a graded judgment). A leading ``./`` is stripped, trailing
    slashes are collapsed, and ``.`` for the repo root stays ``.``.
    """
    import os.path
    if not isinstance(p, str) or not p:
        return p
    norm = os.path.normpath(p)
    # `normpath('./')` returns `.` — keep that as the repo-root sentinel.
    # `normpath('foo/')` returns `foo`. `normpath('./foo')` returns `foo`.
    return norm


def _normalize_paths(paths: list[str]) -> list[str]:
    """Sort + de-dupe paths for canonical exact-paths-set comparison.

    Per verifier-α MED #2 closure: each path is run through
    :func:`_canonicalize_path` so ``./foo`` / ``foo`` / ``foo/`` collapse
    to the same canonical form before set-comparison. Preserves the
    "exact-string match" V3 contract (sub-spec §5.V3) — normalized
    exact-string is still exact-string; no globbing introduced.
    """
    return sorted(set(
        _canonicalize_path(p) for p in paths if isinstance(p, str)
    ))


def _find_idempotent_match(
    *,
    wip_dir: Path,
    seat: str,
    paths: list[str],
    scope: str,
) -> Path | None:
    """Return the file path of an existing ``claimed`` wip-claim that
    matches seat + exact-paths-set + scope, or ``None``.

    Per sub-spec §6: idempotency is keyed on (seat, exact-paths set,
    scope). Re-recording returns the existing path without writing a
    new file.
    """
    if not wip_dir.exists():
        return None
    target_paths = _normalize_paths(paths)
    for path in sorted(wip_dir.glob("*.md")):
        if path.name == "INDEX.md" or path.name.startswith("INDEX-"):
            continue
        try:
            fm, _body = _fm.parse(path)
        except Exception:
            continue
        if not isinstance(fm, dict):
            continue
        if fm.get("token_state") != _ACTIVE_STATE:
            continue
        if fm.get("seat") != seat:
            continue
        if fm.get("scope") != scope:
            continue
        existing = _normalize_paths(list(fm.get("paths") or []))
        if existing == target_paths:
            return path
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def record_wip_claim(
    *,
    repo_root: Path,
    slug: str,
    paths: list[str],
    scope: str,
    expires_at: datetime | None = None,
    seat: str,
    sprint_id: str | None = None,
    stage: str | None = None,
    linked_msg_ids: list[str] | None = None,
    linked_sprints: list[str] | None = None,
    linked_decisions: list[str] | None = None,
    created_at: datetime | None = None,
    created_by: str | None = None,
    owner_user: str = "user/local",
    title: str | None = None,
) -> Path:
    """Write a wip_claim entity; return the file path.

    Per sub-spec §3 + §6:
    - ``paths`` must be a non-empty list (raises ``ValueError`` otherwise).
    - ``expires_at`` defaults to ``created_at + 4h`` (Q-WL-3 resolution).
    - Idempotency: if a ``claimed`` claim exists with the same seat +
      exact-paths set + scope, returns that path without writing a new file.

    The ``seat`` value is the caller's responsibility (the skill layer
    derives it from ``parley whoami``; this lib stays parley-agnostic
    per Hard Rule 1).
    """
    if not paths:
        raise ValueError("paths must be a non-empty list")
    if not isinstance(paths, list):
        raise ValueError("paths must be a list")
    paths = [str(p) for p in paths]

    repo = Path(repo_root)
    wip_dir = ledger_paths.compat_kind_dir(repo, "wip")

    # Idempotency probe — sub-spec §6 §3.
    existing = _find_idempotent_match(
        wip_dir=wip_dir, seat=seat, paths=paths, scope=scope,
    )
    if existing is not None:
        return existing

    if created_at is None:
        created_at = _utc_now()
    if expires_at is None:
        expires_at = created_at + timedelta(hours=4)

    if created_by is None:
        # Default to the seat string prefixed with @ — but for FQID
        # seats (host:session:member or session:member), strip the
        # host/session prefix so `created_by` carries the bare-member
        # convention used by the rest of the substrate (verifier-α
        # LOW #2 closure: previously `@wl-rearch:wl-plan`; now `@wl-plan`).
        bare = seat.split(":")[-1] if seat else seat
        cb = bare if bare.startswith("@") else f"@{bare}"
        created_by = cb

    slug_clean = _slugify(slug)
    claim_id = _format_id(created_at=created_at, seat=seat, slug=slug_clean)

    # Effective title — used in body H1.
    effective_title = title or f"WIP-claim by {seat}: {slug_clean}"

    fm = {
        "id": claim_id,
        "type": "wip_claim",
        "title": effective_title,
        "seat": seat,
        "paths": list(paths),
        "scope": scope,
        "sprint_id": sprint_id,
        "stage": stage,
        "status": _ACTIVE_STATE,
        "token_state": _ACTIVE_STATE,
        "expires_at": _iso(expires_at),
        "created_at": _iso(created_at),
        "created_by": created_by,
        "linked_sprints": list(linked_sprints or []),
        "linked_decisions": list(linked_decisions or []),
        "linked_msg_ids": list(linked_msg_ids or []),
        "owner_user": owner_user,
    }

    # Strict validator pass — raises ValidationError on schema violation.
    validators.validate_wip_claim(fm)

    body = _initial_body(
        title=effective_title,
        seat=seat,
        paths=paths,
        scope=scope,
        expires_at=expires_at,
    )

    target = wip_dir / f"{claim_id}.md"

    # Pre-write collision guard (verifier-α HIGH #2 closure). If a file
    # at this exact path already exists AND its seat differs from the
    # incoming seat, refuse — two distinct seats flattening to the same
    # filename would otherwise silently clobber each other. Same-seat
    # paths/scope idempotency is handled earlier by
    # `_find_idempotent_match`; an existing file at the target path
    # here therefore means a distinct claim (different paths or scope)
    # if same-seat, or a distinct seat altogether — either way the
    # write would lose information.
    if target.exists():
        try:
            existing_fm, _existing_body = _fm.parse(target)
        except Exception:
            existing_fm = None
        existing_seat = (
            existing_fm.get("seat")
            if isinstance(existing_fm, dict)
            else None
        )
        if existing_seat != seat:
            raise WipClaimCollisionError(
                f"wip_claim collision at {target.name}: incoming "
                f"seat={seat!r} would clobber existing seat="
                f"{existing_seat!r}. Distinct seats with FQID-shapes "
                "that flatten to the same filename are not permitted "
                "(sub-spec §3 + verifier-α HIGH #2). Disambiguate by "
                "slug or wait one minute for a different created_at."
            )
        # Same-seat-same-path-but-different-paths-or-scope: still a
        # clobber risk (idempotency probe failed earlier). Refuse too.
        raise WipClaimCollisionError(
            f"wip_claim collision at {target.name}: same seat={seat!r} "
            "but mismatched paths/scope vs existing claim. "
            "Disambiguate by slug or wait for a different created_at."
        )

    _fm.write(target, fm, body)
    _render_wip_index(wip_dir)
    cross_links.rebuild_link_index(repo)
    return target


def _initial_body(
    *,
    title: str,
    seat: str,
    paths: list[str],
    scope: str,
    expires_at: datetime,
) -> str:
    """Compose the initial body for a freshly-written claim.

    Two sections:
      - **Claim** — seat / scope / expires-at / paths list.
      - **Lifecycle** — empty transition log; appended-to on
        release/extend/etc.
    """
    paths_block = "\n".join(f"- `{p}`" for p in paths) or "- (no paths)"
    lines: list[str] = [
        f"# {title}",
        "",
        "## Claim",
        "",
        f"- **Seat:** `{seat}`",
        f"- **Scope:** `{scope}`",
        f"- **Expires at:** {_iso(expires_at)}",
        "- **Paths:**",
        paths_block,
        "",
        "## Lifecycle",
        "",
        "(transition log appended below as the claim evolves)",
        "",
    ]
    return "\n".join(lines)


def release_wip_claim(
    *,
    repo_root: Path,
    claim_id: str,
    rationale: str | None = None,
    released_at: datetime | None = None,
) -> Path:
    """Transition ``status``/``token_state`` from ``claimed`` to
    ``released``. Append a transition entry to the body Lifecycle
    section. Idempotent if the claim is already terminal (no-op return).

    Per sub-spec §4 + §6: ``released`` is voluntary drop by the seat;
    a terminal-state claim returns unchanged (idempotent).
    """
    repo = Path(repo_root)
    wip_dir = ledger_paths.compat_kind_dir(repo, "wip")
    target = wip_dir / f"{claim_id}.md"
    if not target.exists():
        raise FileNotFoundError(
            f"wip_claim {claim_id!r} not found at {target}"
        )

    fm, body = _fm.parse(target)
    if not isinstance(fm, dict):
        raise ValueError(f"{target}: frontmatter not a mapping")

    current = fm.get("token_state")
    if current in _TERMINAL_STATES:
        # Idempotent: terminal-state claim is a no-op.
        return target

    if released_at is None:
        released_at = _utc_now()
    rel_iso = _iso(released_at)

    fm["status"] = "released"
    fm["token_state"] = "released"
    fm["released_at"] = rel_iso
    if rationale:
        fm["release_rationale"] = rationale

    # Strict re-validate — guards against drift.
    validators.validate_wip_claim(fm)

    body = _append_transition(
        body,
        kind="released",
        when=rel_iso,
        detail=rationale,
    )

    _fm.write(target, fm, body)
    _render_wip_index(wip_dir)
    cross_links.rebuild_link_index(repo)
    return target


def extend_wip_claim(
    *,
    repo_root: Path,
    claim_id: str,
    duration: timedelta,
    extended_at: datetime | None = None,
) -> Path:
    """Extend ``expires_at`` by ``duration``. Append a transition entry.
    INFO + no-op (returns unchanged path) if the claim is terminal.

    Per sub-spec §6: ``record-wip extend`` is idempotent if claim is
    already terminal (committed/released/abandoned).
    """
    repo = Path(repo_root)
    wip_dir = ledger_paths.compat_kind_dir(repo, "wip")
    target = wip_dir / f"{claim_id}.md"
    if not target.exists():
        raise FileNotFoundError(
            f"wip_claim {claim_id!r} not found at {target}"
        )

    fm, body = _fm.parse(target)
    if not isinstance(fm, dict):
        raise ValueError(f"{target}: frontmatter not a mapping")

    current = fm.get("token_state")
    if current in _TERMINAL_STATES:
        # Terminal claims cannot be extended; no-op per sub-spec.
        return target

    old_expires = fm.get("expires_at")
    try:
        old_dt = datetime.fromisoformat(
            str(old_expires).replace("Z", "+00:00"),
        )
    except (ValueError, TypeError) as exc:
        raise ValueError(
            f"{target}: cannot parse expires_at={old_expires!r}: {exc}"
        )

    new_dt = old_dt + duration
    new_iso = _iso(new_dt)
    if extended_at is None:
        extended_at = _utc_now()
    fm["expires_at"] = new_iso

    validators.validate_wip_claim(fm)

    body = _append_transition(
        body,
        kind="extended",
        when=_iso(extended_at),
        detail=(
            f"expires_at: {old_expires} -> {new_iso} "
            f"(+{_format_duration(duration)})"
        ),
    )

    _fm.write(target, fm, body)
    _render_wip_index(wip_dir)
    cross_links.rebuild_link_index(repo)
    return target


def _format_duration(td: timedelta) -> str:
    """Compact ``Xh Ym`` rendering of a timedelta."""
    total_seconds = int(td.total_seconds())
    sign = "-" if total_seconds < 0 else ""
    total_seconds = abs(total_seconds)
    hours, rem = divmod(total_seconds, 3600)
    minutes = rem // 60
    if hours and minutes:
        return f"{sign}{hours}h{minutes}m"
    if hours:
        return f"{sign}{hours}h"
    return f"{sign}{minutes}m"


def _append_transition(
    body: str,
    *,
    kind: str,
    when: str,
    detail: str | None,
) -> str:
    """Append a transition log entry to the body.

    Each entry is one line under the ``## Lifecycle`` section. Idempotent
    structure: appends regardless of what's already present (the lib is
    callable multiple times for non-terminal transitions like ``extend``).
    """
    line = f"- **{kind}** at {when}"
    if detail:
        line += f" — {detail}"
    body = body.rstrip()
    if not body:
        body = "## Lifecycle\n"
    if "## Lifecycle" not in body:
        body += "\n\n## Lifecycle\n"
    return body + "\n" + line + "\n"


# ---------------------------------------------------------------------------
# INDEX rendering (sub-spec §8)
# ---------------------------------------------------------------------------

def _format_expires_delta(expires_iso: str, now: datetime) -> str:
    """Render expires-at as a Δ from ``now`` (e.g. ``in 3h 12m`` or
    ``5h ago``).
    """
    try:
        exp = datetime.fromisoformat(str(expires_iso).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return "(unparseable)"
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    delta = exp - now
    seconds = int(delta.total_seconds())
    abs_secs = abs(seconds)
    hours, rem = divmod(abs_secs, 3600)
    minutes = rem // 60
    if hours and minutes:
        text = f"{hours}h {minutes}m"
    elif hours:
        text = f"{hours}h"
    else:
        text = f"{minutes}m"
    return f"in {text}" if seconds >= 0 else f"{text} ago"


def _load_config(repo: Path) -> dict:
    """Read ``.claude/workshop-lite-config.toml`` (Hard Rule 3 prefix).

    Returns a dict (possibly empty). Failures degrade silently to empty
    (Hard Rule 5 / D33 — never block / never raise from advisory paths).
    """
    cfg_path = repo / ".claude" / "workshop-lite-config.toml"
    if not cfg_path.exists():
        return {}
    try:
        import tomllib
        return tomllib.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _rolling_collapse_days(repo: Path) -> int:
    cfg = _load_config(repo)
    wip = cfg.get("wip") if isinstance(cfg, dict) else None
    if isinstance(wip, dict):
        val = wip.get("rolling_collapse_threshold_days")
        if isinstance(val, int) and val > 0:
            return val
    return 7  # sub-spec §8 default


def _render_wip_index(wip_dir: Path) -> None:
    """Render ``docs/wip/INDEX.md`` per sub-spec §8.

    Two-section layout: ``## Active`` (token_state=claimed) and
    ``## Closed (trailing Nd)`` (committed / released / abandoned).
    A summary count line appears under the title. Closed claims older
    than the rolling-collapse threshold collapse into a single
    rolling-line.
    """
    if not wip_dir.exists():
        return  # nothing to render
    now = _utc_now()
    repo = wip_dir.parent.parent  # docs/wip -> docs -> repo
    threshold_days = _rolling_collapse_days(repo)
    threshold_dt = now - timedelta(days=threshold_days)

    active: list[tuple[str, dict]] = []
    closed_recent: list[tuple[str, dict, datetime]] = []
    collapsed_old: list[tuple[str, dict, datetime]] = []
    abandoned_recent_count = 0
    abandoned_in_window = 0  # tracked separately for summary line

    for path in sorted(wip_dir.glob("*.md")):
        if path.name == "INDEX.md" or path.name.startswith("INDEX-"):
            continue
        try:
            fm, _body = _fm.parse(path)
        except Exception:
            continue
        if not isinstance(fm, dict):
            continue
        state = fm.get("token_state")
        slug = path.stem
        if state == _ACTIVE_STATE:
            active.append((slug, fm))
            continue
        if state not in _TERMINAL_STATES:
            continue
        # Closed: pick a representative timestamp for collapse decision.
        closed_at_iso = (
            fm.get("released_at")
            or fm.get("committed_at")
            or fm.get("abandoned_at")
            or fm.get("expires_at")
            or fm.get("created_at")
        )
        try:
            closed_dt = datetime.fromisoformat(
                str(closed_at_iso).replace("Z", "+00:00"),
            )
            if closed_dt.tzinfo is None:
                closed_dt = closed_dt.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            closed_dt = now
        if closed_dt >= threshold_dt:
            closed_recent.append((slug, fm, closed_dt))
            if state == "abandoned":
                abandoned_recent_count += 1
        else:
            collapsed_old.append((slug, fm, closed_dt))

    committed_recent = sum(
        1 for _s, f, _t in closed_recent if f.get("token_state") == "committed"
    )
    released_recent = sum(
        1 for _s, f, _t in closed_recent if f.get("token_state") == "released"
    )
    abandoned_in_window = abandoned_recent_count

    lines: list[str] = []
    lines.append("# WIP-claim INDEX")
    lines.append("")
    lines.append(
        f"Updated: {_iso(now)} "
        f"({len(active)} active / {committed_recent} committed / "
        f"{released_recent} released / {abandoned_in_window} abandoned "
        f"in trailing {threshold_days}d)"
    )
    lines.append("")
    lines.append("## Active")
    lines.append("")
    if active:
        for slug, fm in sorted(active, key=lambda x: x[0]):
            seat = fm.get("seat") or "?"
            expires_iso = fm.get("expires_at") or ""
            delta = _format_expires_delta(expires_iso, now)
            ts = fm.get("token_state") or "?"
            lines.append(
                f"- [{slug}]({slug}.md) — {seat} — expires {expires_iso} "
                f"({delta}) — `{ts}`"
            )
    else:
        lines.append("(none)")
    lines.append("")
    lines.append(f"## Closed (trailing {threshold_days}d)")
    lines.append("")
    if closed_recent:
        for slug, fm, _t in sorted(
            closed_recent, key=lambda x: x[2], reverse=True,
        ):
            seat = fm.get("seat") or "?"
            ts = fm.get("token_state") or "?"
            lines.append(f"- [{slug}]({slug}.md) — {seat} — `{ts}`")
    else:
        lines.append("(none)")
    if collapsed_old:
        collapsed_old.sort(key=lambda x: x[2])
        oldest = collapsed_old[0][2].strftime("%Y-%m-%d")
        newest = collapsed_old[-1][2].strftime("%Y-%m-%d")
        lines.append("")
        lines.append(
            f"- {len(collapsed_old)} claims collapsed "
            f"(oldest {oldest}, newest {newest})"
        )
    lines.append("")
    content = "\n".join(lines)

    wip_dir.mkdir(parents=True, exist_ok=True)
    index_path = wip_dir / "INDEX.md"
    tmp = index_path.with_suffix(index_path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(index_path)


# ---------------------------------------------------------------------------
# Discovery helpers for state_digest / external surface
# ---------------------------------------------------------------------------

def load_active_claims(repo_root: Path) -> list[dict]:
    """Return the list of active (token_state=claimed) wip-claim
    frontmatter dicts under ``docs/wip/``.

    Each dict adds a ``_path`` key (the source file path as string) and
    a ``_slug`` key (file stem) so callers can render references.
    Failures degrade silently to skip-the-file (advisory layer).
    """
    repo = Path(repo_root)
    wip_dir = ledger_paths.compat_kind_dir(repo, "wip")
    if not wip_dir.exists():
        return []
    out: list[dict] = []
    for path in sorted(wip_dir.glob("*.md")):
        if path.name == "INDEX.md" or path.name.startswith("INDEX-"):
            continue
        try:
            fm, _body = _fm.parse(path)
        except Exception:
            continue
        if not isinstance(fm, dict):
            continue
        if fm.get("token_state") != _ACTIVE_STATE:
            continue
        fm = dict(fm)
        fm["_path"] = str(path)
        fm["_slug"] = path.stem
        out.append(fm)
    return out


# Index column declarations (for the markdown-table side; the bespoke
# §8 layout above is the primary INDEX. These columns are kept as a
# fallback path consistent with index.py conventions in case a future
# caller wants a flat-table rendering.)
def _seat_cell(value: object, _fm: dict, _path: Path) -> str:
    return str(value) if value not in (None, "") else "?"


def _paths_cell(value: object, _fm: dict, _path: Path) -> str:
    if isinstance(value, list):
        return str(len(value))
    return "0"


WIP_CLAIM_COLUMNS = [
    ("ID", "id", index._plain),
    ("Seat", "seat", _seat_cell),
    ("Status", "token_state", index._plain),
    ("Scope", "scope", index._plain),
    ("Paths", "paths", _paths_cell),
    ("Expires", "expires_at", index._date_only),
    ("Created", "created_at", index._date_only),
]
