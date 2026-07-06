"""PRD entity writer (cross-repo PM-bridge supporting substrate).

Per the binding charter at
``docs/inbox/2026-06-02-prd-entity-cross-repo-pm-bridge-charter.md``: codify
a first-class PRD entity for cross-repo PM-bridge coordination — a non-
technical human PM authors a PRD here in workshop-lite, the parley-side
PM-bridge (par-p0-defect-55 product_manager role_kind + /translate skill)
bridges status UP to PM-readable form, and the multi-repo coordination
convention (par-p0-defect-56 LANDed at a7d6384) carries the
``cross_repo_prds: [<repo>:<id>]`` URI grammar.

Lifecycle (5-state forward-only linear chain per charter §2.1):

    draft → ratified → converting → technical_plan_ready → shipped

Each transition has a dedicated CLI verb (``record-prd-ratify`` etc.) that
stamps the per-state required fields (``ratified_at``/``ratified_by`` /
``technical_plan_url`` / ``shipped_sha``). State-conditional required-
fields enforcement lives in ``validators.validate_prd``; per-state matrix
in ``validators._PRD_PER_STATE_REQUIRED``. Forward-only — no back-
transitions; bidirectional supersede deferred to v2 iff real PM workflow
surfaces the need (par-plan ratify chunk-0 PG-4 disposition).

PARLEY-AGNOSTIC (CLAUDE.md Hard Rule 1): this module NEVER imports or
shells out to parley. The author seat + parley-side cross-references are
caller-supplied strings derived at the skill layer (``parley whoami``).

WORKSHOP-IMPORTABLE (Hard Rule 2): frontmatter columns map 1:1 to a future
Workshop ``PRD`` entity. Until Workshop's heavyweight tier ships PRD type,
all PRD-specific fields land in ``metadata_`` JSONB on import (same
pattern as standing-dispatch).

NOT A JUDGMENT COMPONENT (Hard Rule 7): the entity is a declarative
record + a deterministic 5-state forward-only lifecycle. Validators are
binary structural checks; INDEX surfacing is deterministic ordering
(``state`` group + ``created_at ASC`` within group).
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
# Slug / id helpers (mirror dispatch.py / entities.py for homogeneity)
# ---------------------------------------------------------------------------

_FILENAME_LIMIT = 255
_TMP_SUFFIX = ".md.tmp"


def _slugify(text: str) -> str:
    text = (text or "").lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text or "untitled"


def _cap_slug(slug: str, prefix: str) -> str:
    budget = _FILENAME_LIMIT - len(prefix) - len(_TMP_SUFFIX)
    if budget <= 0 or len(slug) <= budget:
        return slug if len(slug) <= budget else slug[: max(budget, 0)]
    head = slug[:budget]
    cut = head.rfind("-")
    return (head[:cut] if cut > 0 else head).strip("-") or "untitled"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _iso(ts: datetime) -> str:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _next_counter(prds_dir: Path, date_str: str) -> int:
    pattern = re.compile(rf"^{re.escape(date_str)}-(\d{{2}})-")
    max_n = 0
    if prds_dir.exists():
        for path in prds_dir.glob(f"{date_str}-*.md"):
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

# Forward-only linear chain per charter §2.1 + chunk-0 PG-4 ratify.
# Each non-terminal state maps to its single allowed next state. This
# is THE canonical ordering — derive _STATES, _STATE_ORDER, and the
# membership / past-check helpers from it (eliminate-by-construction,
# single source of truth for the 5-state lifecycle).
_FORWARD_TRANSITIONS: dict[str, str] = {
    "draft": "ratified",
    "ratified": "converting",
    "converting": "technical_plan_ready",
    "technical_plan_ready": "shipped",
}
# Derived: full ordered chain (initial → ... → terminal). The first
# state has no inbound edge; the last has no outbound edge. Used for
# _is_past() linear-chain position check + INDEX section ordering.
_STATE_ORDER: list[str] = ["draft", "ratified", "converting",
                            "technical_plan_ready", "shipped"]
_STATES: frozenset[str] = frozenset(_STATE_ORDER)
_INITIAL_STATE = _STATE_ORDER[0]
_TERMINAL_STATE = _STATE_ORDER[-1]


# ---------------------------------------------------------------------------
# Public API — create
# ---------------------------------------------------------------------------

def record_prd(
    *,
    repo_root: Path,
    slug: str,
    title: str,
    scope: str,
    author: str = "@unknown",
    owner_user: str = "user/local",
    pm_summary: str | None = None,
    linked_msg_ids: list[str] | None = None,
    linked_decisions: list[str] | None = None,
    cross_repo_prds: list[str] | None = None,
    created_at: datetime | None = None,
) -> Path:
    """Write a new PRD entity in ``draft`` state; return the file path.

    Per charter §2.1 + §2.3: ``/record-prd`` creates a fresh draft PRD at
    ``docs/prds/<YYYY-MM-DD>-<NN>-<slug>.md``. State transitions happen
    via the dedicated CLI verbs (``ratify_prd`` / ``convert_prd`` /
    ``mark_technical_plan_ready`` / ``ship_prd``); this function only
    handles the draft-creation path.

    ``pm_summary`` (optional) — initial body text for the REQUIRED
    ``## PM Summary`` section (charter AXIS-12 belt-and-suspenders).
    Defaults to a placeholder if omitted; the validator only requires
    the SECTION to exist, not the prose within it.

    ``cross_repo_prds`` — list of ``<repo>:<id>`` references per charter
    AXIS-13 + par-p0-defect-56 multi-repo coordination convention (URI
    grammar canonically lives there; this entity carries the literal
    reference list).
    """
    if not title or not isinstance(title, str):
        raise ValueError("title must be a non-empty string")
    if not scope or not isinstance(scope, str):
        raise ValueError("scope must be a non-empty string")

    repo = Path(repo_root)
    prds_dir = ledger_paths.compat_kind_dir(repo, "prds")

    if created_at is None:
        created_at = _utc_now()

    slug_clean = _slugify(slug)
    date_str = created_at.strftime("%Y-%m-%d")
    counter = _next_counter(prds_dir, date_str)
    prd_id = _format_id(
        created_at=created_at, counter=counter, slug=slug_clean,
    )

    fm = {
        "id": prd_id,
        "type": "prd",
        "title": title,
        "state": _INITIAL_STATE,
        "scope": scope,
        "created_at": _iso(created_at),
        "author": author,
        "owner_user": owner_user,
        "linked_msg_ids": list(linked_msg_ids or []),
        "linked_decisions": list(linked_decisions or []),
        "cross_repo_prds": list(cross_repo_prds or []),
        "parley_external_ref": f"workshop-lite-prd://{prd_id}",
        # Per-state stamped fields; null at draft creation.
        "ratified_at": None,
        "ratified_by": None,
        "technical_plan_url": None,
        "shipped_sha": None,
    }

    validators.validate_prd(fm)

    body = _initial_body(title=title, scope=scope, pm_summary=pm_summary)
    validators.validate_prd_body(body)

    prds_dir.mkdir(parents=True, exist_ok=True)
    target = prds_dir / f"{prd_id}.md"
    _fm.write(target, fm, body)

    _render_prd_index(prds_dir)
    cross_links.rebuild_link_index(repo)
    return target


def _initial_body(
    *,
    title: str,
    scope: str,
    pm_summary: str | None,
) -> str:
    """Compose the initial body for a freshly-created draft PRD.

    Sections:
      - ``# <title>``
      - ``## PM Summary`` — REQUIRED per charter AXIS-12 belt-and-
        suspenders. Defaults to a placeholder if caller omits prose.
      - ``## Scope`` — what the PRD covers.
      - ``## Requirements`` — empty placeholder for the PM author.
      - ``## Lifecycle`` — empty transition log; appended-to on each
        state transition (mirrors dispatch.py / wip_claim.py shape).
    """
    summary = pm_summary or (
        "(PM-readable plain-language summary of what this PRD describes "
        "and why it matters; bridged UP by the parley-side /translate "
        "skill via the par-p0-defect-55 product_manager role_kind.)"
    )
    return "\n".join([
        f"# {title}",
        "",
        "## PM Summary",
        "",
        summary,
        "",
        "## Scope",
        "",
        f"- **Scope tag:** `{scope}`",
        "",
        "## Requirements",
        "",
        "(numbered requirement list — the PM-authored substantive content)",
        "",
        "## Lifecycle",
        "",
        "(transition log appended below as the PRD progresses through states)",
        "",
    ])


# ---------------------------------------------------------------------------
# Public API — state transitions (forward-only linear chain)
# ---------------------------------------------------------------------------

def ratify_prd(
    *,
    repo_root: Path,
    prd_id: str,
    by_seat: str,
    rationale: str | None = None,
    ratified_at: datetime | None = None,
) -> Path:
    """Transition state ``draft → ratified``; stamp ``ratified_at`` +
    ``ratified_by`` (charter §2.2 required-fields-per-state).

    Idempotent on terminal mismatch: if state is already past ``draft``
    (i.e. ratified / converting / technical_plan_ready / shipped), the
    call is a no-op returning the existing path (consistent with the
    dispatch-satisfy idempotency rule).
    """
    if not by_seat or not isinstance(by_seat, str):
        raise ValueError("by_seat must be a non-empty FQID string")
    return _do_transition(
        repo_root=repo_root,
        prd_id=prd_id,
        from_state="draft",
        to_state="ratified",
        transition_at=ratified_at,
        stamp_fields={"ratified_by": by_seat},
        stamp_at_field="ratified_at",
        rationale=rationale,
    )


def convert_prd(
    *,
    repo_root: Path,
    prd_id: str,
    by_seat: str | None = None,
    rationale: str | None = None,
    converted_at: datetime | None = None,
) -> Path:
    """Transition state ``ratified → converting`` (technical-plan dispatch
    fired). Per charter §2.2 there's no per-state required-field at this
    edge other than the transition itself — the technical-plan
    artifact is a SEPARATE entity (dispatch / decision) referenced via
    ``linked_*``; the transition signals "scrum-master picked this up".
    """
    return _do_transition(
        repo_root=repo_root,
        prd_id=prd_id,
        from_state="ratified",
        to_state="converting",
        transition_at=converted_at,
        stamp_fields={},
        stamp_at_field=None,
        rationale=rationale,
        by_seat=by_seat,
    )


def mark_technical_plan_ready(
    *,
    repo_root: Path,
    prd_id: str,
    technical_plan_url: str,
    by_seat: str | None = None,
    rationale: str | None = None,
    marked_at: datetime | None = None,
) -> Path:
    """Transition state ``converting → technical_plan_ready``; stamp
    ``technical_plan_url`` (charter §2.2 required-fields-per-state).
    """
    if not technical_plan_url or not isinstance(technical_plan_url, str):
        raise ValueError(
            "technical_plan_url must be a non-empty string "
            "(charter §2.2: technical_plan_ready requires technical_plan_url)"
        )
    return _do_transition(
        repo_root=repo_root,
        prd_id=prd_id,
        from_state="converting",
        to_state="technical_plan_ready",
        transition_at=marked_at,
        stamp_fields={"technical_plan_url": technical_plan_url},
        stamp_at_field=None,
        rationale=rationale,
        by_seat=by_seat,
    )


def ship_prd(
    *,
    repo_root: Path,
    prd_id: str,
    shipped_sha: str,
    by_seat: str | None = None,
    rationale: str | None = None,
    shipped_at: datetime | None = None,
) -> Path:
    """Transition state ``technical_plan_ready → shipped`` (terminal);
    stamp ``shipped_sha`` (charter §2.2 required-fields-per-state).

    ``shipped`` is ``_TERMINAL_STATE`` — no further transitions per the
    forward-only linear chain (chunk-0 PG-4 ratify).
    """
    if not shipped_sha or not isinstance(shipped_sha, str):
        raise ValueError(
            "shipped_sha must be a non-empty string "
            "(charter §2.2: shipped requires shipped_sha)"
        )
    return _do_transition(
        repo_root=repo_root,
        prd_id=prd_id,
        from_state="technical_plan_ready",
        to_state=_TERMINAL_STATE,
        transition_at=shipped_at,
        stamp_fields={"shipped_sha": shipped_sha},
        stamp_at_field=None,
        rationale=rationale,
        by_seat=by_seat,
    )


def _do_transition(
    *,
    repo_root: Path,
    prd_id: str,
    from_state: str,
    to_state: str,
    transition_at: datetime | None,
    stamp_fields: dict[str, str],
    stamp_at_field: str | None,
    rationale: str | None,
    by_seat: str | None = None,
) -> Path:
    """Generic state-transition helper used by ratify/convert/ready/ship.

    Per charter PG-4 disposition: forward-only linear chain. If current
    state isn't ``from_state``, raise unless the PRD is already past
    ``to_state`` in the chain (idempotent forward-only no-op).
    """
    repo = Path(repo_root)
    prds_dir = ledger_paths.compat_kind_dir(repo, "prds")
    target = prds_dir / f"{prd_id}.md"
    if not target.exists():
        raise FileNotFoundError(f"PRD {prd_id!r} not found at {target}")

    fm, body = _fm.parse(target)
    if not isinstance(fm, dict):
        raise ValueError(f"{target}: frontmatter not a mapping")

    current = fm.get("state")
    if current == to_state or _is_past(current, to_state):
        # Idempotent forward-only no-op (already at-or-past target state).
        return target

    if current != from_state:
        raise ValueError(
            f"PRD {prd_id!r} in state {current!r}; expected {from_state!r} "
            f"for transition to {to_state!r}. Forward-only linear chain "
            "(draft → ratified → converting → technical_plan_ready → "
            "shipped); use the dedicated CLI verb matching the current "
            "state's allowed next state."
        )

    # Edge-sanity: the (from_state, to_state) pair must match the
    # forward-only linear chain encoded in _FORWARD_TRANSITIONS. This
    # guards against caller-side typos in the helpers (ratify_prd /
    # convert_prd / mark_technical_plan_ready / ship_prd) — internal
    # belt-and-suspenders, never reached if helpers are correct.
    if _FORWARD_TRANSITIONS.get(from_state) != to_state:
        raise ValueError(
            f"internal: ({from_state!r} → {to_state!r}) is not a valid "
            f"forward-chain edge per _FORWARD_TRANSITIONS"
        )

    if transition_at is None:
        transition_at = _utc_now()
    when_iso = _iso(transition_at)

    fm["state"] = to_state
    for k, v in stamp_fields.items():
        fm[k] = v
    if stamp_at_field is not None:
        fm[stamp_at_field] = when_iso

    validators.validate_prd(fm)

    detail_parts: list[str] = []
    if by_seat:
        detail_parts.append(f"by {by_seat}")
    for k, v in stamp_fields.items():
        detail_parts.append(f"{k}={v}")
    if rationale:
        detail_parts.append(rationale)
    detail = " — ".join(detail_parts) if detail_parts else None

    body = _append_transition(
        body, kind=to_state, when=when_iso, detail=detail,
    )
    validators.validate_prd_body(body)

    _fm.write(target, fm, body)
    _render_prd_index(prds_dir)
    cross_links.rebuild_link_index(repo)
    return target


def _is_past(current: object, target: str) -> bool:
    """Return True if ``current`` is at-or-past ``target`` in the linear chain.

    Derives the linear order from ``_STATE_ORDER`` (single-source per
    chunk-0 PG-4 ratify); uncovered values (None / typos) return False.
    """
    if not isinstance(current, str) or current not in _STATE_ORDER:
        return False
    if target not in _STATE_ORDER:
        return False
    return _STATE_ORDER.index(current) >= _STATE_ORDER.index(target)


def _append_transition(
    body: str,
    *,
    kind: str,
    when: str,
    detail: str | None,
) -> str:
    """Append a transition log entry to the body Lifecycle section.

    Mirrors ``dispatch._append_transition`` / ``wip_claim._append_transition``.
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
# INDEX rendering (multi-section per state group)
# ---------------------------------------------------------------------------

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


def _render_prd_index(prds_dir: Path) -> None:
    """Render ``docs/prds/INDEX.md``.

    Sections (per state):
      - ``## Draft``
      - ``## Ratified``
      - ``## Converting``
      - ``## Technical-plan-ready``
      - ``## Shipped``

    Within each section: sorted by ``created_at ASC`` for deterministic
    ordering (Hard Rule 7 — no judgment).
    """
    if not prds_dir.exists():
        return
    now = _utc_now()

    by_state: dict[str, list[tuple[str, dict, datetime]]] = {
        s: [] for s in _STATE_ORDER
    }

    for path in sorted(prds_dir.glob("*.md")):
        if path.name == "INDEX.md" or path.name.startswith("INDEX-"):
            continue
        try:
            fm, _body = _fm.parse(path)
        except Exception:
            continue
        if not isinstance(fm, dict):
            continue
        if fm.get("type") != "prd":
            continue
        state = fm.get("state")
        if not isinstance(state, str) or state not in _STATES:
            continue
        created_dt = _parse_iso(fm.get("created_at")) or now
        by_state[state].append((path.stem, fm, created_dt))

    for state in by_state:
        by_state[state].sort(key=lambda x: x[2])

    summary_parts = [
        f"{len(by_state['draft'])} draft",
        f"{len(by_state['ratified'])} ratified",
        f"{len(by_state['converting'])} converting",
        f"{len(by_state['technical_plan_ready'])} technical-plan-ready",
        f"{len(by_state['shipped'])} shipped",
    ]
    summary = " / ".join(summary_parts)

    lines: list[str] = []
    lines.append("# PRD INDEX")
    lines.append("")
    lines.append(f"Updated: {_iso(now)} ({summary})")
    lines.append("")

    section_headings = [
        ("draft", "Draft"),
        ("ratified", "Ratified"),
        ("converting", "Converting"),
        ("technical_plan_ready", "Technical-plan-ready"),
        ("shipped", "Shipped"),
    ]

    for state_key, heading in section_headings:
        lines.append(f"## {heading}")
        lines.append("")
        rows = by_state[state_key]
        if rows:
            lines.append("| ID | Title | Scope | Created |")
            lines.append("|----|-------|-------|---------|")
            for slug, fm, _t in rows:
                title = str(fm.get("title") or "?").replace("|", "\\|")
                scope = str(fm.get("scope") or "?").replace("|", "\\|")
                created = str(fm.get("created_at") or "")[:10]
                lines.append(
                    f"| [{slug}]({slug}.md) | {title} | {scope} | {created} |"
                )
        else:
            lines.append("(none)")
        lines.append("")

    content = "\n".join(lines)
    if not content.endswith("\n"):
        content += "\n"

    prds_dir.mkdir(parents=True, exist_ok=True)
    index_path = prds_dir / "INDEX.md"
    tmp = index_path.with_suffix(index_path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(index_path)


# ---------------------------------------------------------------------------
# Discovery helpers (for state_digest / cross-link / validate.run_checks)
# ---------------------------------------------------------------------------

def load_prds(repo_root: Path) -> list[dict]:
    """Return all PRD frontmatter dicts under ``docs/prds/``.

    Each dict adds ``_path`` and ``_slug`` keys. Failures degrade
    silently to skip-the-file. Ordered by ``created_at ASC`` (Hard
    Rule 7 deterministic ordering).
    """
    repo = Path(repo_root)
    prds_dir = ledger_paths.compat_kind_dir(repo, "prds")
    if not prds_dir.exists():
        return []
    out: list[tuple[datetime, dict]] = []
    for path in sorted(prds_dir.glob("*.md")):
        if path.name == "INDEX.md" or path.name.startswith("INDEX-"):
            continue
        try:
            fm, _body = _fm.parse(path)
        except Exception:
            continue
        if not isinstance(fm, dict):
            continue
        if fm.get("type") != "prd":
            continue
        fm = dict(fm)
        fm["_path"] = str(path)
        fm["_slug"] = path.stem
        created_dt = _parse_iso(fm.get("created_at")) or _utc_now()
        out.append((created_dt, fm))
    out.sort(key=lambda x: x[0])
    return [fm for _t, fm in out]
