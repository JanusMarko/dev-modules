"""Standing-dispatch entity writer (Phase 2 of the workshop-lite re-arch arc).

Per the binding sub-spec at
``docs/design/2026-05-29-wl-standing-dispatch-spec.md``: codify a first-
class entity for "this dispatch is load-bearing and must remain front-
of-mind across seat replacements until its recipients act on it."
Closes charter §4 failure #5.

PARLEY-AGNOSTIC (CLAUDE.md Hard Rule 1): this module NEVER imports or
shells out to parley. Recipient FQIDs are caller-supplied strings; the
skill layer (``.claude/skills/record-dispatch/``) computes them via
``parley whoami`` / ``parley roster``. Parley primitive #1 delivery-
state lookups (V5 ALL-RECIPIENTS-ACKED, SessionStart annotations) live
in the skill / hook layer; the library only handles the durable
entity + lifecycle.

WORKSHOP-IMPORTABLE (CLAUDE.md Hard Rule 2): per sub-spec §3.2, the
frontmatter columns map 1:1 to a future Workshop ``StandingDispatch``
entity. WL-specific fields land in ``metadata_`` JSONB.

NOT A JUDGMENT COMPONENT (Hard Rule 7): the entity is a declarative
record + a deterministic 4-state lifecycle (standing / satisfied /
superseded / expired). The validator (`dispatch_checks.py`) applies
binary V1-V6 rules; surfacing is `created_at ASC` deterministic
ordering (sub-spec §7 + §3.2 + §7.1 anti-judgment-creep).
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

import cross_links
import frontmatter as _fm
import ledger_paths
import validators


# ---------------------------------------------------------------------------
# Slug / id helpers (mirror entities.py conventions to stay homogenous)
# ---------------------------------------------------------------------------

_FILENAME_LIMIT = 255
_TMP_SUFFIX = ".md.tmp"


def _slugify(text: str) -> str:
    text = (text or "").lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text or "untitled"


def _cap_slug(slug: str, prefix: str) -> str:
    """Cap slug so ``<prefix><slug>.md.tmp`` fits the 255-byte filename limit.

    Mirrors ``entities._cap_slug`` so dispatch ids carry the same
    by-construction overflow guarantee as Decision / Handoff / Issue.
    """
    budget = _FILENAME_LIMIT - len(prefix) - len(_TMP_SUFFIX)
    if budget <= 0 or len(slug) <= budget:
        return slug if len(slug) <= budget else slug[: max(budget, 0)]
    head = slug[:budget]
    cut = head.rfind("-")
    return (head[:cut] if cut > 0 else head).strip("-") or "untitled"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _iso(ts: datetime) -> str:
    """ISO 8601 with trailing Z, second precision."""
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _next_counter(dispatches_dir: Path, date_str: str) -> int:
    """Per-day NN counter: scan existing dispatch files, return max+1 (min 1).

    Mirrors :func:`entities._next_counter` shape (Decision/Issue/Review use the
    same per-day-NN scheme).
    """
    pattern = re.compile(rf"^{re.escape(date_str)}-(\d{{2}})-")
    max_n = 0
    if dispatches_dir.exists():
        for path in dispatches_dir.glob(f"{date_str}-*.md"):
            m = pattern.match(path.name)
            if m:
                max_n = max(max_n, int(m.group(1)))
    return max_n + 1


def _format_id(*, created_at: datetime, counter: int, slug: str) -> str:
    date_str = created_at.strftime("%Y-%m-%d")
    prefix = f"{date_str}-{counter:02d}-"
    return prefix + _cap_slug(slug, prefix)


# ---------------------------------------------------------------------------
# Lifecycle constants
# ---------------------------------------------------------------------------

_STATUSES = frozenset({"standing", "satisfied", "superseded", "expired"})
_TERMINAL_STATES = frozenset({"satisfied", "superseded", "expired"})
_ACTIVE_STATE = "standing"


# ---------------------------------------------------------------------------
# Idempotency helpers (sub-spec §9: same scope + same exact recipients set +
# same purpose returns existing path, no second write)
# ---------------------------------------------------------------------------

def _find_idempotent_match(
    *,
    dispatches_dir: Path,
    scope: str,
    recipients: list[str],
    purpose: str,
) -> Path | None:
    """Return the file path of an existing ``standing`` dispatch with the same
    scope + exact-recipients set + purpose, or ``None``.

    Per sub-spec §9 idempotency clause: if a standing dispatch already
    matches, return its path without writing.
    """
    if not dispatches_dir.exists():
        return None
    target_recipients = sorted(set(recipients))
    for path in sorted(dispatches_dir.glob("*.md")):
        if path.name == "INDEX.md" or path.name.startswith("INDEX-"):
            continue
        try:
            fm, _body = _fm.parse(path)
        except Exception:
            continue
        if not isinstance(fm, dict):
            continue
        if fm.get("type") != "standing_dispatch":
            continue
        if fm.get("status") != _ACTIVE_STATE:
            continue
        if fm.get("scope") != scope:
            continue
        if fm.get("purpose") != purpose:
            continue
        existing = sorted(set(fm.get("recipients") or []))
        if existing == target_recipients:
            return path
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def record_standing_dispatch(
    *,
    repo_root: Path,
    slug: str,
    purpose: str,
    recipients: list[str],
    expected_outcome: str,
    scope: str,
    deadline: datetime | None = None,
    expires_at: datetime | None = None,
    linked_msg_ids: list[str] | None = None,
    linked_decisions: list[str] | None = None,
    linked_handoffs: list[str] | None = None,
    linked_reviews: list[str] | None = None,
    supersedes: str | None = None,
    satisfy_quorum: int | None = None,
    sprint_id: str | None = None,
    stage: str | None = None,
    created_at: datetime | None = None,
    created_by: str = "@unknown",
    owner_user: str = "user/local",
    title: str | None = None,
) -> Path:
    """Write a standing_dispatch entity; return the file path.

    Per sub-spec §3 + §9:

    - ``recipients`` must be a non-empty list of FQID strings (raises
      ``ValueError`` otherwise).
    - ``purpose`` must be one of ``{charter, brief, governance, routing,
      other}``.
    - ``parley_external_ref`` auto-populated as
      ``workshop-lite-dispatch://<id>`` per D-WL-19 element 2.
    - Idempotency: if a ``standing`` dispatch exists with the same
      scope + exact-recipients set + purpose, returns that path
      without writing a new file.

    The ``created_by`` / ``recipients`` values are the caller's
    responsibility (skill layer derives via ``parley whoami`` /
    ``parley roster``; this lib stays parley-agnostic per Hard Rule 1).
    """
    if not isinstance(recipients, list):
        raise ValueError("recipients must be a list")
    recipients = [str(r) for r in recipients if isinstance(r, str) and r]
    if not recipients:
        raise ValueError("recipients must be a non-empty list of FQID strings")
    if not expected_outcome or not isinstance(expected_outcome, str):
        raise ValueError("expected_outcome must be a non-empty string")
    if not scope or not isinstance(scope, str):
        raise ValueError("scope must be a non-empty string")

    repo = Path(repo_root)
    dispatches_dir = ledger_paths.compat_kind_dir(repo, "dispatches")

    # Idempotency probe — sub-spec §9. When `supersedes` is set the
    # caller is explicitly replacing an existing dispatch; do not
    # collapse onto the dispatch being superseded. (If the probe still
    # matches a DIFFERENT prior with the same shape, we'd return it
    # rather than risk silently creating divergent records.)
    existing = _find_idempotent_match(
        dispatches_dir=dispatches_dir,
        scope=scope,
        recipients=recipients,
        purpose=purpose,
    )
    if existing is not None:
        if supersedes is None or existing.stem != supersedes:
            return existing

    if created_at is None:
        created_at = _utc_now()

    slug_clean = _slugify(slug)
    date_str = created_at.strftime("%Y-%m-%d")
    counter = _next_counter(dispatches_dir, date_str)
    dispatch_id = _format_id(
        created_at=created_at, counter=counter, slug=slug_clean,
    )

    effective_title = title or f"Standing dispatch: {slug_clean}"

    fm = {
        "id": dispatch_id,
        "type": "standing_dispatch",
        "title": effective_title,
        "status": _ACTIVE_STATE,
        "purpose": purpose,
        "scope": scope,
        "sprint_id": sprint_id,
        "stage": stage,
        "recipients": list(recipients),
        "expected_outcome": expected_outcome,
        "deadline": _iso(deadline) if deadline is not None else None,
        "expires_at": _iso(expires_at) if expires_at is not None else None,
        "created_at": _iso(created_at),
        "created_by": created_by,
        "linked_msg_ids": list(linked_msg_ids or []),
        "linked_decisions": list(linked_decisions or []),
        "linked_handoffs": list(linked_handoffs or []),
        "linked_reviews": list(linked_reviews or []),
        # D-WL-19 element 2: URI auto-populated.
        "parley_external_ref": f"workshop-lite-dispatch://{dispatch_id}",
        "satisfy_quorum": satisfy_quorum,
        "supersedes": supersedes,
        "owner_user": owner_user,
    }

    # Strict validator pass — raises ValidationError on schema violation.
    validators.validate_standing_dispatch(fm)

    body = _initial_body(
        title=effective_title,
        purpose=purpose,
        scope=scope,
        recipients=recipients,
        expected_outcome=expected_outcome,
        deadline=deadline,
        expires_at=expires_at,
    )

    target = dispatches_dir / f"{dispatch_id}.md"
    _fm.write(target, fm, body)

    # Bidirectional supersede ref (sub-spec §4.2 + §9 record-dispatch
    # supersede subcommand). If `supersedes` points at a known
    # dispatch, also flip the prior to status=superseded with
    # superseded_by=<new-id>. This is the supersede-on-create
    # convenience — supersede_dispatch() is the explicit verb.
    if supersedes:
        prior_path = dispatches_dir / f"{supersedes}.md"
        if prior_path.exists():
            _flip_to_superseded(prior_path, new_id=dispatch_id)

    _render_dispatch_index(dispatches_dir)
    cross_links.rebuild_link_index(repo)
    return target


def _initial_body(
    *,
    title: str,
    purpose: str,
    scope: str,
    recipients: list[str],
    expected_outcome: str,
    deadline: datetime | None,
    expires_at: datetime | None,
) -> str:
    """Compose the initial body for a freshly-written dispatch.

    Three sections:
      - **Dispatch** — purpose / scope / expected-outcome.
      - **Recipients** — FQID list with one bullet per recipient.
      - **Lifecycle** — empty transition log; appended-to on
        satisfy/supersede.
    """
    recipients_block = "\n".join(f"- `{r}`" for r in recipients) or "- (none)"
    lines: list[str] = [
        f"# {title}",
        "",
        "## Dispatch",
        "",
        f"- **Purpose:** {purpose}",
        f"- **Scope:** `{scope}`",
        f"- **Expected outcome:** {expected_outcome}",
    ]
    if deadline is not None:
        lines.append(f"- **Deadline:** {_iso(deadline)}")
    if expires_at is not None:
        lines.append(f"- **Expires at:** {_iso(expires_at)}")
    lines += [
        "",
        "## Recipients",
        "",
        recipients_block,
        "",
        "## Lifecycle",
        "",
        "(transition log appended below as the dispatch evolves)",
        "",
    ]
    return "\n".join(lines)


def satisfy_dispatch(
    *,
    repo_root: Path,
    dispatch_id: str,
    by_seat: str | None = None,
    rationale: str | None = None,
    satisfied_at: datetime | None = None,
) -> Path:
    """Transition ``status`` from ``standing`` to ``satisfied``. Append a
    transition entry to the body Lifecycle section. Idempotent if the
    dispatch is already terminal (no-op return).

    Per sub-spec §4.1: ``satisfied`` is the recipient explicitly closing
    the dispatch. A terminal-state dispatch returns unchanged.
    """
    repo = Path(repo_root)
    dispatches_dir = ledger_paths.compat_kind_dir(repo, "dispatches")
    target = dispatches_dir / f"{dispatch_id}.md"
    if not target.exists():
        raise FileNotFoundError(
            f"standing_dispatch {dispatch_id!r} not found at {target}"
        )

    fm, body = _fm.parse(target)
    if not isinstance(fm, dict):
        raise ValueError(f"{target}: frontmatter not a mapping")

    current = fm.get("status")
    if current in _TERMINAL_STATES:
        # Idempotent: terminal-state dispatch is a no-op.
        return target

    if satisfied_at is None:
        satisfied_at = _utc_now()
    sat_iso = _iso(satisfied_at)

    fm["status"] = "satisfied"
    fm["satisfied_at"] = sat_iso
    if by_seat:
        fm["satisfied_by"] = by_seat
    if rationale:
        fm["satisfy_rationale"] = rationale

    validators.validate_standing_dispatch(fm)

    detail_parts: list[str] = []
    if by_seat:
        detail_parts.append(f"by {by_seat}")
    if rationale:
        detail_parts.append(rationale)
    detail = " — ".join(detail_parts) if detail_parts else None

    body = _append_transition(
        body,
        kind="satisfied",
        when=sat_iso,
        detail=detail,
    )

    _fm.write(target, fm, body)
    _render_dispatch_index(dispatches_dir)
    cross_links.rebuild_link_index(repo)
    return target


def supersede_dispatch(
    *,
    repo_root: Path,
    new_id: str,
    old_id: str,
    superseded_at: datetime | None = None,
) -> Path:
    """Flip ``<old_id>`` to ``superseded`` and add bidirectional refs
    (``superseded_by``/``supersedes``) per sub-spec §9.

    The new dispatch must already exist. The old dispatch is the one
    whose status flips. Idempotent if old is already terminal.

    Returns the path of the **old** dispatch (the one whose state
    flipped). The caller already has the path to ``new_id``.
    """
    repo = Path(repo_root)
    dispatches_dir = ledger_paths.compat_kind_dir(repo, "dispatches")
    old_path = dispatches_dir / f"{old_id}.md"
    new_path = dispatches_dir / f"{new_id}.md"

    if not old_path.exists():
        raise FileNotFoundError(
            f"standing_dispatch {old_id!r} (to be superseded) not found at "
            f"{old_path}"
        )
    if not new_path.exists():
        raise FileNotFoundError(
            f"standing_dispatch {new_id!r} (the superseder) not found at "
            f"{new_path}"
        )

    if superseded_at is None:
        superseded_at = _utc_now()

    _flip_to_superseded(old_path, new_id=new_id, when=superseded_at)
    _add_supersedes_ref(new_path, old_id=old_id)
    _render_dispatch_index(dispatches_dir)
    cross_links.rebuild_link_index(repo)
    return old_path


def _flip_to_superseded(
    old_path: Path,
    *,
    new_id: str,
    when: datetime | None = None,
) -> None:
    """In-place flip the dispatch at ``old_path`` to status=superseded.

    Idempotent on terminal state (no-op). Used by both
    :func:`supersede_dispatch` and the supersede-on-create path of
    :func:`record_standing_dispatch`.
    """
    fm, body = _fm.parse(old_path)
    if not isinstance(fm, dict):
        return
    if fm.get("status") in _TERMINAL_STATES:
        return
    if when is None:
        when = _utc_now()
    when_iso = _iso(when)
    fm["status"] = "superseded"
    fm["superseded_at"] = when_iso
    fm["superseded_by"] = new_id

    validators.validate_standing_dispatch(fm)

    body = _append_transition(
        body,
        kind="superseded",
        when=when_iso,
        detail=f"by {new_id}",
    )
    _fm.write(old_path, fm, body)


def _add_supersedes_ref(new_path: Path, *, old_id: str) -> None:
    """Add ``supersedes: <old_id>`` to the new dispatch's frontmatter
    if not already set. No body change.
    """
    fm, body = _fm.parse(new_path)
    if not isinstance(fm, dict):
        return
    existing = fm.get("supersedes")
    if existing == old_id:
        return
    fm["supersedes"] = old_id
    validators.validate_standing_dispatch(fm)
    _fm.write(new_path, fm, body)


def _append_transition(
    body: str,
    *,
    kind: str,
    when: str,
    detail: str | None,
) -> str:
    """Append a transition log entry to the body Lifecycle section.

    Mirrors ``wip_claim._append_transition``. Each entry is one line
    under ``## Lifecycle``.
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
# Config + INDEX rendering (sub-spec §8)
# ---------------------------------------------------------------------------

def _load_config(repo: Path) -> dict:
    """Read ``.claude/workshop-lite-config.toml`` (Hard Rule 3 prefix).

    Returns a dict (possibly empty). Failures degrade silently to empty
    (Hard Rule 5 / D33).
    """
    cfg_path = repo / ".claude" / "workshop-lite-config.toml"
    if not cfg_path.exists():
        return {}
    try:
        import tomllib
        return tomllib.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _hide_satisfied_after_days(repo: Path) -> int:
    """Per sub-spec §5.2 / §8 — per-repo config knob with default 30."""
    cfg = _load_config(repo)
    section = cfg.get("dispatches") if isinstance(cfg, dict) else None
    if isinstance(section, dict):
        val = section.get("hide_satisfied_after_days")
        if isinstance(val, int) and val > 0:
            return val
    return 30


def _parse_iso(value: object) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _render_dispatch_index(dispatches_dir: Path) -> None:
    """Render ``docs/dispatches/INDEX.md`` per sub-spec §8.

    Sections:
      - ``## Standing`` — status=standing, sorted by created_at ASC.
      - ``## Satisfied (trailing Nd)`` — status=satisfied, within window.
      - ``## Superseded`` — status=superseded.
      - ``## Expired`` — status=expired.

    Per sub-spec §5.2: satisfied entries past `hide_satisfied_after_days`
    are NOT enumerated; they collapse into a rolling-line.
    """
    if not dispatches_dir.exists():
        return
    now = _utc_now()
    repo = dispatches_dir.parent.parent  # docs/dispatches -> docs -> repo
    threshold_days = _hide_satisfied_after_days(repo)
    from datetime import timedelta
    threshold_dt = now - timedelta(days=threshold_days)

    standing: list[tuple[str, dict, datetime]] = []
    satisfied_recent: list[tuple[str, dict, datetime]] = []
    satisfied_collapsed: list[tuple[str, dict, datetime]] = []
    superseded: list[tuple[str, dict, datetime]] = []
    expired: list[tuple[str, dict, datetime]] = []

    for path in sorted(dispatches_dir.glob("*.md")):
        if path.name == "INDEX.md" or path.name.startswith("INDEX-"):
            continue
        try:
            fm, _body = _fm.parse(path)
        except Exception:
            continue
        if not isinstance(fm, dict):
            continue
        if fm.get("type") != "standing_dispatch":
            continue
        status = fm.get("status")
        slug = path.stem
        created_dt = _parse_iso(fm.get("created_at")) or now
        if status == "standing":
            standing.append((slug, fm, created_dt))
        elif status == "satisfied":
            sat_dt = _parse_iso(fm.get("satisfied_at")) or created_dt
            if sat_dt >= threshold_dt:
                satisfied_recent.append((slug, fm, sat_dt))
            else:
                satisfied_collapsed.append((slug, fm, sat_dt))
        elif status == "superseded":
            sup_dt = _parse_iso(fm.get("superseded_at")) or created_dt
            superseded.append((slug, fm, sup_dt))
        elif status == "expired":
            expired.append((slug, fm, created_dt))

    standing.sort(key=lambda x: x[2])
    satisfied_recent.sort(key=lambda x: x[2], reverse=True)
    superseded.sort(key=lambda x: x[2], reverse=True)
    expired.sort(key=lambda x: x[2], reverse=True)

    summary = (
        f"{len(standing)} standing / {len(satisfied_recent)} satisfied "
        f"/ {len(superseded)} superseded / {len(expired)} expired "
        f"in trailing {threshold_days}d"
    )

    lines: list[str] = []
    lines.append("# Standing-dispatch INDEX")
    lines.append("")
    lines.append(f"Updated: {_iso(now)} ({summary})")
    lines.append("")
    lines.append("## Standing")
    lines.append("")
    if standing:
        lines.append("| ID | Title | Purpose | Scope | Recipients | Deadline |")
        lines.append("|----|-------|---------|-------|------------|----------|")
        for slug, fm, _t in standing:
            title = str(fm.get("title") or "?").replace("|", "\\|")
            purpose = str(fm.get("purpose") or "?").replace("|", "\\|")
            scope = str(fm.get("scope") or "?").replace("|", "\\|")
            recipients = ", ".join(
                str(r) for r in (fm.get("recipients") or [])
            ).replace("|", "\\|")
            deadline = fm.get("deadline") or "none"
            lines.append(
                f"| [{slug}]({slug}.md) | {title} | {purpose} | {scope} | "
                f"{recipients} | {deadline} |"
            )
    else:
        lines.append("(none)")
    lines.append("")

    lines.append(f"## Satisfied (trailing {threshold_days}d)")
    lines.append("")
    if satisfied_recent:
        lines.append("| ID | Title | Satisfied-at |")
        lines.append("|----|-------|--------------|")
        for slug, fm, sat_dt in satisfied_recent:
            title = str(fm.get("title") or "?").replace("|", "\\|")
            sat_at = fm.get("satisfied_at") or "?"
            lines.append(f"| [{slug}]({slug}.md) | {title} | {sat_at} |")
    else:
        lines.append("(none)")
    if satisfied_collapsed:
        satisfied_collapsed.sort(key=lambda x: x[2])
        oldest = satisfied_collapsed[0][2].strftime("%Y-%m-%d")
        newest = satisfied_collapsed[-1][2].strftime("%Y-%m-%d")
        lines.append("")
        lines.append(
            f"- {len(satisfied_collapsed)} dispatches collapsed "
            f"(oldest {oldest}, newest {newest})"
        )
    lines.append("")

    if superseded:
        lines.append("## Superseded")
        lines.append("")
        lines.append("| ID | Title | Superseded-by |")
        lines.append("|----|-------|---------------|")
        for slug, fm, _t in superseded:
            title = str(fm.get("title") or "?").replace("|", "\\|")
            by = str(fm.get("superseded_by") or "?")
            lines.append(f"| [{slug}]({slug}.md) | {title} | {by} |")
        lines.append("")

    if expired:
        lines.append("## Expired")
        lines.append("")
        lines.append("| ID | Title | Expires-at |")
        lines.append("|----|-------|------------|")
        for slug, fm, _t in expired:
            title = str(fm.get("title") or "?").replace("|", "\\|")
            exp = fm.get("expires_at") or "?"
            lines.append(f"| [{slug}]({slug}.md) | {title} | {exp} |")
        lines.append("")

    content = "\n".join(lines)
    if not content.endswith("\n"):
        content += "\n"

    dispatches_dir.mkdir(parents=True, exist_ok=True)
    index_path = dispatches_dir / "INDEX.md"
    tmp = index_path.with_suffix(index_path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(index_path)


# ---------------------------------------------------------------------------
# Discovery helpers for state_digest / external surface (sub-spec §7)
# ---------------------------------------------------------------------------

def load_standing_dispatches(repo_root: Path) -> list[dict]:
    """Return all ``status: standing`` dispatch frontmatter dicts under
    ``docs/dispatches/``.

    Each dict adds ``_path`` (string) and ``_slug`` (file stem) keys.
    Failures degrade silently to skip-the-file (advisory layer).
    Returned in ``created_at ASC`` order per sub-spec §7 (deterministic
    ordering rule — anti-judgment-creep MED #7 amendment).
    """
    repo = Path(repo_root)
    dispatches_dir = ledger_paths.compat_kind_dir(repo, "dispatches")
    if not dispatches_dir.exists():
        return []
    out: list[tuple[datetime, dict]] = []
    for path in sorted(dispatches_dir.glob("*.md")):
        if path.name == "INDEX.md" or path.name.startswith("INDEX-"):
            continue
        try:
            fm, _body = _fm.parse(path)
        except Exception:
            continue
        if not isinstance(fm, dict):
            continue
        if fm.get("type") != "standing_dispatch":
            continue
        if fm.get("status") != _ACTIVE_STATE:
            continue
        fm = dict(fm)
        fm["_path"] = str(path)
        fm["_slug"] = path.stem
        created_dt = _parse_iso(fm.get("created_at")) or _utc_now()
        out.append((created_dt, fm))
    out.sort(key=lambda x: x[0])
    return [fm for _t, fm in out]


def load_dispatches_for_seat(
    repo_root: Path, seat: str,
) -> list[dict]:
    """Return ``status: standing`` dispatches naming ``seat`` as recipient,
    in ``created_at ASC`` order.

    Match is exact-string equality against any element of the dispatch's
    ``recipients[]`` list. Per sub-spec §3.1 + §7: FQID convention is
    caller's responsibility — the lib compares strings literally.
    """
    if not seat:
        return []
    return [
        fm for fm in load_standing_dispatches(repo_root)
        if seat in (fm.get("recipients") or [])
    ]
