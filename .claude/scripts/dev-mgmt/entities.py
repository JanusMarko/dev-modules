"""Entity-specific write functions for the lightweight dev-mgmt system.

Sprint 1 shipped ``record_decision``. Sprint 2 added ``start_sprint`` /
``end_sprint``. Sprint 3 adds ``record_handoff`` (D6.A schema; fills the
§6 design-doc gap). Sprint 4 adds ``record_issue`` + ``record_review``
(D12-D17 schema refinements). Sprint 5 adds ``add_task`` (inline list
items in a sprint's tasks.md per D19-D21) + ``capture_conversation``
(full §6 Conversation entity with two-section body per D23 and parley-
agnostic verbatim renderer per D27).
"""
from __future__ import annotations

import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

import frontmatter as _fm
import cross_links
import denial as _denial
import index
import ledger_paths
import templates
import validators


def _slugify(text: str) -> str:
    """Lowercase, replace non-alphanumeric runs with hyphens."""
    text = (text or "").lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text or "untitled"


# Sprint S-B D2 (ce1fc36 §3; ADDENDUM substrate-gap (i)) — slug-cap
# by-construction. The entity id is ``<date-NN-prefix><slug>`` and the
# on-disk artifact is ``docs/<kind>/<id>.md`` (the writer also stages a
# sibling ``<id>.md.tmp``). An uncapped slug overflowed the 255-byte
# filesystem filename limit (errno 36, hit at decisions/2026-05-16-05
# and -06 — previously mitigated by manually trimming the title, a
# fragile not-by-construction workaround). ``_cap_slug`` makes the
# overflow STRUCTURALLY IMPOSSIBLE: given the already-formed functional
# prefix it returns the longest slug whose full ``<prefix><slug>.md.tmp``
# filename fits the limit, truncated DETERMINISTICALLY at a hyphen
# boundary. R-B: the date-NN functional prefix is NEVER touched (it is
# passed in already-formed; only the trailing human-readable slug is
# capped) so the D15 id-format contract (parseable, unique) is unbroken.
_FILENAME_LIMIT = 255
_TMP_SUFFIX = ".md.tmp"  # the longest sibling the writer ever forms


def _cap_slug(slug: str, prefix: str) -> str:
    """Longest hyphen-delimited prefix of ``slug`` such that
    ``<prefix><slug>`` + the writer's ``.md.tmp`` sibling fits
    ``_FILENAME_LIMIT``. ``prefix`` is the already-formed functional
    ``<date>-<NN>-`` (or ``<date>-<HHMM>-``) head — NEVER truncated
    (R-B). Deterministic: truncate at the last hyphen ≤ budget; if no
    hyphen fits, hard-cut to the budget (a degenerate single mega-token
    title — still a valid, bounded, unique-by-prefix id)."""
    budget = _FILENAME_LIMIT - len(prefix) - len(_TMP_SUFFIX)
    if budget <= 0 or len(slug) <= budget:
        return slug if len(slug) <= budget else slug[: max(budget, 0)]
    head = slug[:budget]
    cut = head.rfind("-")
    return (head[:cut] if cut > 0 else head).strip("-") or "untitled"


def _today_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _utc_now_iso() -> str:
    """Return current UTC time as ISO 8601 with trailing Z, second precision."""
    now = datetime.now(timezone.utc).replace(microsecond=0)
    return now.strftime("%Y-%m-%dT%H:%M:%SZ")


def _utc_hhmm() -> str:
    """Return current UTC time as HHMM (4 digits, no separators).

    Used by ``record_handoff`` to form the ``YYYY-MM-DD-HHMM-<slug>`` id.
    Collision window: one UTC minute when two handoffs of the same slug fire
    concurrently. Per N3 (sprint 3 plan), we accept the small risk; if it
    surfaces in practice we'll widen to HHMMSS or add a per-minute NN counter.
    """
    return datetime.now(timezone.utc).strftime("%H%M")


def _next_counter(decisions_dir: Path, date_str: str) -> int:
    """Per-day NN counter: scan existing decision files, return max+1 (min 1)."""
    pattern = re.compile(rf"^{re.escape(date_str)}-(\d{{2}})-")
    max_n = 0
    if decisions_dir.exists():
        for path in decisions_dir.glob(f"{date_str}-*.md"):
            m = pattern.match(path.name)
            if m:
                max_n = max(max_n, int(m.group(1)))
    return max_n + 1


def _format_options_block(options: list[dict]) -> str:
    if not options:
        return "(none recorded)"
    lines: list[str] = []
    for opt in options:
        label = opt.get("label", "?")
        verdict = "chosen" if opt.get("chosen") else "rejected"
        reasoning = (opt.get("reasoning") or "").strip()
        if reasoning:
            lines.append(f"- **{label}** ({verdict}): {reasoning}")
        else:
            lines.append(f"- **{label}** ({verdict})")
    return "\n".join(lines)


def record_decision(
    *,
    title: str,
    rationale: str,
    options: list[dict],
    scope: str,
    author: str,
    repo_root: str | Path | None = None,
    authored_with: list[str] | None = None,
    linked_decisions: list[str] | None = None,
    linked_reviews: list[str] | None = None,
    linked_msg_ids: list[str] | None = None,
    sprint_id: str | None = None,
    stage: str | None = None,
    supersedes: str | None = None,
    status: str = "accepted",
    affects: str | None = None,
    owner_user: str = "user/local",
    decision_shape: str | None = None,
) -> Path:
    """Record a Decision entity.

    Loads the decision template, fills frontmatter, validates against the §6
    schema, writes ``docs/decisions/<id>.md``, then re-renders the INDEX.

    Returns the path of the written file. Raises ``ValidationError`` if the
    composed frontmatter fails validation (no file written).
    """
    repo = Path(repo_root) if repo_root else Path.cwd()
    decisions_dir = ledger_paths.compat_kind_dir(repo, "decisions")

    date_str = _today_iso()
    counter = _next_counter(decisions_dir, date_str)
    slug = _slugify(title)
    _prefix = f"{date_str}-{counter:02d}-"
    decision_id = _prefix + _cap_slug(slug, _prefix)  # S-B D2/R-B

    fm, _tpl_body = templates.load("decision", repo_root=repo)
    fm.update({
        "id": decision_id,
        "type": "decision",
        "title": title,
        "status": status,
        "scope": scope,
        "sprint_id": sprint_id,
        "stage": stage,
        "options": list(options),
        "created_at": _utc_now_iso(),
        "author": author,
        "authored_with": list(authored_with or []),
        "linked_decisions": list(linked_decisions or []),
        "linked_reviews": list(linked_reviews or []),
        "linked_msg_ids": list(linked_msg_ids or []),
        "supersedes": supersedes,
        # Phase 4 (master §3.2 + D-WL-11): owner_user threaded through
        # existing v3 entity types as OPTIONAL with default `user/local`.
        # On-disk files without owner_user parse fine (read-time default
        # via validators); new writes populate it.
        "owner_user": owner_user,
        # Cohort C D2 — /auto-decision-doc v1-AUTO categorization. OPTIONAL:
        # None when called from /record-decision direct (no shape detection
        # layer) OR from a pre-D2 caller; populated only when the skill-
        # layer detector classified the shape.
        "decision_shape": decision_shape,
    })

    validators.validate_decision(fm)

    body = "\n".join([
        f"# {title}",
        "",
        "## Why this decision was made",
        "",
        rationale.strip() or "(no rationale provided)",
        "",
        "## Options considered",
        "",
        _format_options_block(options),
        "",
        "## What this affects",
        "",
        (affects.strip() if affects and affects.strip()
         else "(not yet specified)"),
        "",
    ])

    target = decisions_dir / f"{decision_id}.md"
    _fm.write(target, fm, body)
    # par:2026-06-04-13 cohort D D2 — CURATED (C) HYBRID render with
    # auto-rotation. exclude_patterns skips .canonical.md silent siblings
    # per cohort C precedent; preserve_manual_rows keeps any pre-
    # convention headerless rows operators added before the schema era.
    index.render_curated(
        decisions_dir,
        title="Decisions",
        columns=index.DECISION_COLUMNS,
        exclude_patterns=("*.canonical.md",),
        preserve_manual_rows=True,
    )
    cross_links.rebuild_link_index(repo)
    return target


def _strip_frontmatter(text: str) -> str:
    """If ``text`` begins with a ``---\\n...---\\n`` frontmatter block, strip it.

    Used by ``start_sprint`` when ``--from-plan`` points at a file that itself
    has frontmatter (e.g. a previously-written sprint plan.md). The body alone
    becomes the new plan.md body; fresh frontmatter is generated.
    """
    if not text.startswith("---\n"):
        return text
    closer = text.find("\n---\n", 4)
    if closer == -1:
        return text
    return text[closer + len("\n---\n"):]


def _update_sprint_backlog(repo_root: Path, sprint_id: str, status: str) -> bool:
    """Update SPRINT-BACKLOG.md if it exists (D1: skip-if-missing).

    Returns True if an update was made; False if the file was absent or no
    matching entry was found. The update is minimal-impact: any line matching
    ``- [<sprint_id>]`` has its trailing ``status=...`` token rewritten (or
    appended if absent). Format details of SPRINT-BACKLOG.md aren't locked in
    the design yet, so this is intentionally lenient.
    """
    backlog = repo_root / "SPRINT-BACKLOG.md"
    if not backlog.exists():
        return False
    text = backlog.read_text(encoding="utf-8")
    needle = f"- [{sprint_id}]"
    if needle not in text:
        return False
    new_lines: list[str] = []
    touched = False
    for line in text.splitlines():
        if line.lstrip().startswith(needle):
            base = re.sub(r"\s+status=\S+\s*$", "", line)
            new_lines.append(f"{base.rstrip()} status={status}")
            touched = True
        else:
            new_lines.append(line)
    if touched:
        backlog.write_text("\n".join(new_lines) + ("\n" if text.endswith("\n") else ""), encoding="utf-8")
    return touched


def start_sprint(
    *,
    sprint_id: str,
    title: str,
    author: str,
    repo_root: str | Path | None = None,
    plan_body_path: str | Path | None = None,
    force: bool = False,
    linked_design_docs: list[str] | None = None,
    owner_user: str = "user/local",
) -> Path:
    """Scaffold ``docs/sprints/active/sprint-<sprint_id>/`` for a new sprint.

    Writes ``plan.md`` (frontmatter + body) and an empty ``tasks.md`` heading.
    Refreshes ``docs/sprints/INDEX.md`` and (if present) updates the
    SPRINT-BACKLOG.md entry to ``status=in_progress``.

    Returns the path to the written ``plan.md``.
    """
    repo = Path(repo_root) if repo_root else Path.cwd()
    sprints_dir = ledger_paths.compat_sprints_dir(repo)
    sprint_dir = sprints_dir / "active" / f"sprint-{sprint_id}"
    plan_path = sprint_dir / "plan.md"

    if plan_path.exists() and not force:
        raise FileExistsError(
            f"plan.md already exists at {plan_path}; use force=True to overwrite"
        )

    fm, tpl_body = templates.load("sprint-plan", repo_root=repo)
    fm.update({
        "id": f"sprint-{sprint_id}-plan",
        "type": "plan",
        "plan_type": fm.get("plan_type") or "forge",
        "title": title,
        "sprint_id": sprint_id,
        "status": "active",
        "version": 1,
        "previous_version_id": None,
        "created_at": _utc_now_iso(),
        "author": author,
        "linked_design_docs": list(linked_design_docs or []),
        # Phase 4 (master §3.2 + D-WL-11): owner_user threaded through.
        "owner_user": owner_user,
    })

    validators.validate_sprint_plan(fm)

    if plan_body_path is not None:
        body_src = Path(plan_body_path)
        body = _strip_frontmatter(body_src.read_text(encoding="utf-8"))
        if not body.endswith("\n"):
            body += "\n"
    else:
        body = tpl_body.replace("(title)", title, 1)

    sprint_dir.mkdir(parents=True, exist_ok=True)
    _fm.write(plan_path, fm, body)

    tasks_path = sprint_dir / "tasks.md"
    if not tasks_path.exists() or force:
        tasks_path.write_text(f"# Tasks — sprint-{sprint_id}\n", encoding="utf-8")

    _update_sprint_backlog(repo, sprint_id, "in_progress")

    index.render(sprints_dir, title="Sprints", columns=index.SPRINT_COLUMNS,
                 scanner=index.sprint_paths)
    return plan_path


def end_sprint(
    *,
    sprint_id: str,
    author: str,
    repo_root: str | Path | None = None,
    retro_title: str | None = None,
    retro_body: str | None = None,
    force: bool = False,
    test_results: dict | None = None,
    linked_decisions: list[str] | None = None,
    linked_reviews: list[str] | None = None,
    owner_user: str = "user/local",
) -> Path:
    """Close out a sprint: write retro.md (if absent), archive folder, re-INDEX.

    Per D2 (non-destructive default): if ``retro.md`` already exists, the write
    is skipped and only the archive move + INDEX update happen. Pass
    ``force=True`` to overwrite. Returns the path to the archived ``retro.md``.
    """
    repo = Path(repo_root) if repo_root else Path.cwd()
    sprints_dir = ledger_paths.compat_sprints_dir(repo)
    active_dir = sprints_dir / "active" / f"sprint-{sprint_id}"
    archive_dir = sprints_dir / "archive" / f"sprint-{sprint_id}"
    retro_path_active = active_dir / "retro.md"

    if not active_dir.exists():
        raise FileNotFoundError(
            f"no active sprint folder at {active_dir}; nothing to end"
        )

    write_retro = (not retro_path_active.exists()) or force
    if write_retro:
        fm, tpl_body = templates.load("retrospective", repo_root=repo)
        effective_title = retro_title or f"sprint-{sprint_id} retrospective"
        fm.update({
            "id": f"sprint-{sprint_id}-retro",
            "type": "retrospective",
            "title": effective_title,
            "sprint_id": sprint_id,
            "status": "completed",
            "shipped_at": _utc_now_iso(),
            "created_at": _utc_now_iso(),
            "author": author,
            "linked_decisions": list(linked_decisions or []),
            "linked_reviews": list(linked_reviews or []),
            "test_results": dict(test_results) if test_results is not None else None,
            # Phase 4 (master §3.2 + D-WL-11): owner_user threaded through.
            "owner_user": owner_user,
        })
        validators.validate_retrospective(fm)
        body = (retro_body if retro_body is not None
                else tpl_body.replace("(title)", effective_title, 1))
        if not body.endswith("\n"):
            body += "\n"
        _fm.write(retro_path_active, fm, body)

    # workshop-lite cohort (A) substrate-hygiene (charter §2 D5):
    # flip plan.md frontmatter from `status: active` → `status: closed`
    # + write `closed_at: <ISO-now>` before the archive move. Closes
    # the wsl-plan checkpoint #2 §④ drift surface (18/18 archived
    # sprints stuck at `status: active` pre-cohort-A). Done BEFORE
    # the move so the file is at a known path; the move carries the
    # updated frontmatter into archive/ atomically. _SPRINT_PLAN_STATUSES
    # carries `closed` per the dual-update at validators.py:91 +
    # STATUS_TRANSITIONS["sprint-plan"]["active"] += {closed}; the
    # written value validates clean.
    plan_path_active = active_dir / "plan.md"
    if plan_path_active.exists():
        plan_fm, plan_body = _fm.parse(plan_path_active)
        plan_fm["status"] = "closed"
        plan_fm["closed_at"] = _utc_now_iso()
        _fm.write(plan_path_active, plan_fm, plan_body)

    if archive_dir.exists():
        raise FileExistsError(
            f"archive target already exists at {archive_dir}; cannot move"
        )
    archive_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(active_dir), str(archive_dir))

    _update_sprint_backlog(repo, sprint_id, "shipped")

    index.render(sprints_dir, title="Sprints", columns=index.SPRINT_COLUMNS,
                 scanner=index.sprint_paths)
    return archive_dir / "retro.md"


def _auto_handoff_body(
    *,
    title: str,
    sprint_id: str | None,
    stage: str | None,
    next_action: str | None,
    repo_root: Path,
) -> str:
    """Generate a minimal body for ``record_handoff`` when no body is supplied.

    Composes the four canonical sections (Current state / Since last handoff /
    What's next / Notes). Sibling INDEXes are silently skipped if absent
    (graceful per Q3 — same skip-if-missing pattern as ``_update_sprint_backlog``).
    """
    lines: list[str] = [f"# {title}", ""]

    lines += ["## Current state", ""]
    if sprint_id and stage:
        lines.append(f"Active sprint: `{sprint_id}` at stage `{stage}`.")
    elif sprint_id:
        lines.append(f"Active sprint: `{sprint_id}`.")
    else:
        lines.append("No active sprint at handoff time.")
    lines.append("")

    lines += ["## Since last handoff", ""]
    pointers: list[str] = []
    decisions_idx = ledger_paths.compat_kind_dir(repo_root, "decisions") / "INDEX.md"
    if decisions_idx.exists():
        pointers.append("- Recent decisions: see `docs/decisions/INDEX.md`")
    issues_idx = ledger_paths.compat_kind_dir(repo_root, "issues") / "INDEX.md"
    if issues_idx.exists():
        pointers.append("- Open issues: see `docs/issues/INDEX.md`")
    if sprint_id:
        tasks_path = (ledger_paths.compat_sprints_dir(repo_root) / "active"
                      / f"sprint-{sprint_id}" / "tasks.md")
        if tasks_path.exists():
            pointers.append(
                f"- Sprint tasks: see `docs/sprints/active/sprint-{sprint_id}/tasks.md`"
            )
    if pointers:
        lines.extend(pointers)
    else:
        lines.append(
            "(no sibling indices found; body to be filled by author or caller)"
        )
    lines.append("")

    lines += ["## What's next", ""]
    if next_action and next_action.strip():
        lines.append(next_action.strip())
    else:
        lines.append("TBD")
    lines.append("")

    lines += [
        "## Notes",
        "",
        "(auto-generated handoff body; replace with hand-authored content as needed)",
        "",
    ]
    return "\n".join(lines)


def record_handoff(
    *,
    title: str,
    topic: str,
    author: str,
    trigger: str = "manual",
    sprint_id: str | None = None,
    stage: str | None = None,
    since_handoff_id: str | None = None,
    since_msg_id: str | None = None,
    repo_root: str | Path | None = None,
    body: str | None = None,
    body_from_path: str | Path | None = None,
    linked_decisions: list[str] | None = None,
    linked_issues: list[str] | None = None,
    linked_tasks: list[str] | None = None,
    linked_msg_ids: list[str] | None = None,
    next_action: str | None = None,
    owner_user: str = "user/local",
) -> Path:
    """Record a Handoff entity (D6.A schema).

    Writes ``docs/handoffs/<YYYY-MM-DD-HHMM>-<slug>.md`` with validated
    frontmatter and re-renders ``docs/handoffs/INDEX.md``.

    Body resolution order (D7.A):
    1. ``body`` argument if non-None;
    2. content of ``body_from_path`` (frontmatter stripped) if provided;
    3. auto-generated minimal body via ``_auto_handoff_body``.

    ``sprint_id`` and ``stage`` are paired: both null OR both set (enforced by
    ``validators.validate_handoff``). ``trigger`` defaults to ``"manual"``;
    ``"pre_compact"`` is reserved for Sprint 6's hook caller; ``"session_end"``
    for explicit session-end invocations. ``since_msg_id`` is the caller's
    responsibility to populate (helper lib stays parley-agnostic per Q1).

    Returns the path of the written handoff file. Raises ``ValidationError``
    if frontmatter validation fails (no file written).
    """
    repo = Path(repo_root) if repo_root else Path.cwd()
    handoffs_dir = ledger_paths.compat_kind_dir(repo, "handoffs")

    date_str = _today_iso()
    hhmm = _utc_hhmm()
    slug = _slugify(topic)
    _prefix = f"{date_str}-{hhmm}-"
    handoff_id = _prefix + _cap_slug(slug, _prefix)  # S-B D2/R-B

    fm, _tpl_body = templates.load("handoff", repo_root=repo)
    fm.update({
        "id": handoff_id,
        "type": "handoff",
        "title": title,
        "topic": topic,
        "trigger": trigger,
        "sprint_id": sprint_id,
        "stage": stage,
        "status": "written",
        "created_at": _utc_now_iso(),
        "author": author,
        "since_handoff_id": since_handoff_id,
        "since_msg_id": since_msg_id,
        "linked_decisions": list(linked_decisions or []),
        "linked_issues": list(linked_issues or []),
        "linked_tasks": list(linked_tasks or []),
        "linked_msg_ids": list(linked_msg_ids or []),
        "next_action": next_action,
        # Phase 4 (master §3.2 + D-WL-11): owner_user threaded through.
        "owner_user": owner_user,
    })

    validators.validate_handoff(fm)

    if body is not None:
        resolved_body = body
    elif body_from_path is not None:
        body_text = Path(body_from_path).read_text(encoding="utf-8")
        resolved_body = _strip_frontmatter(body_text)
    else:
        resolved_body = _auto_handoff_body(
            title=title,
            sprint_id=sprint_id,
            stage=stage,
            next_action=next_action,
            repo_root=repo,
        )

    if not resolved_body.endswith("\n"):
        resolved_body += "\n"

    target = handoffs_dir / f"{handoff_id}.md"
    _fm.write(target, fm, resolved_body)
    # Phase 1 Cycle 2 (wl-rearch §4.6): route through the rolling-collapse
    # aware renderer. When `[handoffs].rolling_collapse` is OFF in
    # `.claude/workshop-lite-config.toml` (the default), this delegates
    # to the existing `index.render(..., HANDOFF_COLUMNS)` flat-table
    # path — zero behavior change. When ON, the bespoke list shape
    # with stub-collapse renders.
    index.render_handoffs_index_with_rolling_collapse(repo_root=repo)
    cross_links.rebuild_link_index(repo)
    return target


def _format_findings_block(findings: list[dict]) -> str:
    """Render a Review's structured findings list as a markdown bullet block.

    Same shape role as ``_format_options_block`` for decisions: frontmatter is
    the structured SoT; the body's Findings section is derived. Each finding
    renders as ``- **{severity}**: {summary}`` with any extra dict keys
    (``status``, ``resolution``, ``location``, ...) as indented sub-bullets.
    Empty list renders as ``(no findings)``.
    """
    if not findings:
        return "(no findings)"
    lines: list[str] = []
    for finding in findings:
        severity = finding.get("severity", "?")
        summary = finding.get("summary", "?")
        lines.append(f"- **{severity}**: {summary}")
        for key, value in finding.items():
            if key in ("severity", "summary"):
                continue
            lines.append(f"  - {key}: {value}")
    return "\n".join(lines)


def record_issue(
    *,
    title: str,
    severity: str,
    scope: str,
    reporter: str,
    status: str = "open",
    sprint_id: str | None = None,
    stage: str | None = None,
    klass: str | None = None,
    repo_root: str | Path | None = None,
    body: str | None = None,
    body_from_path: str | Path | None = None,
    linked_decisions: list[str] | None = None,
    linked_reviews: list[str] | None = None,
    linked_msg_ids: list[str] | None = None,
    owner_user: str = "user/local",
) -> Path:
    """Record an Issue entity (Sprint 4 / D12+D13 schema).

    Writes ``docs/issues/<YYYY-MM-DD-NN>-<slug>.md`` with validated frontmatter
    and re-renders ``docs/issues/INDEX.md``.

    D12: ``klass`` (mapped to frontmatter ``class``) is an optional free-form
    string — per-repo can use it for their own taxonomy. ``linked_decisions``
    instead of §6's ``related_decisions`` for linked_* family consistency.

    D13: ``scope`` is one of ``sprint:<id>``, ``repo:<area>``, ``design:<doc-name>``.
    ``sprint_id``+``stage`` are paired (both set or both null).

    Body resolution (Q3a — template-verbatim default, different from /handoff
    auto-body):
    1. ``body`` argument if non-None;
    2. content of ``body_from_path`` (frontmatter stripped) if provided;
    3. template body verbatim from ``docs/.templates/issue.md`` (or the inline
       ``templates._DEFAULTS`` fallback).
    """
    repo = Path(repo_root) if repo_root else Path.cwd()
    issues_dir = ledger_paths.compat_kind_dir(repo, "issues")

    date_str = _today_iso()
    counter = _next_counter(issues_dir, date_str)
    slug = _slugify(title)
    _prefix = f"{date_str}-{counter:02d}-"
    issue_id = _prefix + _cap_slug(slug, _prefix)  # S-B D2/R-B

    fm, tpl_body = templates.load("issue", repo_root=repo)
    fm.update({
        "id": issue_id,
        "type": "issue",
        "title": title,
        "status": status,
        "severity": severity,
        "scope": scope,
        "sprint_id": sprint_id,
        "stage": stage,
        "class": klass,
        "created_at": _utc_now_iso(),
        "reporter": reporter,
        "linked_decisions": list(linked_decisions or []),
        "linked_reviews": list(linked_reviews or []),
        "linked_msg_ids": list(linked_msg_ids or []),
        # Phase 4 (master §3.2 + D-WL-11): owner_user threaded through.
        "owner_user": owner_user,
    })

    validators.validate_issue(fm)

    if body is not None:
        resolved_body = body
    elif body_from_path is not None:
        body_text = Path(body_from_path).read_text(encoding="utf-8")
        resolved_body = _strip_frontmatter(body_text)
    else:
        resolved_body = tpl_body

    if not resolved_body.endswith("\n"):
        resolved_body += "\n"

    target = issues_dir / f"{issue_id}.md"
    _fm.write(target, fm, resolved_body)
    index.render(issues_dir, title="Issues", columns=index.ISSUE_COLUMNS)
    cross_links.rebuild_link_index(repo)
    return target


def record_review(
    *,
    title: str,
    review_type: str,
    scope: str,
    author: str,
    status: str = "completed",
    sprint_id: str | None = None,
    stage: str | None = None,
    repo_root: str | Path | None = None,
    body: str | None = None,
    body_from_path: str | Path | None = None,
    findings: list[dict] | None = None,
    accurate_trail: dict | list | str | None = None,
    linked_decisions: list[str] | None = None,
    linked_reviews: list[str] | None = None,
    linked_msg_ids: list[str] | None = None,
    owner_user: str = "user/local",
) -> Path:
    """Record a Review entity (Sprint 4 / D14+D16 schema).

    Writes ``docs/reviews/<YYYY-MM-DD-NN>-<slug>.md`` with validated frontmatter
    and re-renders ``docs/reviews/INDEX.md``.

    D14: §6 verbatim + ``linked_decisions: []`` for linked_* family consistency.
    D16: ``findings`` is required-but-may-be-empty; each finding-dict requires
    ``severity`` (high|medium|low) and ``summary`` (non-empty); extra keys
    permitted.

    Body resolution (Q3a + Q2a):
    1. ``body`` argument if non-None — used verbatim (user owns drift);
    2. content of ``body_from_path`` (frontmatter stripped) if provided —
       used verbatim;
    3. template body from ``docs/.templates/review.md`` (or inline default)
       with the ``{findings_block}`` placeholder substituted with the
       auto-rendered findings list (Q2a: frontmatter is SoT, body Findings
       section is derived — same shape as /record-decision options).
    """
    repo = Path(repo_root) if repo_root else Path.cwd()
    reviews_dir = ledger_paths.compat_kind_dir(repo, "reviews")

    date_str = _today_iso()
    counter = _next_counter(reviews_dir, date_str)
    slug = _slugify(title)
    _prefix = f"{date_str}-{counter:02d}-"
    review_id = _prefix + _cap_slug(slug, _prefix)  # S-B D2/R-B

    findings_list = list(findings or [])

    fm, tpl_body = templates.load("review", repo_root=repo)
    fm.update({
        "id": review_id,
        "type": "review",
        "review_type": review_type,
        "title": title,
        "status": status,
        "scope": scope,
        "sprint_id": sprint_id,
        "stage": stage,
        "findings": findings_list,
        "created_at": _utc_now_iso(),
        "author": author,
        "linked_decisions": list(linked_decisions or []),
        "linked_reviews": list(linked_reviews or []),
        "linked_msg_ids": list(linked_msg_ids or []),
        # Phase 4 (master §3.2 + D-WL-11): owner_user threaded through.
        "owner_user": owner_user,
    })

    # Sprint S-B D1=A — thread the structured 4.6f accurate-trail ONLY
    # when supplied. cross-check-resolution REQUIRES it (validator-hard,
    # R-A); every other review_type passes accurate_trail=None ⇒ the
    # key is absent ⇒ that review's frontmatter is byte-identical to
    # pre-S-B (D5 zero-regression; grandfathering by-construction — the
    # validator branch only fires for review_type=cross-check-resolution).
    if accurate_trail is not None:
        fm["accurate_trail"] = accurate_trail

    validators.validate_review(fm)

    if body is not None:
        resolved_body = body
    elif body_from_path is not None:
        body_text = Path(body_from_path).read_text(encoding="utf-8")
        resolved_body = _strip_frontmatter(body_text)
    else:
        findings_block = _format_findings_block(findings_list)
        resolved_body = tpl_body.replace("{findings_block}", findings_block)

    if not resolved_body.endswith("\n"):
        resolved_body += "\n"

    target = reviews_dir / f"{review_id}.md"
    _fm.write(target, fm, resolved_body)
    # par:2026-06-04-13 cohort D D2 — CURATED (C) HYBRID render with
    # auto-rotation. No canonical-pair convention for reviews;
    # preserve_manual_rows keeps any operator-annotated headerless rows.
    index.render_curated(
        reviews_dir,
        title="Reviews",
        columns=index.REVIEW_COLUMNS,
        preserve_manual_rows=True,
    )
    cross_links.rebuild_link_index(repo)
    return target


# ---------------------------------------------------------------------------
# Sprint 5: add_task (D19-D21) + capture_conversation (D22-D27)
# ---------------------------------------------------------------------------


def _scan_tasks(tasks_md_path: Path, sprint_id: str) -> list[dict]:
    """Parse all valid task lines from ``tasks_md_path`` for ``sprint_id``.

    Skips non-task lines (headings, blanks, prose) and lines that fail
    ``validate_task_line``. Returns the list of parsed task dicts in
    file-order.
    """
    if not tasks_md_path.exists():
        return []
    parsed: list[dict] = []
    for raw in tasks_md_path.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        if not line.lstrip().startswith("- ["):
            continue
        try:
            task_dict, _warnings = validators.validate_task_line(
                line, sprint_id=sprint_id
            )
        except validators.ValidationError:
            continue
        parsed.append(task_dict)
    return parsed


def _next_task_nn(parsed_tasks: list[dict], sprint_id: str) -> int:
    """Max-per-sprint task counter + 1 (min 1)."""
    prefix = f"task-{sprint_id}."
    max_n = 0
    for t in parsed_tasks:
        tid = t.get("id") or ""
        if not tid.startswith(prefix):
            continue
        nn = tid[len(prefix):]
        if nn.isdigit():
            max_n = max(max_n, int(nn))
    return max_n + 1


_TASK_IDENTITY_RESERVED = frozenset(
    {"id", "type", "sprint_id", "description", "status", "block_overlay",
     "assignee", "linked_issues", "linked_decisions"}
)


def _task_identity_tuple(task: dict) -> tuple:
    """Hashable identity tuple for Q5 idempotency (everything except the id).

    Two task dicts that produce the same identity tuple are considered the
    "same task" for idempotency purposes. Different metadata → different
    tuple → pure-append (Q5b).
    """
    extras = sorted(
        (k, repr(v)) for k, v in task.items()
        if k not in _TASK_IDENTITY_RESERVED
    )
    return (
        task.get("description"),
        task.get("status"),
        task.get("assignee"),
        tuple(task.get("linked_issues") or []),
        tuple(task.get("linked_decisions") or []),
        tuple(extras),
    )


def _normalize_task_status(status: str) -> str:
    """Map a legacy v1 4-state status to its R6 equivalent (BC1.5).

    Pass-through for an already-R6 status. ``blocked`` best-effort maps to
    ``in-progress`` (it is no longer a task status — it becomes a block-signal).
    """
    return validators._TASK_V1_TO_R6.get(status, status)


def _render_task_line(
    *,
    task_id: str,
    status: str,
    description: str,
    assignee: str | None,
    linked_issues: list[str],
    linked_decisions: list[str],
    extra_meta: dict | None = None,
    block_overlay: bool = False,
) -> str:
    """Render a single task line per D20.A in R6 canonical form (BC1.5).

    The checkbox is derived from the R6 status bucket
    (`[ ]`=created/picked-up · `[~]`=in-progress/verified · `[x]`=done/cleaned-up).
    `(status: ...)` is OMITTED for the bucket-default status (created /
    in-progress / done) and INCLUDED for the non-default
    (picked-up / verified / cleaned-up) — the explicit field being authoritative.
    When ``block_overlay`` is set, the checkbox is `[!]` (a block-signal overlay,
    §9) and the underlying R6 status is ALWAYS stamped explicitly.
    """
    status = _normalize_task_status(status)
    parts: list[str] = []
    if block_overlay:
        checkbox = "!"
        parts.append(f"status: {status}")
    else:
        checkbox = validators._R6_TO_CHECKBOX[status]
        bucket = validators._CHECKBOX_BUCKET[checkbox]
        if status != bucket[0]:
            parts.append(f"status: {status}")
    if assignee:
        parts.append(f"assignee: {assignee}")
    if linked_issues:
        parts.append(f"linked_issues: [{', '.join(linked_issues)}]")
    if linked_decisions:
        parts.append(f"linked_decisions: [{', '.join(linked_decisions)}]")
    for k, v in (extra_meta or {}).items():
        if isinstance(v, list):
            parts.append(f"{k}: [{', '.join(str(x) for x in v)}]")
        else:
            parts.append(f"{k}: {v}")
    meta_block = f" ({'; '.join(parts)})" if parts else ""
    return f"- [{checkbox}] **{task_id}** — {description}{meta_block}"


def add_task(
    *,
    sprint_id: str,
    description: str,
    assignee: str | None = None,
    status: str = "created",
    linked_issues: list[str] | None = None,
    linked_decisions: list[str] | None = None,
    repo_root: str | Path | None = None,
    extra_meta: dict | None = None,
) -> tuple[Path, str]:
    """Append a task line to a sprint's ``tasks.md`` per D19-D21.

    Returns ``(tasks_md_path, task_id)``. Auto-generates the per-sprint
    ``task-<sprint_id>.<NN>`` id (D19) and constructs the line per D20.A.

    Idempotency (Q5): if an existing line has the same identity tuple
    (description + status + assignee + linked_* + extra_meta), returns that
    line's task_id without appending. Different metadata → new task (Q5b
    pure-append semantics).

    Sprint must exist as ``docs/sprints/active/sprint-<sprint_id>/`` or the
    archive equivalent; raises ``FileNotFoundError`` otherwise. ``tasks.md``
    is initialized with the standard heading if absent.
    """
    repo = Path(repo_root) if repo_root else Path.cwd()
    sprints_dir = ledger_paths.compat_sprints_dir(repo)
    active_dir = sprints_dir / "active" / f"sprint-{sprint_id}"
    archive_dir = sprints_dir / "archive" / f"sprint-{sprint_id}"
    if active_dir.exists():
        sprint_dir = active_dir
    elif archive_dir.exists():
        sprint_dir = archive_dir
    else:
        raise FileNotFoundError(
            f"no sprint folder at {active_dir} or {archive_dir}"
        )

    tasks_md_path = sprint_dir / "tasks.md"
    if not tasks_md_path.exists():
        tasks_md_path.write_text(
            f"# Tasks — sprint-{sprint_id}\n", encoding="utf-8"
        )

    existing = _scan_tasks(tasks_md_path, sprint_id)

    # Normalize legacy v1 status to R6 so idempotency compares apples to apples
    # (the parser returns R6 for existing lines).
    status = _normalize_task_status(status)

    candidate = {
        "description": description,
        "status": status,
        "assignee": assignee,
        "linked_issues": list(linked_issues or []),
        "linked_decisions": list(linked_decisions or []),
    }
    if extra_meta:
        candidate.update(extra_meta)
    candidate_identity = _task_identity_tuple(candidate)
    for t in existing:
        if _task_identity_tuple(t) == candidate_identity:
            existing_id = t.get("id")
            if isinstance(existing_id, str):
                return tasks_md_path, existing_id

    nn = _next_task_nn(existing, sprint_id)
    task_id = f"task-{sprint_id}.{nn}"

    new_line = _render_task_line(
        task_id=task_id,
        status=status,
        description=description,
        assignee=assignee,
        linked_issues=list(linked_issues or []),
        linked_decisions=list(linked_decisions or []),
        extra_meta=extra_meta,
    )

    # Validate the rendered line before persisting (raises ValidationError)
    validators.validate_task_line(new_line, sprint_id=sprint_id)

    text = tasks_md_path.read_text(encoding="utf-8")
    if text and not text.endswith("\n"):
        text += "\n"
    text += new_line + "\n"
    tasks_md_path.write_text(text, encoding="utf-8")

    return tasks_md_path, task_id


def _reconstruct_task_line(parsed: dict) -> str:
    """Re-render a parsed task dict into canonical R6 form (BC1.5 migration).

    Reserved keys are consumed positionally; everything else is preserved as
    free-form ``extra_meta`` so a migration is loss-free on custom keys.
    """
    extra = {
        k: v for k, v in parsed.items()
        if k not in _TASK_IDENTITY_RESERVED
    }
    return _render_task_line(
        task_id=parsed["id"],
        status=parsed["status"],
        description=parsed["description"],
        assignee=parsed.get("assignee"),
        linked_issues=list(parsed.get("linked_issues") or []),
        linked_decisions=list(parsed.get("linked_decisions") or []),
        extra_meta=extra or None,
        block_overlay=bool(parsed.get("block_overlay")),
    )


def migrate_tasks_md(tasks_md_path: str | Path, sprint_id: str | None = None) -> int:
    """Migrate a single ``tasks.md`` file's task lines to canonical R6 (BC1.5).

    Every parseable task line is re-rendered from its parsed (R6-mapped) fields;
    a line is rewritten only if its canonical form differs from the original
    (so the pass is idempotent and touches only legacy/non-canonical lines).
    Non-task lines (headings, prose) are preserved verbatim. Returns the number
    of lines migrated. Per spec §C.6 (additive-forward), existing files parse
    before and after; this makes the on-disk form canonical R6.
    """
    path = Path(tasks_md_path)
    if not path.exists():
        return 0
    lines = path.read_text(encoding="utf-8").splitlines()
    migrated = 0
    out: list[str] = []
    for raw in lines:
        line = raw.rstrip()
        if not line.lstrip().startswith("- ["):
            out.append(raw)
            continue
        try:
            parsed, _warnings = validators.validate_task_line(line, sprint_id=sprint_id)
        except validators.ValidationError:
            out.append(raw)  # not a valid task line — leave untouched
            continue
        canonical = _reconstruct_task_line(parsed)
        if canonical != line:
            migrated += 1
            out.append(canonical)
        else:
            out.append(raw)
    if migrated:
        text = "\n".join(out)
        if not text.endswith("\n"):
            text += "\n"
        path.write_text(text, encoding="utf-8")
    return migrated


def migrate_all_tasks(repo_root: str | Path | None = None) -> dict[str, int]:
    """Migrate every sprint's ``tasks.md`` under the repo to canonical R6.

    Returns ``{tasks_md_path: migrated_count}`` for files that changed. Walks
    both ``active/`` and ``archive/`` sprint folders.
    """
    repo = Path(repo_root) if repo_root else Path.cwd()
    sprints_dir = ledger_paths.compat_sprints_dir(repo)
    results: dict[str, int] = {}
    if not sprints_dir.exists():
        return results
    for sub in ("active", "archive"):
        sub_dir = sprints_dir / sub
        if not sub_dir.exists():
            continue
        for sprint_dir in sorted(sub_dir.iterdir()):
            if not sprint_dir.is_dir():
                continue
            tasks_md = sprint_dir / "tasks.md"
            if not tasks_md.exists():
                continue
            sid = sprint_dir.name[len("sprint-"):] if sprint_dir.name.startswith("sprint-") else None
            count = migrate_tasks_md(tasks_md, sprint_id=sid)
            if count:
                results[str(tasks_md)] = count
    return results


# Renderer presentation literal ONLY — the human-readable marker
# _render_parley_verbatim emits for an empty record list. This is NOT a
# guard contract: per MOD-W-F1 (b) (@plan msg-1a89d7dbb688) no other
# module keys off this value. The silent-empty-capture footgun
# (2026-05-15-05) is closed STRUCTURALLY — cli.py guard-1 rejects an
# empty records-json set by record-count before this function is even
# called, and guard-2 rejects a structurally-empty resolved body — so
# this string can be reworded freely for presentation with zero
# functional/guard impact (that decoupling is the W-arc-W-F1 (b) fix;
# the prior shared-constant-as-guard-contract (a) approach a868e7d was
# superseded). Keep it module-local to entities.py.
EMPTY_VERBATIM_MARKER = "(no records in this range)"


def _render_parley_verbatim(
    records: list[dict],
) -> tuple[str, list[str | None], str | None, str | None]:
    """Render parley JSON-lines records as sender-attributed markdown per D23.

    Each record produces a ``### @<from> · <msg-id> · <iso_ts>`` sub-section
    followed by the ``raw`` body text. Empty records list returns the explicit
    "(no records in this range)" marker.

    Returns ``(markdown, [first_id, last_id], started_at_iso, ended_at_iso)``.
    The msg-id pair and iso timestamps are derived from the captured records
    (Q3 — captured range, not caller args). All four return values use ``None``
    placeholders for the empty-range case.

    Parley-agnostic: this function processes plain dicts (whatever parley get
    --json emits, the SKILL layer hands the parsed list here). The lib never
    shells out to parley (D27).
    """
    if not records:
        return f"{EMPTY_VERBATIM_MARKER}\n", [None, None], None, None

    def _iso(ts: object) -> str | None:
        if isinstance(ts, (int, float)):
            return datetime.fromtimestamp(ts, tz=timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
        return None

    first_id = records[0].get("id")
    last_id = records[-1].get("id")
    started_at = _iso(records[0].get("ts"))
    ended_at = _iso(records[-1].get("ts"))

    parts: list[str] = []
    for r in records:
        from_id = (r.get("from") or "?").strip()
        if not from_id.startswith("@"):
            from_id = f"@{from_id}"
        msg_id = r.get("id") or "msg-?"
        ts = r.get("ts")
        if isinstance(ts, (int, float)):
            ts_display = datetime.fromtimestamp(ts, tz=timezone.utc).strftime(
                "%Y-%m-%d %H:%MZ"
            )
        else:
            ts_display = str(ts) if ts else "?"
        body = r.get("raw") or r.get("body") or ""
        parts.append(f"### {from_id} · {msg_id} · {ts_display}")
        parts.append("")
        parts.append(body.rstrip())
        parts.append("")

    rendered = "\n".join(parts).rstrip() + "\n"
    return rendered, [first_id, last_id], started_at, ended_at


def capture_conversation(
    *,
    title: str,
    topic: str,
    verbatim_text: str,
    verbatim_msg_range: list[str | None],
    participants: list[str],
    zone: str = "cross-sprint",
    sprint_id: str | None = None,
    stage: str | None = None,
    started_at: str | None = None,
    ended_at: str | None = None,
    repo_root: str | Path | None = None,
    body: str | None = None,
    body_from_path: str | Path | None = None,
    linked_design_docs: list[str] | None = None,
    linked_decisions: list[str] | None = None,
    linked_reviews: list[str] | None = None,
    linked_issues: list[str] | None = None,
    linked_handoffs: list[str] | None = None,
    linked_msg_ids: list[str] | None = None,
) -> Path:
    """Record a Conversation entity (Sprint 5 / §6 + D22-D27 schema).

    The verbatim chat section is passed pre-rendered as ``verbatim_text``; the
    SKILL layer is responsible for the parley shell-out + rendering (D27 keeps
    the lib parley-agnostic). ``verbatim_msg_range`` is ``[first_msg_id,
    last_msg_id]`` of the actually-captured records (Q3 — captured range, not
    caller args); both ``None`` for an explicit-empty range.

    D25: ``zone`` defaults to ``cross-sprint``. When ``zone='sprint'``,
    ``sprint_id`` and ``stage`` are required (validator enforces).

    Body resolution for the Curated summary section (D23):
    1. ``body`` argument if non-None;
    2. content of ``body_from_path`` (frontmatter stripped) if provided;
    3. placeholder ``"_curated summary pending_"``.

    Writes ``docs/conversations/<YYYY-MM-DD-NN>-<slug>.md`` (D15) with
    validated frontmatter and re-renders ``docs/conversations/INDEX.md``.
    """
    repo = Path(repo_root) if repo_root else Path.cwd()
    conversations_dir = ledger_paths.compat_kind_dir(repo, "conversations")

    date_str = _today_iso()
    counter = _next_counter(conversations_dir, date_str)
    slug = _slugify(topic)
    _prefix = f"{date_str}-{counter:02d}-"
    conv_id = _prefix + _cap_slug(slug, _prefix)  # S-B D2/R-B

    fm, tpl_body = templates.load("conversation", repo_root=repo)
    fm.update({
        "id": conv_id,
        "type": "conversation",
        "title": title,
        "topic": topic,
        "zone": zone,
        "sprint_id": sprint_id,
        "stage": stage,
        "participants": list(participants),
        "verbatim_msg_range": list(verbatim_msg_range),
        "started_at": started_at,
        "ended_at": ended_at,
        "created_at": _utc_now_iso(),
        "linked_design_docs": list(linked_design_docs or []),
        "linked_decisions": list(linked_decisions or []),
        "linked_reviews": list(linked_reviews or []),
        "linked_issues": list(linked_issues or []),
        "linked_handoffs": list(linked_handoffs or []),
        "linked_msg_ids": list(linked_msg_ids or []),
    })

    validators.validate_conversation(fm)

    if body is not None:
        curated = body
    elif body_from_path is not None:
        body_text = Path(body_from_path).read_text(encoding="utf-8")
        curated = _strip_frontmatter(body_text)
    else:
        curated = "_curated summary pending_"

    resolved_body = tpl_body.replace("(title)", title, 1)
    resolved_body = resolved_body.replace("{curated_summary}", curated.rstrip())
    resolved_body = resolved_body.replace(
        "{verbatim_chat}", verbatim_text.rstrip()
    )

    if not resolved_body.endswith("\n"):
        resolved_body += "\n"

    target = conversations_dir / f"{conv_id}.md"
    _fm.write(target, fm, resolved_body)
    index.render(
        conversations_dir,
        title="Conversations",
        columns=index.CONVERSATION_COLUMNS,
    )
    cross_links.rebuild_link_index(repo)
    return target


# ---------------------------------------------------------------------------
# BC1.2 — writers for the 5 new kinds (spec §2.3):
#   workflow · role-set (library entries) · block-signal (runtime block) ·
#   resume-ledger · canonical-pointer (continuity).
# owner_user carries on the 4 authored kinds (BC1.3 writer-side stamping);
# block-signal does NOT carry it (transient signal, created_by only).
# ---------------------------------------------------------------------------


def record_workflow(
    *,
    title: str,
    stages: list[dict],
    author: str,
    status: str = "active",
    library_layer: str = "user",
    is_default: bool = False,
    supersedes: str | None = None,
    linked_decisions: list[str] | None = None,
    repo_root: str | Path | None = None,
    owner_user: str = "user/local",
    body: str | None = None,
) -> Path:
    """Record a workflow library entry (spec §2.3; DOC1 §6.4).

    A workflow is data: a declared ordered set of ``stages`` (each a dict with
    a ``name`` + optional ``produces_artifact_kind`` / ``parallelizable``).
    The id is the title slug; the on-disk file is ``workflows/<slug>.md``.
    """
    repo = Path(repo_root) if repo_root else Path.cwd()
    workflows_dir = ledger_paths.compat_kind_dir(repo, "workflows")

    slug = _slugify(title)
    workflow_id = _cap_slug(slug, "")

    fm = {
        "id": workflow_id,
        "type": "workflow",
        "title": title,
        "status": status,
        "stages": list(stages),
        "library_layer": library_layer,
        "is_default": is_default,
        "created_at": _utc_now_iso(),
        "author": author,
        "owner_user": owner_user,
        "supersedes": supersedes,
        "linked_decisions": list(linked_decisions or []),
    }
    validators.validate_workflow(fm)

    resolved_body = body if body is not None else _workflow_body(title, stages)
    if not resolved_body.endswith("\n"):
        resolved_body += "\n"

    target = workflows_dir / f"{workflow_id}.md"
    _fm.write(target, fm, resolved_body)
    index.render(workflows_dir, title="Workflows", columns=index.WORKFLOW_COLUMNS)
    cross_links.rebuild_link_index(repo)
    return target


def _workflow_body(title: str, stages: list[dict]) -> str:
    lines = [f"# {title}", "", "## Stages", ""]
    if not stages:
        lines.append("(no stages declared)")
    else:
        for idx, stage in enumerate(stages, start=1):
            name = stage.get("name", "?")
            produces = stage.get("produces_artifact_kind")
            par = " (parallelizable)" if stage.get("parallelizable") else ""
            suffix = f" → {produces}" if produces else ""
            lines.append(f"{idx}. **{name}**{suffix}{par}")
    lines.append("")
    return "\n".join(lines)


def record_role_set(
    *,
    title: str,
    roles: list[dict],
    author: str,
    sod_predicates: list | None = None,
    per_stage_markers: dict | None = None,
    status: str = "active",
    library_layer: str = "user",
    is_default: bool = False,
    supersedes: str | None = None,
    repo_root: str | Path | None = None,
    owner_user: str = "user/local",
    body: str | None = None,
) -> Path:
    """Record a role-set library entry (spec §2.3; DOC1 §6.4).

    Names roles + SoD rules; companion to a workflow. ``roles`` is a non-empty
    list of {name, owns_stage, identity_predicate?}. id = title slug; on-disk
    file ``role-sets/<slug>.md``.
    """
    repo = Path(repo_root) if repo_root else Path.cwd()
    role_sets_dir = ledger_paths.compat_kind_dir(repo, "role-sets")

    slug = _slugify(title)
    role_set_id = _cap_slug(slug, "")

    fm = {
        "id": role_set_id,
        "type": "role-set",
        "title": title,
        "status": status,
        "roles": list(roles),
        "sod_predicates": list(sod_predicates or []),
        "per_stage_markers": dict(per_stage_markers or {}),
        "library_layer": library_layer,
        "is_default": is_default,
        "created_at": _utc_now_iso(),
        "author": author,
        "owner_user": owner_user,
        "supersedes": supersedes,
    }
    validators.validate_role_set(fm)

    resolved_body = body if body is not None else _role_set_body(title, roles)
    if not resolved_body.endswith("\n"):
        resolved_body += "\n"

    target = role_sets_dir / f"{role_set_id}.md"
    _fm.write(target, fm, resolved_body)
    index.render(role_sets_dir, title="Role-sets", columns=index.ROLE_SET_COLUMNS)
    cross_links.rebuild_link_index(repo)
    return target


def _role_set_body(title: str, roles: list[dict]) -> str:
    lines = [f"# {title}", "", "## Roles", ""]
    if not roles:
        lines.append("(no roles declared)")
    else:
        for role in roles:
            name = role.get("name", "?")
            owns = role.get("owns_stage", "?")
            lines.append(f"- **{name}** — owns stage `{owns}`")
    lines.append("")
    return "\n".join(lines)


def raise_block_signal(
    *,
    blocked_subject: str,
    waits_on: str,
    klass: str,
    created_by: str,
    status: str = "raised",
    deadline: str | None = None,
    ttl: str | None = None,
    inferred_by: str | None = None,
    repo_root: str | Path | None = None,
    body: str | None = None,
) -> Path:
    """Raise a block-signal (spec §2.3; DOC1 §6.3; the runtime block).

    Two classes (§11.5): ``HALT`` (human-cleared, may wait indefinitely) and
    ``wait_for`` (bounded — a ``ttl`` is REQUIRED). id = ``<date>-NN-<slug>``
    per §1.2 (slug from blocked_subject); on-disk file ``block-signals/<id>.md``.
    Does NOT carry owner_user (created_by only).
    """
    repo = Path(repo_root) if repo_root else Path.cwd()
    bs_dir = ledger_paths.compat_kind_dir(repo, "block-signals")

    date_str = _today_iso()
    counter = _next_counter(bs_dir, date_str)
    slug = _slugify(blocked_subject)
    _prefix = f"{date_str}-{counter:02d}-"
    signal_id = _prefix + _cap_slug(slug, _prefix)

    fm = {
        "id": signal_id,
        "type": "block-signal",
        "blocked_subject": blocked_subject,
        "waits_on": waits_on,
        "class": klass,
        "status": status,
        "created_at": _utc_now_iso(),
        "created_by": created_by,
    }
    if deadline is not None:
        fm["deadline"] = deadline
    if ttl is not None:
        fm["ttl"] = ttl
    if inferred_by is not None:
        fm["inferred_by"] = inferred_by

    validators.validate_block_signal(fm)

    resolved_body = body if body is not None else (
        f"# Block signal {signal_id}\n\n"
        f"**{klass}** — `{blocked_subject}` waits on `{waits_on}`.\n"
    )
    if not resolved_body.endswith("\n"):
        resolved_body += "\n"

    target = bs_dir / f"{signal_id}.md"
    _fm.write(target, fm, resolved_body)
    index.render(bs_dir, title="Block-signals", columns=index.BLOCK_SIGNAL_COLUMNS)
    cross_links.rebuild_link_index(repo)
    return target


def write_denial(
    *,
    denied_subject: str,
    denial_class: str,
    from_state: str,
    reason_ref: str,
    handler: str | None = None,
    resolution: str = "open",
    repo_root: str | Path | None = None,
    body: str | None = None,
) -> Path:
    """Write a denial/degrade envelope (spec §9, CP7; THE canonical envelope).

    Builds the envelope through ``denial.build_denial`` (raised_by/handler
    derived per §9.2; born ``resolution=open``, forward-only) so every
    denial/degrade point — work-readiness guard-miss (§11.2), the acceptance
    conjunction gate-refused (§11.4), coverage-gap, store-unavailable, degrade —
    produces an instance of the SAME shape, never a redefinition (BC2.4 reuse
    hard part). Forward-only, stored ``denials/<id>.md``, linked to
    ``denied_subject`` (§9.3). id = ``<date>-NN-<slug>`` (slug from
    denied_subject), §1.2.
    """
    repo = Path(repo_root) if repo_root else Path.cwd()
    den_dir = ledger_paths.compat_kind_dir(repo, "denials")

    date_str = _today_iso()
    counter = _next_counter(den_dir, date_str)
    _prefix = f"{date_str}-{counter:02d}-"
    denial_id = _prefix + _cap_slug(_slugify(denied_subject), _prefix)

    fm = _denial.build_denial(
        id=denial_id,
        denied_subject=denied_subject,
        denial_class=denial_class,
        from_state=from_state,
        reason_ref=reason_ref,
        created_at=_utc_now_iso(),
        handler=handler,
        resolution=resolution,
    )
    _denial.validate_denial(fm)

    resolved_body = body if body is not None else (
        f"# Denial {denial_id}\n\n"
        f"**{denial_class}** — `{denied_subject}` denied, stays `{from_state}`.\n\n"
        f"- raised_by: `{fm['raised_by']}`\n"
        f"- handler: `{fm['handler']}`\n"
        f"- reason: {reason_ref}\n"
    )
    if not resolved_body.endswith("\n"):
        resolved_body += "\n"

    target = den_dir / f"{denial_id}.md"
    _fm.write(target, fm, resolved_body)
    index.render(den_dir, title="Denials", columns=index.DENIAL_COLUMNS)
    cross_links.rebuild_link_index(repo)
    return target


def write_closure_record(
    *,
    task_ref: str,
    disposition: str,
    closure_signal_ref: str,
    closed_by: str,
    supersedes_ref: str | None = None,
    repo_root: str | Path | None = None,
    body: str | None = None,
) -> Path:
    """Write a closure record (spec §11.3; BC2.3).

    The lifecycle sub-record written on the two terminal edges (§11.1):
    ``disposition ∈ {completed, superseded}`` on ``done → cleaned-up``;
    ``disposition = abandoned`` on the pre-done abandon edge. ``supersedes_ref``
    is set iff ``disposition == superseded``. Stored ``closures/<id>.md``,
    id = ``<date>-NN-<slug>`` (slug from task_ref), §1.2. NOT a built-in kind —
    the catalog stays at 20.
    """
    repo = Path(repo_root) if repo_root else Path.cwd()
    cl_dir = ledger_paths.compat_kind_dir(repo, "closures")

    date_str = _today_iso()
    counter = _next_counter(cl_dir, date_str)
    _prefix = f"{date_str}-{counter:02d}-"
    closure_id = _prefix + _cap_slug(_slugify(task_ref), _prefix)

    fm = {
        "id": closure_id,
        "type": "closure-record",
        "task_ref": task_ref,
        "disposition": disposition,
        "closure_signal_ref": closure_signal_ref,
        "closed_by": closed_by,
        "closed_at": _utc_now_iso(),
    }
    if supersedes_ref is not None:
        fm["supersedes_ref"] = supersedes_ref

    validators.validate_closure_record(fm)

    resolved_body = body if body is not None else (
        f"# Closure {closure_id}\n\n"
        f"**{disposition}** — `{task_ref}` closed by `{closed_by}`.\n"
    )
    if not resolved_body.endswith("\n"):
        resolved_body += "\n"

    target = cl_dir / f"{closure_id}.md"
    _fm.write(target, fm, resolved_body)
    index.render(cl_dir, title="Closures", columns=index.CLOSURE_COLUMNS)
    cross_links.rebuild_link_index(repo)
    return target


def write_resume_ledger(
    *,
    worker: str,
    in_flight_state: str,
    next_actions: list[str],
    author: str,
    status: str = "written",
    canonical_pointer_ref: str | None = None,
    supersedes: str | None = None,
    repo_root: str | Path | None = None,
    owner_user: str = "user/local",
    body: str | None = None,
) -> Path:
    """Write a resume-ledger (spec §2.3; DOC1 §7; continuity).

    The in-flight state + immediate next actions for the NEXT incarnation of
    THIS ``worker`` after a restart. id = ``<date>-HHMM-<slug>`` per §1.2
    (slug from worker); on-disk file ``resume-ledgers/<id>.md``. Carries
    owner_user.
    """
    repo = Path(repo_root) if repo_root else Path.cwd()
    rl_dir = ledger_paths.compat_kind_dir(repo, "resume-ledgers")

    date_str = _today_iso()
    _prefix = f"{date_str}-{_utc_hhmm()}-"
    ledger_id = _prefix + _cap_slug(_slugify(worker), _prefix)

    fm = {
        "id": ledger_id,
        "type": "resume-ledger",
        "worker": worker,
        "status": status,
        "in_flight_state": in_flight_state,
        "next_actions": list(next_actions),
        "created_at": _utc_now_iso(),
        "author": author,
        "owner_user": owner_user,
        "canonical_pointer_ref": canonical_pointer_ref,
        "supersedes": supersedes,
    }
    validators.validate_resume_ledger(fm)

    resolved_body = body if body is not None else _resume_ledger_body(
        worker, in_flight_state, next_actions
    )
    if not resolved_body.endswith("\n"):
        resolved_body += "\n"

    target = rl_dir / f"{ledger_id}.md"
    _fm.write(target, fm, resolved_body)
    index.render(rl_dir, title="Resume-ledgers", columns=index.RESUME_LEDGER_COLUMNS)
    cross_links.rebuild_link_index(repo)
    return target


def _resume_ledger_body(
    worker: str, in_flight_state: str, next_actions: list[str]
) -> str:
    lines = [
        f"# Resume ledger — {worker}",
        "",
        "## In-flight state",
        "",
        in_flight_state.strip() or "(none recorded)",
        "",
        "## Next actions",
        "",
    ]
    if not next_actions:
        lines.append("(none recorded)")
    else:
        lines.extend(f"- {action}" for action in next_actions)
    lines.append("")
    return "\n".join(lines)


def write_canonical_pointer(
    *,
    names: str,
    points_to: str,
    updated_by: str,
    repo_root: str | Path | None = None,
    owner_user: str = "user/local",
    body: str | None = None,
) -> Path:
    """Write/update a canonical-pointer (spec §2.3; DOC1 §7).

    One per named body-of-work; **mutable head** — re-invoking with the same
    ``names`` updates ``points_to`` + ``updated_at`` in place (not
    forward-only). id = names slug; on-disk file ``pointers/<slug>.md``.
    Carries owner_user.
    """
    repo = Path(repo_root) if repo_root else Path.cwd()
    pointers_dir = ledger_paths.compat_kind_dir(repo, "pointers")

    slug = _slugify(names)
    pointer_id = _cap_slug(slug, "")

    fm = {
        "id": pointer_id,
        "type": "canonical-pointer",
        "names": names,
        "points_to": points_to,
        "updated_at": _utc_now_iso(),
        "updated_by": updated_by,
        "owner_user": owner_user,
    }
    validators.validate_canonical_pointer(fm)

    resolved_body = body if body is not None else (
        f"# Canonical pointer — {names}\n\n"
        f"Current source-of-truth: `{points_to}`\n"
    )
    if not resolved_body.endswith("\n"):
        resolved_body += "\n"

    target = pointers_dir / f"{pointer_id}.md"
    _fm.write(target, fm, resolved_body)
    index.render(
        pointers_dir, title="Canonical-pointers", columns=index.CANONICAL_POINTER_COLUMNS
    )
    cross_links.rebuild_link_index(repo)
    return target
