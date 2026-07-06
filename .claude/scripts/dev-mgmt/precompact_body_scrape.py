"""PreCompact body-scrape synthesizer (pure library; heuristic-v1).

Resolves master design §4.3 / sub-spec
``docs/design/2026-05-29-wl-precompact-body-scrape-spec.md``: turns the
deterministic scrape rows (produced by the HOOK layer) into a populated
handoff body + frontmatter additions.

This module is JUDGMENT-CLASSIFIED (sub-spec §3 + Hard Rule #7): the
heuristic rule order in §5.7 is a graded disposition. The corpus
PASS verdict + Kris-ratification gate fires AFTER LAND-as-experimental
and gates the flag-flip to default-ON. The deterministic implementation
of §5.7 below is the judgment surface; rule order and thresholds are
the gradable behavior.

**Hard Rule 1 (parley-agnostic library)**: this module performs NO
shell calls, NO parley imports, and NO I/O beyond the inputs.  All
shell / parley calls live in the HOOK layer (``pre-compact.sh``); the
hook produces a fully-populated ``ScrapeResult`` and hands it here.

**Public API** (sub-spec §7):

* :class:`ScrapeResult` — dataclass of all enumerable rows.
* :func:`synthesize_handoff_body` — pure synthesizer; returns
  ``(body_markdown, frontmatter_additions)``.

The HOOK is responsible for the timeout wallclock + the error-fallback
path; this module exposes ``fallback_stub_body`` so the hook can write
the same shape on either branch.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Iterable


# ---------------------------------------------------------------------------
# Dataclasses (sub-spec §7)
# ---------------------------------------------------------------------------


@dataclass
class GitRow:
    """A single ``git log`` row from the scrape window."""

    sha: str
    author: str
    subject: str
    iso_ts: str = ""


@dataclass
class ParleyRow:
    """A single ``parley get`` row, kinds-pre-filtered by the hook.

    ``governance_input`` is intentionally excluded from the hook's
    ``--kind`` filter per master design §4.3 HIGH #3 amendment; the
    sub-spec §5.3 NOTE says governance dispatches surface via the
    standing-dispatch entity-walk in §5.4 instead.
    """

    msg_id: str
    kind: str
    sender: str
    body_first_line: str
    iso_ts: str = ""


@dataclass
class EntityRow:
    """A single entity row read from an INDEX.md table."""

    entity_type: str
    id: str
    title: str
    status: str
    scope: str = ""
    severity: str = ""
    created_at: str = ""


@dataclass
class SprintState:
    """Active sprint snapshot from sub-spec §5.5."""

    sprint_id: str
    stage: str
    tasks: list["TaskRow"] = field(default_factory=list)


@dataclass
class TaskRow:
    """A single task line read from tasks.md (4-state machine)."""

    description: str
    status: str  # pending | in_progress | completed | blocked
    assignee: str = ""


@dataclass
class XreqRow:
    """An open cross-arc xrequest row from sub-spec §5.6."""

    xreq_id: str
    domain_tag: str
    state: str
    expects_response: bool
    ttl_remaining: str = ""
    direction: str = ""  # from | to | both
    from_seat: str = ""


@dataclass
class WipClaim:
    """A WIP-claim entity row (used by render_current_state rule 3)."""

    id: str
    seat: str
    paths: list[str] = field(default_factory=list)
    status: str = "claimed"


@dataclass
class StandingDispatch:
    """A standing-dispatch entity row (used by render_current_state rule 2)."""

    id: str
    seat: str
    scope: str
    status: str = "standing"


@dataclass
class ScrapeResult:
    """Aggregate scrape inputs to the synthesizer (sub-spec §7)."""

    cursor_msg_id: str | None
    cursor_iso_ts: str
    git_commits: list[GitRow] = field(default_factory=list)
    git_status_short: str = ""
    parley_events: list[ParleyRow] = field(default_factory=list)
    entity_walk: dict[str, list[EntityRow]] = field(default_factory=dict)
    active_sprint: SprintState | None = None
    xrequests: list[XreqRow] = field(default_factory=list)
    wip_claims: list[WipClaim] = field(default_factory=list)
    standing_dispatches: list[StandingDispatch] = field(default_factory=list)
    # Surface-to-Kris triggers active per master §10; the hook may
    # pass an enumerated list of trigger ids (e.g. ["§10.3", "§10.7"]).
    # Empty list = no triggers active.
    surface_to_kris_triggers: list[str] = field(default_factory=list)
    # Optional charter open-questions for the current seat / arc, used
    # by render_whats_next rule 3. Empty list = no open standing forks.
    charter_open_questions: list[str] = field(default_factory=list)
    # Cursor window described in human-readable form; goes into the
    # frontmatter `body_scrape_window` additions.
    git_since: str = ""
    parley_since: str = ""
    entity_walk_since: str = ""


# ---------------------------------------------------------------------------
# Stub body (sub-spec §5.8 fallback path; matches existing _auto_handoff_body
# shape so timeout-fallback and error-fallback produce the same artifact the
# old hook produced).
# ---------------------------------------------------------------------------


def fallback_stub_body(*, title: str) -> str:
    """Return the empty-stub body used on fallback paths.

    Matches the section skeleton of the existing
    ``entities._auto_handoff_body`` (the four canonical sections) so
    handoffs written via fallback parse identically to those written
    via the no-synthesizer path. Hook layer chooses this on timeout
    or scrape error.
    """
    lines = [
        f"# {title}",
        "",
        "## Current state",
        "",
        "(body-scrape unavailable; see frontmatter `body_synthesizer_status`)",
        "",
        "## Since last handoff",
        "",
        "(no synthesizer output; check INDEX.md siblings for recent activity)",
        "",
        "## What's next",
        "",
        "TBD",
        "",
        "## Notes",
        "",
        "(auto-generated handoff body; replace with hand-authored content as needed)",
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Synthesizer (sub-spec §5.7)
# ---------------------------------------------------------------------------


def synthesize_handoff_body(
    *,
    scrape: ScrapeResult,
    current_seat: str | None,
    timeout_s: float = 5.0,
    title: str = "Pre-compact snapshot",
) -> tuple[str, dict]:
    """Pure heuristic-v1 synthesizer (sub-spec §5.7).

    Returns ``(body_markdown, frontmatter_additions)``. NO shell calls,
    NO parley import, NO I/O beyond inputs (Hard Rule 1).

    ``timeout_s`` is enforced by a soft wallclock check at the entry
    and after each render step; on overrun the function returns
    ``(fallback_stub_body, {'body_synthesizer_status': 'timeout-fallback'})``
    so the hook can persist the fallback unchanged.

    Per sub-spec §3: the judgment surface is the rule order + relevance
    thresholds in :func:`render_current_state` / :func:`render_whats_next`
    / et al.  The implementation here is deterministic pure code; the
    corpus evaluates whether the deterministic ordering actually surfaces
    the right rows for the right scenarios.
    """
    started = time.monotonic()

    # Below the per-step viability floor, fall back immediately. The
    # heuristic-v1 synth itself is fast (well under 5ms on modern
    # hardware), but every render step costs some non-zero work; any
    # caller-supplied budget that cannot accommodate one render step
    # is treated as a timeout-fallback request (sub-spec §5.8 — the
    # hook layer should always pass timeout_s ≥ 1.0 in practice).
    _STEP_FLOOR_S = 0.01

    def _deadline_hit() -> bool:
        if timeout_s <= 0:
            return True
        return (time.monotonic() - started) >= timeout_s

    if timeout_s < _STEP_FLOOR_S or _deadline_hit():
        return (
            fallback_stub_body(title=title),
            {
                "body_synthesizer": "heuristic-v1",
                "body_synthesizer_status": "timeout-fallback",
                "body_scrape_p99_ms": _elapsed_ms(started),
            },
        )

    sections: list[str] = [f"# {title}", ""]

    try:
        sections.append(render_current_state(scrape, current_seat=current_seat))
        if _deadline_hit():
            raise _SynthTimeout()
        sections.append(render_since_last_handoff(scrape))
        if _deadline_hit():
            raise _SynthTimeout()
        sections.append(render_whats_next(scrape, current_seat=current_seat))
        if _deadline_hit():
            raise _SynthTimeout()
        if scrape.xrequests:
            sections.append(render_cross_arc_state(scrape))
        sections.append(render_notes_placeholder())
    except _SynthTimeout:
        return (
            fallback_stub_body(title=title),
            {
                "body_synthesizer": "heuristic-v1",
                "body_synthesizer_status": "timeout-fallback",
                "body_scrape_p99_ms": _elapsed_ms(started),
            },
        )

    body = "\n".join(s for s in sections if s is not None)
    if not body.endswith("\n"):
        body += "\n"

    fm_add = {
        "body_synthesizer": "heuristic-v1",
        "body_synthesizer_status": "completed",
        "body_scrape_window": {
            "git_since": scrape.git_since or scrape.cursor_iso_ts,
            "parley_since": scrape.parley_since or (scrape.cursor_msg_id or ""),
            "entity_walk_since": scrape.entity_walk_since or scrape.cursor_iso_ts,
        },
        "body_scrape_p99_ms": _elapsed_ms(started),
    }
    return body, fm_add


class _SynthTimeout(Exception):
    """Internal sentinel for the §5.8 timeout fallback path."""


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


# ---------------------------------------------------------------------------
# render_* (sub-spec §5.7.1–5.7.5)
# ---------------------------------------------------------------------------


def render_current_state(
    scrape: ScrapeResult,
    *,
    current_seat: str | None,
) -> str:
    """Render the ``## Current state`` section per sub-spec §5.7.2.

    Rule order (each rule contributes at most one sentence; empty
    rules silently skip; if no rule matches the section renders a
    graceful-empty marker per §5.7.2 trailing clause):

    1. Active sprint exists → name it + stage.
    2. Standing-dispatch for current seat → name charter + scope.
    3. WIP-claim ``claimed`` for current seat → list paths (cap 3+count).
    4. Open xrequest, expects-response, from=current-seat → name it.
    5. Most-recent ratified Decision (status=accepted) in window → title + id.
    """
    parts: list[str] = []

    # Rule 1: active sprint.
    if scrape.active_sprint:
        parts.append(
            f"Active sprint: `{scrape.active_sprint.sprint_id}` at stage `{scrape.active_sprint.stage}`."
        )

    # Rule 2: standing-dispatch for the current seat.
    if current_seat:
        for d in scrape.standing_dispatches:
            if d.seat == current_seat and d.status == "standing":
                parts.append(
                    f"Standing dispatch active: `{d.id}` (scope: {d.scope})."
                )
                break

    # Rule 3: WIP-claim claimed for current seat.
    if current_seat:
        for w in scrape.wip_claims:
            if w.seat == current_seat and w.status == "claimed":
                paths = list(w.paths)
                shown = paths[:3]
                rest = max(0, len(paths) - 3)
                tail = f" (+{rest} more)" if rest else ""
                parts.append(
                    f"WIP-claim `{w.id}` held: {', '.join(shown)}{tail}."
                )
                break

    # Rule 4: open xreq expects-response from current-seat.
    if current_seat:
        for x in scrape.xrequests:
            if (
                x.state in {"open", "accepted"}
                and x.expects_response
                and x.from_seat == current_seat
            ):
                parts.append(
                    f"Blocked awaiting reply on `{x.xreq_id}` {x.domain_tag}."
                )
                break

    # Rule 5: most-recent accepted Decision in window.
    decisions = scrape.entity_walk.get("decisions", [])
    accepted = [d for d in decisions if d.status == "accepted"]
    accepted.sort(key=lambda d: d.created_at, reverse=True)
    if accepted:
        d = accepted[0]
        parts.append(f"Most-recent ratified decision: {d.title} (`{d.id}`).")

    lines = ["## Current state", ""]
    if parts:
        lines.append(" ".join(parts))
    else:
        lines.append("(no notable state at compact moment)")
    return "\n".join(lines)


_SUBSECTION_DECISIONS = ("Decisions", "decisions")
_SUBSECTION_ISSUES = ("Issues", "issues")
_SUBSECTION_REVIEWS = ("Reviews", "reviews")
_SUBSECTION_DISPATCHES = ("Standing-dispatches", "dispatches")
_SUBSECTION_EPICS_SHIPPED = ("Epics shipped", "_epics_shipped")  # parley-derived
_SUBSECTION_BLOCKERS = ("Blockers", "_blockers")  # parley + issues blended


def render_since_last_handoff(scrape: ScrapeResult) -> str:
    """Render ``## Since last handoff`` per sub-spec §5.7.3.

    Only non-empty sub-sections render. Each row formats as
    ``- <id> — <title> (<status>)``. Order within sub-section is
    ``created_at DESC``.
    """
    lines: list[str] = ["## Since last handoff", ""]

    rendered_any = False

    # Decisions: status=accepted in window.
    accepted = [
        d for d in scrape.entity_walk.get("decisions", [])
        if d.status == "accepted"
    ]
    if accepted:
        rendered_any = True
        accepted.sort(key=lambda r: r.created_at, reverse=True)
        lines.append("### Decisions")
        lines.append("")
        for d in accepted:
            lines.append(f"- {d.id} — {d.title} ({d.status})")
        lines.append("")

    # Issues: severity in {high, critical} OR status=open in window.
    issues = [
        i for i in scrape.entity_walk.get("issues", [])
        if i.severity in {"high", "critical"} or i.status == "open"
    ]
    if issues:
        rendered_any = True
        issues.sort(key=lambda r: r.created_at, reverse=True)
        lines.append("### Issues")
        lines.append("")
        for i in issues:
            lines.append(f"- {i.id} — {i.title} ({i.status})")
        lines.append("")

    # Reviews: any finished review in window.
    reviews = [
        r for r in scrape.entity_walk.get("reviews", [])
        if r.status in {"finished", "completed", "ratified"}
    ]
    if reviews:
        rendered_any = True
        reviews.sort(key=lambda r: r.created_at, reverse=True)
        lines.append("### Reviews")
        lines.append("")
        for r in reviews:
            lines.append(f"- {r.id} — {r.title} ({r.status})")
        lines.append("")

    # Standing-dispatches: any in window.
    dispatches = list(scrape.entity_walk.get("dispatches", []))
    if dispatches:
        rendered_any = True
        dispatches.sort(key=lambda r: r.created_at, reverse=True)
        lines.append("### Standing-dispatches")
        lines.append("")
        for d in dispatches:
            lines.append(f"- {d.id} — {d.title} ({d.status})")
        lines.append("")

    # Epics shipped (parley-derived).
    epics = [p for p in scrape.parley_events if p.kind == "epic_shipped"]
    if epics:
        rendered_any = True
        epics.sort(key=lambda r: r.iso_ts, reverse=True)
        lines.append("### Epics shipped")
        lines.append("")
        for p in epics:
            lines.append(f"- {p.msg_id} — {p.body_first_line} ({p.kind})")
        lines.append("")

    # Blockers: parley BLOCKER_RAISED + high+ severity open Issues.
    blockers_parley = [
        p for p in scrape.parley_events if p.kind == "blocker_raised"
    ]
    blockers_issues = [
        i for i in scrape.entity_walk.get("issues", [])
        if i.status == "open" and i.severity in {"high", "critical"}
    ]
    if blockers_parley or blockers_issues:
        rendered_any = True
        lines.append("### Blockers")
        lines.append("")
        for p in sorted(blockers_parley, key=lambda r: r.iso_ts, reverse=True):
            lines.append(f"- {p.msg_id} — {p.body_first_line} ({p.kind})")
        for i in sorted(blockers_issues, key=lambda r: r.created_at, reverse=True):
            lines.append(f"- {i.id} — {i.title} ({i.status})")
        lines.append("")

    if not rendered_any:
        lines.append("(no substantive events in window)")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


_WHATS_NEXT_CAP = 5


def render_whats_next(
    scrape: ScrapeResult,
    *,
    current_seat: str | None,
) -> str:
    """Render ``## What's next`` per sub-spec §5.7.4 (cap=5 bullets)."""
    bullets: list[str] = []

    # Rule 1: tasks for current seat — in_progress, then pending, then blocked.
    if scrape.active_sprint and scrape.active_sprint.tasks:
        tasks_for_seat = (
            [t for t in scrape.active_sprint.tasks
             if (not current_seat) or t.assignee == current_seat]
            if current_seat is not None
            else list(scrape.active_sprint.tasks)
        )
        ordered = (
            [t for t in tasks_for_seat if t.status == "in_progress"]
            + [t for t in tasks_for_seat if t.status == "pending"]
            + [t for t in tasks_for_seat if t.status == "blocked"]
        )
        for t in ordered:
            bullets.append(
                f"- ({t.status}) {t.description}"
                + (f" — @{t.assignee}" if t.assignee else "")
            )

    # Rule 2: surface-to-Kris triggers.
    for trig in scrape.surface_to_kris_triggers:
        bullets.append(f"- Surface-to-Kris trigger active: {trig}")

    # Rule 3: charter standing-fork-points / unresolved open questions.
    for q in scrape.charter_open_questions:
        bullets.append(f"- Charter open question: {q}")

    # Cap at 5; collapse excess into a single trailing "see tasks.md" bullet.
    if len(bullets) > _WHATS_NEXT_CAP:
        kept = bullets[:_WHATS_NEXT_CAP - 1]
        extra = len(bullets) - (_WHATS_NEXT_CAP - 1)
        kept.append(f"- ({extra} more pending, see tasks.md)")
        bullets = kept

    if not bullets:
        # Rule 4: default fallback.
        bullets = ["- Resume autonomous-arc protocol; no specific next move queued."]

    return "\n".join(["## What's next", "", *bullets])


def render_cross_arc_state(scrape: ScrapeResult) -> str:
    """Render ``## Cross-arc state`` per sub-spec §5.7.5.

    Only renders if there ARE xrequests (the caller checks this);
    sorted by ttl_remaining ASC (soonest-expiring first).
    """
    xs = sorted(
        scrape.xrequests,
        key=lambda x: _ttl_sort_key(x.ttl_remaining),
    )
    lines = ["## Cross-arc state", ""]
    for x in xs:
        exp = "expects-response" if x.expects_response else "informational"
        ttl = x.ttl_remaining or "n/a"
        lines.append(
            f"- xreq-{x.xreq_id} — {x.domain_tag} — state={x.state} — {exp} — TTL {ttl}"
        )
    return "\n".join(lines)


def _ttl_sort_key(ttl: str) -> tuple[int, str]:
    """Coerce a TTL string into a sort key (soonest-first).

    Best-effort: numeric prefixes sort by integer; non-numeric falls
    back to string ordering. Empty TTL sorts last.
    """
    if not ttl:
        return (10**9, "")
    digits = ""
    for ch in ttl:
        if ch.isdigit():
            digits += ch
        else:
            break
    if digits:
        return (int(digits), ttl)
    return (10**9 - 1, ttl)


def render_notes_placeholder() -> str:
    """Render the trailing ``## Notes`` placeholder per sub-spec §4.1."""
    return "\n".join([
        "## Notes",
        "",
        "(reserved for hand-edited subjective context; auto-generated above)",
        "",
    ])


# ---------------------------------------------------------------------------
# Public exports
# ---------------------------------------------------------------------------


__all__ = [
    "ScrapeResult",
    "GitRow",
    "ParleyRow",
    "EntityRow",
    "SprintState",
    "TaskRow",
    "XreqRow",
    "WipClaim",
    "StandingDispatch",
    "synthesize_handoff_body",
    "fallback_stub_body",
    "render_current_state",
    "render_since_last_handoff",
    "render_whats_next",
    "render_cross_arc_state",
    "render_notes_placeholder",
]
