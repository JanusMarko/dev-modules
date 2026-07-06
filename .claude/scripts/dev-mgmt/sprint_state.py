"""Sprint-state aggregation for the ``wl sprint-status`` verb.

Reads a sprint's current state from a single repo's workshop-lite entity
files (sprint folder, decisions, issues, tasks.md) plus the repo's git
log for boundary commits. The CLI verb composes this per-repo collector
across multiple ``--repo`` flags to render a cross-repo picture for
sprints that span repos.

Parley-agnostic (Hard Rule 1): no parley imports, no shell-outs to
parley. Reads from local filesystem + ``git log`` only.
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable

import frontmatter
import ledger_paths


# --- Data shapes -----------------------------------------------------------


@dataclass
class TaskSummary:
    id: str
    description: str
    status: str
    assignee: str | None = None


@dataclass
class DecisionRef:
    id: str
    title: str
    status: str
    path: str


@dataclass
class IssueRef:
    id: str
    title: str
    severity: str
    status: str
    path: str


@dataclass
class BoundaryCommit:
    sha: str
    subject: str
    author_date: str


@dataclass
class RepoSprintState:
    repo_root: str
    sprint_id: str
    phase: str
    plan_path: str | None
    tasks_path: str | None
    tasks: list[TaskSummary] = field(default_factory=list)
    pending_decisions: list[DecisionRef] = field(default_factory=list)
    accepted_decisions: list[DecisionRef] = field(default_factory=list)
    pending_issues: list[IssueRef] = field(default_factory=list)
    boundary_commits: list[BoundaryCommit] = field(default_factory=list)


@dataclass
class CrossRepoSprintState:
    sprint_id: str
    repos: list[RepoSprintState] = field(default_factory=list)


# Phase constants — pure data, not enums (keeps JSON output as plain strings).
PHASE_IN_FLIGHT = "in_flight"
PHASE_BOUNDARY_PENDING = "boundary_pending"
PHASE_ARCHIVED = "archived"
PHASE_ABSENT = "absent"

_OPEN_ISSUE_STATUSES = {"open", "investigating"}
_OPEN_DECISION_STATUSES = {"open"}
_ACCEPTED_DECISION_STATUSES = {"accepted"}


# --- Phase detection -------------------------------------------------------


def detect_phase(repo_root: Path, sprint_id: str) -> tuple[str, Path | None]:
    """Return ``(phase, sprint_dir_or_None)``.

    ``sprint_dir`` is the resolved folder (active or archive) when present,
    so callers don't re-do the lookup. ``boundary_pending`` is the
    transient state where the sprint is still in ``active/`` but a
    ``retro.md`` exists — usually means ``/end-sprint`` was interrupted
    after retro-write but before archive-move.
    """
    sprints = ledger_paths.compat_sprints_dir(repo_root)
    active = sprints / "active" / f"sprint-{sprint_id}"
    archive = sprints / "archive" / f"sprint-{sprint_id}"
    if active.is_dir():
        if (active / "retro.md").is_file():
            return PHASE_BOUNDARY_PENDING, active
        return PHASE_IN_FLIGHT, active
    if archive.is_dir():
        return PHASE_ARCHIVED, archive
    return PHASE_ABSENT, None


# --- Tasks -----------------------------------------------------------------


def _collect_tasks(sprint_dir: Path, sprint_id: str) -> tuple[list[TaskSummary], Path | None]:
    """Parse the sprint's ``tasks.md`` into TaskSummary records.

    Reuses ``entities._scan_tasks`` so the parse stays consistent with how
    ``/add-task`` writes lines.
    """
    tasks_path = sprint_dir / "tasks.md"
    if not tasks_path.is_file():
        return [], None

    # Lazy import to keep import graph shallow (entities pulls templates,
    # which is heavier than this module needs at import time).
    import entities

    parsed = entities._scan_tasks(tasks_path, sprint_id)
    summaries: list[TaskSummary] = []
    for t in parsed:
        summaries.append(
            TaskSummary(
                id=str(t.get("id") or ""),
                description=str(t.get("description") or ""),
                status=str(t.get("status") or "pending"),
                assignee=t.get("assignee"),
            )
        )
    return summaries, tasks_path


# --- Decisions + Issues ----------------------------------------------------


def _iter_entity_files(entity_dir: Path) -> Iterable[Path]:
    """Yield ``*.md`` files in ``entity_dir`` excluding the INDEX."""
    if not entity_dir.is_dir():
        return
    for p in sorted(entity_dir.glob("*.md")):
        if p.name == "INDEX.md":
            continue
        yield p


def _sprint_match(fm: dict, sprint_id: str) -> bool:
    """True if a decision/issue/review frontmatter mapping references this sprint.

    Match rules (any):
      - ``sprint_id`` field equals ``sprint_id``
      - ``scope`` field equals ``"sprint:<sprint_id>"``
      - ``linked_sprints`` list contains ``sprint_id``
    """
    if fm.get("sprint_id") == sprint_id:
        return True
    scope = fm.get("scope")
    if isinstance(scope, str) and scope == f"sprint:{sprint_id}":
        return True
    linked = fm.get("linked_sprints")
    if isinstance(linked, list) and sprint_id in linked:
        return True
    return False


def _collect_decisions(
    repo_root: Path, sprint_id: str
) -> tuple[list[DecisionRef], list[DecisionRef]]:
    """Return ``(pending, accepted)`` decision lists scoped to ``sprint_id``.

    Pending = status in ``{open}``. Accepted = status in ``{accepted}``.
    Rejected / superseded decisions are dropped from both lists — they're
    historical noise for a sprint-status view (the doc still exists on
    disk and is reachable via the decisions INDEX).
    """
    decisions_dir = ledger_paths.compat_kind_dir(repo_root, "decisions")
    pending: list[DecisionRef] = []
    accepted: list[DecisionRef] = []
    for path in _iter_entity_files(decisions_dir):
        try:
            fm, _body = frontmatter.parse(path)
        except (ValueError, OSError):
            continue
        if not _sprint_match(fm, sprint_id):
            continue
        status = str(fm.get("status") or "")
        ref = DecisionRef(
            id=path.stem,
            title=str(fm.get("title") or path.stem),
            status=status or "unknown",
            path=str(path.relative_to(repo_root)),
        )
        if status in _OPEN_DECISION_STATUSES:
            pending.append(ref)
        elif status in _ACCEPTED_DECISION_STATUSES:
            accepted.append(ref)
    return pending, accepted


def _collect_issues(repo_root: Path, sprint_id: str) -> list[IssueRef]:
    """Open issues (status in {open, investigating}) scoped to ``sprint_id``."""
    issues_dir = ledger_paths.compat_kind_dir(repo_root, "issues")
    out: list[IssueRef] = []
    for path in _iter_entity_files(issues_dir):
        try:
            fm, _body = frontmatter.parse(path)
        except (ValueError, OSError):
            continue
        if not _sprint_match(fm, sprint_id):
            continue
        status = str(fm.get("status") or "")
        if status not in _OPEN_ISSUE_STATUSES:
            continue
        out.append(
            IssueRef(
                id=path.stem,
                title=str(fm.get("title") or path.stem),
                severity=str(fm.get("severity") or "unknown"),
                status=status,
                path=str(path.relative_to(repo_root)),
            )
        )
    return out


# --- Boundary commits ------------------------------------------------------


def _collect_boundary_commits(
    repo_root: Path, sprint_id: str, limit: int = 10
) -> list[BoundaryCommit]:
    """Return commits whose subject/body mentions the sprint id.

    Uses ``git log --grep=<sprint_id>`` (fixed-string via ``--fixed-strings``).
    Returns an empty list if not a git repo or if git is not on PATH —
    workshop-lite is parley-agnostic and not strictly git-coupled, so we
    degrade silently rather than raising.
    """
    if not (repo_root / ".git").exists():
        return []
    try:
        proc = subprocess.run(
            [
                "git",
                "-C",
                str(repo_root),
                "log",
                f"--max-count={limit}",
                "--grep",
                sprint_id,
                "--fixed-strings",
                "--pretty=format:%h%x09%aI%x09%s",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return []
    if proc.returncode != 0:
        return []
    out: list[BoundaryCommit] = []
    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t", 2)
        if len(parts) != 3:
            continue
        sha, when, subject = parts
        out.append(BoundaryCommit(sha=sha, subject=subject, author_date=when))
    return out


# --- Per-repo collector ----------------------------------------------------


def collect_sprint_state(
    repo_root: Path | str,
    sprint_id: str,
    *,
    commit_limit: int = 10,
) -> RepoSprintState:
    """Aggregate one repo's view of a sprint.

    Always returns a record; missing sprints set ``phase=absent`` and all
    list fields empty (still scans decisions/issues — a sprint folder
    may be absent in one repo while entities cross-referencing the
    sprint live there, e.g. a parley-side decision scoped to a
    workshop-lite sprint).
    """
    repo = Path(repo_root).resolve()
    phase, sprint_dir = detect_phase(repo, sprint_id)

    plan_path = None
    tasks: list[TaskSummary] = []
    tasks_path: Path | None = None
    if sprint_dir is not None:
        plan_md = sprint_dir / "plan.md"
        if plan_md.is_file():
            plan_path = str(plan_md.relative_to(repo))
        tasks, tasks_path_resolved = _collect_tasks(sprint_dir, sprint_id)
        if tasks_path_resolved is not None:
            tasks_path = tasks_path_resolved

    pending_decisions, accepted_decisions = _collect_decisions(repo, sprint_id)
    pending_issues = _collect_issues(repo, sprint_id)
    boundary_commits = _collect_boundary_commits(repo, sprint_id, limit=commit_limit)

    return RepoSprintState(
        repo_root=str(repo),
        sprint_id=sprint_id,
        phase=phase,
        plan_path=plan_path,
        tasks_path=str(tasks_path.relative_to(repo)) if tasks_path else None,
        tasks=tasks,
        pending_decisions=pending_decisions,
        accepted_decisions=accepted_decisions,
        pending_issues=pending_issues,
        boundary_commits=boundary_commits,
    )


def collect_cross_repo(
    repo_roots: Iterable[Path | str],
    sprint_id: str,
    *,
    commit_limit: int = 10,
) -> CrossRepoSprintState:
    """Collect a sprint's state across multiple repos.

    Repos are visited in the order given. De-duplication on resolved
    path so a caller passing the same repo twice (e.g., explicit + cwd
    default) doesn't double-count.
    """
    seen: set[str] = set()
    repos: list[RepoSprintState] = []
    for root in repo_roots:
        resolved = str(Path(root).resolve())
        if resolved in seen:
            continue
        seen.add(resolved)
        repos.append(
            collect_sprint_state(resolved, sprint_id, commit_limit=commit_limit)
        )
    return CrossRepoSprintState(sprint_id=sprint_id, repos=repos)


# --- Formatters ------------------------------------------------------------


def to_json_obj(state: CrossRepoSprintState) -> dict:
    """JSON-serializable plain-dict view (asdict; dataclasses are flat)."""
    return asdict(state)


def to_json_str(state: CrossRepoSprintState, *, indent: int = 2) -> str:
    return json.dumps(to_json_obj(state), indent=indent, sort_keys=False)


def _task_counts(tasks: list[TaskSummary]) -> dict[str, int]:
    counts: dict[str, int] = {
        "pending": 0,
        "in_progress": 0,
        "completed": 0,
        "blocked": 0,
    }
    for t in tasks:
        counts[t.status] = counts.get(t.status, 0) + 1
    return counts


def format_text(state: CrossRepoSprintState, *, detail: bool = False) -> str:
    """Render a human-readable text report.

    Sections per repo: header (path + phase), task counts (or full list
    under ``--detail``), pending decisions, pending issues, recent
    boundary commits. Absent-phase repos still render — empty sections
    are dropped to avoid noise but the header line stays so the operator
    sees the repo was checked.
    """
    lines: list[str] = []
    lines.append(f"# sprint-status: {state.sprint_id}")
    lines.append("")
    if not state.repos:
        lines.append("(no repos checked)")
        return "\n".join(lines) + "\n"

    for repo in state.repos:
        lines.append(f"## {repo.repo_root}")
        lines.append(f"phase: {repo.phase}")
        if repo.plan_path:
            lines.append(f"plan:  {repo.plan_path}")
        if repo.tasks_path:
            counts = _task_counts(repo.tasks)
            total = sum(counts.values())
            summary = (
                f"tasks: {total} total — "
                f"{counts['completed']} done, "
                f"{counts['in_progress']} in_progress, "
                f"{counts['pending']} pending, "
                f"{counts['blocked']} blocked"
            )
            lines.append(summary)
            if detail and repo.tasks:
                for t in repo.tasks:
                    marker = "[x]" if t.status == "completed" else "[ ]"
                    suffix = ""
                    if t.status not in ("completed", "pending"):
                        suffix = f" (status: {t.status})"
                    who = f" — @{t.assignee.lstrip('@')}" if t.assignee else ""
                    lines.append(f"  {marker} {t.id} — {t.description}{suffix}{who}")

        if repo.pending_decisions:
            lines.append("")
            lines.append(f"pending decisions ({len(repo.pending_decisions)}):")
            for d in repo.pending_decisions:
                lines.append(f"  - {d.id} — {d.title} [{d.status}]")

        if repo.pending_issues:
            lines.append("")
            lines.append(f"open issues ({len(repo.pending_issues)}):")
            for i in repo.pending_issues:
                lines.append(
                    f"  - {i.id} [{i.severity}/{i.status}] — {i.title}"
                )

        if detail and repo.accepted_decisions:
            lines.append("")
            lines.append(f"accepted decisions ({len(repo.accepted_decisions)}):")
            for d in repo.accepted_decisions:
                lines.append(f"  - {d.id} — {d.title}")

        if repo.boundary_commits:
            lines.append("")
            lines.append(
                f"recent boundary commits ({len(repo.boundary_commits)}):"
            )
            for c in repo.boundary_commits:
                lines.append(f"  - {c.sha}  {c.author_date}  {c.subject}")

        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
