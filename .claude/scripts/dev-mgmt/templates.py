"""Load entity templates from ``docs/.templates/``.

Sprint 1 shipped ``decision``. Sprint 2 adds ``sprint-plan`` and
``retrospective``. Sprint 3 adds ``handoff``. Sprint 4 adds ``issue`` +
``review``. Sprint 5 adds ``task-line`` (inline-list-item reference doc;
the frontmatter mirrors the parser output shape rather than describing a
standalone file) and ``conversation`` (full §6 + D22-D25 schema with
two-section body per D23). An inline default is used when the on-disk
template file is missing, so the helper lib is usable in fresh repos
before any template has been authored.
"""
from __future__ import annotations

from pathlib import Path

import frontmatter

_DEFAULTS: dict[str, tuple[dict, str]] = {
    "decision": (
        {
            "id": None,
            "type": "decision",
            "title": None,
            "status": "accepted",
            "scope": None,
            "sprint_id": None,
            "stage": None,
            "options": [],
            "created_at": None,
            "author": None,
            "authored_with": [],
            "linked_msg_ids": [],
            "supersedes": None,
        },
        (
            "# (title)\n\n"
            "## Why this decision was made\n\n(rationale)\n\n"
            "## Options considered\n\n(option list)\n\n"
            "## What this affects\n\n(impact, if known)\n"
        ),
    ),
    "sprint-plan": (
        {
            "id": None,
            "type": "plan",
            "plan_type": "forge",
            "title": None,
            "sprint_id": None,
            "status": "active",
            "version": 1,
            "previous_version_id": None,
            "created_at": None,
            "author": None,
            "linked_design_docs": [],
        },
        (
            "# (title)\n\n"
            "## Context\n\n(why this sprint exists, what came before)\n\n"
            "## Scope\n\n(what ships this sprint)\n\n"
            "## Verification\n\n(how we know this sprint is done — DoD)\n\n"
            "## Out of scope\n\n(what is deferred)\n"
        ),
    ),
    "retrospective": (
        {
            "id": None,
            "type": "retrospective",
            "title": None,
            "sprint_id": None,
            "status": "completed",
            "shipped_at": None,
            "created_at": None,
            "author": None,
            "linked_decisions": [],
            "linked_reviews": [],
            "test_results": None,
        },
        (
            "# (title)\n\n"
            "## What shipped\n\n(deliverables)\n\n"
            "## Verification\n\n(DoD checks green; any caveats)\n\n"
            "## Choices worth flagging\n\n(non-obvious decisions made during execution)\n\n"
            "## Out of scope\n\n(what we deferred and why)\n\n"
            "## What's next\n\n(natural follow-up sprint(s))\n"
        ),
    ),
    "handoff": (
        {
            "id": None,
            "type": "handoff",
            "title": None,
            "topic": None,
            "trigger": "manual",
            "sprint_id": None,
            "stage": None,
            "status": "written",
            "created_at": None,
            "author": None,
            "since_handoff_id": None,
            "since_msg_id": None,
            "linked_decisions": [],
            "linked_issues": [],
            "linked_tasks": [],
            "linked_msg_ids": [],
            "next_action": None,
        },
        (
            "# (title)\n\n"
            "## Current state\n\n(active sprint id + stage; the one-paragraph \"where are we right now\")\n\n"
            "## Since last handoff\n\n(what happened between this handoff and the prior one — decisions made, issues raised, tasks closed; cite ids)\n\n"
            "## What's next\n\n(the immediate next action for whoever picks up; one sentence is fine)\n\n"
            "## Notes\n\n(optional context — blockers, open questions, links worth following)\n"
        ),
    ),
    "issue": (
        {
            "id": None,
            "type": "issue",
            "title": None,
            "status": "open",
            "severity": None,
            "scope": None,
            "sprint_id": None,
            "stage": None,
            "class": None,
            "created_at": None,
            "reporter": None,
            "linked_decisions": [],
            "linked_reviews": [],
            "linked_msg_ids": [],
        },
        (
            "# (title)\n\n"
            "## Reproduction\n\n(steps to reproduce — minimal repro path, environment, observed vs expected)\n\n"
            "## Root cause\n\n(what's actually wrong, once known; leave as TBD if still investigating)\n\n"
            "## Fix path\n\n(approach for the fix — code change, test addition, design tweak; cite linked decisions if any)\n\n"
            "## Notes\n\n(optional context — related issues/reviews, blockers, links worth following)\n"
        ),
    ),
    "review": (
        {
            "id": None,
            "type": "review",
            "review_type": None,
            "title": None,
            "status": "completed",
            "scope": None,
            "sprint_id": None,
            "stage": None,
            "findings": [],
            "created_at": None,
            "author": None,
            "linked_decisions": [],
            "linked_msg_ids": [],
        },
        (
            "# (title)\n\n"
            "## Summary\n\n(one-paragraph overview — what was reviewed, headline takeaway)\n\n"
            "## Findings\n\n{findings_block}\n\n"
            "## Recommendations\n\n(what to do about the findings — bulleted action items; cite linked decisions if any)\n\n"
            "## Notes\n\n(optional context — methodology, scope limitations, follow-up review candidates)\n"
        ),
    ),
    "task-line": (
        {
            "id": None,
            "type": "task",
            "status": "pending",
            "description": None,
            "sprint_id": None,
            "assignee": None,
            "linked_issues": [],
            "linked_decisions": [],
        },
        (
            "# Task line format (D20.A)\n\n"
            "Tasks are inline list items in a sprint's tasks.md file — not standalone "
            "entity files. The frontmatter above mirrors what validate_task_line returns "
            "for a single line; the on-disk source of truth is the line itself.\n\n"
            "## Line shape\n\n"
            "`- [<checkbox>] **<task-id>** — <description>[ (<metadata-block>)]`\n\n"
            "- `[ ]` = non-completed; `[x]` = completed (canonical-only per Q2a)\n"
            "- task-id = `task-<sprint-id>.<NN>` (D19)\n"
            "- metadata block = `(key: value; key: value; key: [item, item])` at end-of-line\n"
            "- forbidden chars in values (Q1b): `; ) ] ,`\n\n"
            "See docs/.templates/task-line.md for full reference.\n"
        ),
    ),
    "conversation": (
        {
            "id": None,
            "type": "conversation",
            "title": None,
            "topic": None,
            "zone": None,
            "sprint_id": None,
            "stage": None,
            "participants": [],
            "verbatim_msg_range": [None, None],
            "started_at": None,
            "ended_at": None,
            "created_at": None,
            "linked_design_docs": [],
            "linked_decisions": [],
            "linked_reviews": [],
            "linked_issues": [],
            "linked_handoffs": [],
            "linked_msg_ids": [],
        },
        (
            "# (title)\n\n"
            "## Curated summary\n\n{curated_summary}\n\n"
            "## Verbatim chat (sender-attributed)\n\n{verbatim_chat}\n"
        ),
    ),
    "prd": (
        {
            "id": None,
            "type": "prd",
            "title": None,
            "state": "draft",
            "scope": None,
            "created_at": None,
            "author": None,
            "owner_user": "user/local",
            "linked_msg_ids": [],
            "linked_decisions": [],
            # Charter AXIS-13 + par-p0-defect-56 multi-repo coordination
            # convention: cross_repo_prds carries <repo>:<id> refs.
            "cross_repo_prds": [],
            # Chunk-0 open-Q ratify: workshop-lite-prd:// URI mirrors
            # D-WL-19 grammar; auto-populated by the writer.
            "parley_external_ref": None,
            # Per-state stamped fields (null at draft; transitions stamp).
            "ratified_at": None,
            "ratified_by": None,
            "technical_plan_url": None,
            "shipped_sha": None,
        },
        (
            # Charter AXIS-12: '## PM Summary' is the REQUIRED body
            # section the validator (validate_prd_body) enforces — the
            # belt-and-suspenders structural marker the parley-side
            # /translate skill (par-p0-defect-55) echoes verbatim.
            "# (title)\n\n"
            "## PM Summary\n\n"
            "(PM-readable plain-language summary of what this PRD describes "
            "and why it matters; bridged UP by the parley-side /translate "
            "skill via the par-p0-defect-55 product_manager role_kind.)\n\n"
            "## Scope\n\n"
            "(what this PRD covers — feature surface, user-facing behavior, "
            "out-of-scope explicit-exclusions)\n\n"
            "## Requirements\n\n"
            "(numbered requirement list — the PM-authored substantive content)\n\n"
            "## Acceptance criteria\n\n"
            "(measurable conditions for 'shipped' — how the PM knows the work "
            "satisfies the requirements)\n\n"
            "## Cross-repo references\n\n"
            "(when this PRD coordinates with PRDs in other repos, list them "
            "as cross_repo_prds: [<repo>:<id>] in the frontmatter; this "
            "section is the human-readable narrative companion to that list)\n\n"
            "## Lifecycle\n\n"
            "(transition log appended as the PRD progresses: "
            "draft → ratified → converting → technical_plan_ready → shipped)\n"
        ),
    ),
}


# Map canonical entity_type → disk-file basename when they differ.
# Resolves Issue 2026-05-14-03 (templates.load(retrospective) ↔ retro.md mismatch).
_ENTITY_FILE_NAMES: dict[str, str] = {
    "retrospective": "retro",
}

# Aliases callers may use; normalized to the canonical entity_type before lookup.
_ALIASES: dict[str, str] = {
    "retro": "retrospective",
}


def load(entity_type: str, repo_root: str | Path | None = None) -> tuple[dict, str]:
    """Load a template for ``entity_type``.

    Accepts either the canonical entity_type (e.g. ``"retrospective"``) or a
    registered alias (e.g. ``"retro"``); both resolve to the same template.
    If ``repo_root/docs/.templates/<basename>.md`` exists, parse it (the
    basename is the canonical entity_type unless an entry in
    ``_ENTITY_FILE_NAMES`` overrides). Otherwise return a deep copy of the
    inline default.
    """
    entity_type = _ALIASES.get(entity_type, entity_type)
    if repo_root is not None:
        file_basename = _ENTITY_FILE_NAMES.get(entity_type, entity_type)
        tpl_path = Path(repo_root) / "docs" / ".templates" / f"{file_basename}.md"
        if tpl_path.exists():
            fm, body = frontmatter.parse(tpl_path)
            return dict(fm), body

    if entity_type not in _DEFAULTS:
        raise ValueError(f"unknown entity type: {entity_type!r}")
    fm, body = _DEFAULTS[entity_type]
    return dict(fm), body
