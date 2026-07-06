"""Per-verb adapter functions for the workshop-lite MCP server.

Each adapter replays cli.py main()'s per-verb post-parse logic (JSON-string
decode of --options-json / --findings-json, CSV split of --linked-X /
--authored-with, Path conversion of --repo-root, etc.) before calling the
corresponding entities/dispatch/prd/wip_claim handler. Returning the handler's
result instead of printing + sys.exit-style return.

This preserves CLI/MCP byte-identical parity (test #3 per decision 2026-06-05-02)
WITHOUT touching cli.py — the q2 ratify msg-6ef9864a89bd opted (c) 2.iii-argparse-
introspection, explicitly NOT (d) 2.iv-hybrid (cli.py refactor). Drift between
cli.py main() dispatch and these adapters is the test #3 surface.

Chunk-2 (this file, write verbs): record_decision, record_issue, record_review,
record_handoff, start_sprint, end_sprint, add_task, capture_conversation.

Chunks 3 (read tools) + 4 (transition verbs) extend the adapter set.
"""

from __future__ import annotations

import importlib.util as _il_util
import json
from pathlib import Path
from typing import Any

# Workshop-lite handler modules (parley-agnostic at lib layer per HR-#1).
import entities
import sprint_spec
import dispatch as dispatch_mod
import prd as prd_mod
import wip_claim as wip_claim_mod
import pending_views
import cross_links
import frontmatter as fm_mod
import ledger_paths


# Path-aware cli loader: load the canonical sibling cli.py via its file path
# instead of `from cli import ...`. The bare-name import is fragile when
# another sys.path entry contains a sibling cli.py (observed under the
# full pytest suite, where `tests/test_auto_decision_doc.py` inserts
# `.claude/skills/auto-decision-doc/` — which has its OWN cli.py — at
# sys.path[0]). spec_from_file_location resolves the right file unambiguously.
def _load_canonical_cli():
    cli_path = Path(__file__).resolve().parent / "cli.py"
    spec = _il_util.spec_from_file_location("_wl_canonical_cli", cli_path)
    assert spec is not None and spec.loader is not None
    mod = _il_util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_cli = _load_canonical_cli()
_split_csv = _cli._split_csv
_parse_duration = _cli._parse_duration


# Entity type → docs subdirectory mapping. Used by wl_read_entity +
# wl_cross_links_walk to locate entity files by (type, id).
_ENTITY_TYPE_TO_DIR: dict[str, str] = {
    "decision": "decisions",
    "issue": "issues",
    "review": "reviews",
    "handoff": "handoffs",
    "conversation": "conversations",
    "dispatch": "dispatches",
    "prd": "prds",
    "wip": "wip",
    "gate": "gates",
}


# ---------------------------------------------------------------------------
# Write-verb adapters (chunk-2, 8 verbs per decision 2026-06-04-05)
#
# Each adapter is a pure dispatch: receive the MCP-validated args dict as
# kwargs (argparse-dest underscore form), do the same post-parse cli.py main()
# does, call the entities.* handler, return the result. Errors bubble up as
# domain exceptions (caught + translated by mcp_server.translate_errors).
# ---------------------------------------------------------------------------


def _to_repo_root(value: str | None) -> Path | None:
    return Path(value) if value else None


def record_decision(**kw: Any) -> str:
    path = entities.record_decision(
        title=kw["title"],
        rationale=kw["rationale"],
        options=json.loads(kw["options_json"]),
        scope=kw["scope"],
        author=kw["author"],
        repo_root=_to_repo_root(kw.get("repo_root")),
        authored_with=_split_csv(kw.get("authored_with", "")),
        linked_decisions=_split_csv(kw.get("linked_decisions", "")),
        linked_reviews=_split_csv(kw.get("linked_reviews", "")),
        linked_msg_ids=_split_csv(kw.get("linked_msg_ids", "")),
        sprint_id=kw.get("sprint_id"),
        stage=kw.get("stage"),
        supersedes=kw.get("supersedes"),
        status=kw.get("status", "accepted"),
        affects=kw.get("affects"),
    )
    return str(path)


def start_sprint(**kw: Any) -> str:
    path = entities.start_sprint(
        sprint_id=kw["sprint_id"],
        title=kw["title"],
        author=kw["author"],
        repo_root=_to_repo_root(kw.get("repo_root")),
        plan_body_path=kw.get("from_plan"),
        force=kw.get("force", False),
        linked_design_docs=_split_csv(kw.get("linked_design_docs", "")),
    )
    # Phase 3 (sub-spec §8.1): --spec <kind> creates initial spec.yaml.
    if kw.get("spec"):
        repo = _to_repo_root(kw.get("repo_root")) or Path.cwd()
        charter_ref = _split_csv(kw.get("spec_charter_ref", "")) or []
        sprint_spec.write_initial_spec_yaml(
            repo_root=repo,
            sprint_id=kw["sprint_id"],
            sprint_kind=kw["spec"],
            author=kw["author"],
            has_user_journey=kw.get("spec_has_user_journey", False),
            charter_ref=charter_ref,
        )
    return str(path)


def end_sprint(**kw: Any) -> str:
    retro_body: str | None = None
    if kw.get("retro_body_path"):
        retro_body = Path(kw["retro_body_path"]).read_text(encoding="utf-8")
    # NOTE: entities.end_sprint's `test_results: dict | None` annotation is a
    # pre-existing cli.py-vs-entities.py divergence — cli.py passes the result
    # of `json.loads()` (which may be a list or dict depending on content) and
    # the runtime accepts both. Faithful replay; Pyright noise filed
    # implicitly as a future follow-on.
    test_results: Any = None
    if kw.get("test_results_json"):
        test_results = json.loads(kw["test_results_json"])
    # NOTE: cli.py runs `_maybe_run_end_sprint_gate` here (sub-spec §4.2 gate).
    # MCP-side replay is intentionally omitted in chunk-2: that gate writes to
    # sys.stderr + returns a non-zero exit code, which maps poorly to MCP's
    # tool-result shape. Gate-failure semantics are CLI-only for now; MCP
    # callers that need the gate run /end-sprint via CLI. Surfaced for
    # potential follow-on (4th-amendment-class).
    path = entities.end_sprint(
        sprint_id=kw["sprint_id"],
        author=kw["author"],
        repo_root=_to_repo_root(kw.get("repo_root")),
        retro_title=kw.get("retro_title"),
        retro_body=retro_body,
        force=kw.get("force", False),
        test_results=test_results,
        linked_decisions=_split_csv(kw.get("linked_decisions", "")),
        linked_reviews=_split_csv(kw.get("linked_reviews", "")),
    )
    return str(path)


def record_handoff(**kw: Any) -> str:
    path = entities.record_handoff(
        title=kw["title"],
        topic=kw["topic"],
        author=kw["author"],
        trigger=kw["trigger"],
        sprint_id=kw.get("sprint_id"),
        stage=kw.get("stage"),
        since_handoff_id=kw.get("since_handoff_id"),
        since_msg_id=kw.get("since_msg_id"),
        repo_root=_to_repo_root(kw.get("repo_root")),
        body=kw.get("body"),
        body_from_path=kw.get("body_from_file"),
        linked_decisions=_split_csv(kw.get("linked_decisions", "")),
        linked_issues=_split_csv(kw.get("linked_issues", "")),
        linked_tasks=_split_csv(kw.get("linked_tasks", "")),
        linked_msg_ids=_split_csv(kw.get("linked_msg_ids", "")),
        next_action=kw.get("next_action"),
    )
    return str(path)


def record_issue(**kw: Any) -> str:
    path = entities.record_issue(
        title=kw["title"],
        severity=kw["severity"],
        scope=kw["scope"],
        reporter=kw["reporter"],
        status=kw.get("status", "open"),
        sprint_id=kw.get("sprint_id"),
        stage=kw.get("stage"),
        klass=kw.get("klass"),
        repo_root=_to_repo_root(kw.get("repo_root")),
        body=kw.get("body"),
        body_from_path=kw.get("body_from_file"),
        linked_decisions=_split_csv(kw.get("linked_decisions", "")),
        linked_reviews=_split_csv(kw.get("linked_reviews", "")),
        linked_msg_ids=_split_csv(kw.get("linked_msg_ids", "")),
    )
    return str(path)


def record_review(**kw: Any) -> str:
    findings = json.loads(kw["findings_json"])
    accurate_trail = (
        json.loads(kw["accurate_trail_json"])
        if kw.get("accurate_trail_json")
        else None
    )
    path = entities.record_review(
        title=kw["title"],
        review_type=kw["review_type"],
        scope=kw["scope"],
        author=kw["author"],
        # Default matches cli.py record-review --status default ("completed");
        # the chunk-2 adapter's prior "open" default mismatched and was
        # surfaced by the chunk-5 byte-identical parity test.
        status=kw.get("status", "completed"),
        sprint_id=kw.get("sprint_id"),
        stage=kw.get("stage"),
        repo_root=_to_repo_root(kw.get("repo_root")),
        body=kw.get("body"),
        body_from_path=kw.get("body_from_file"),
        findings=findings,
        accurate_trail=accurate_trail,
        linked_decisions=_split_csv(kw.get("linked_decisions", "")),
        linked_reviews=_split_csv(kw.get("linked_reviews", "")),
        linked_msg_ids=_split_csv(kw.get("linked_msg_ids", "")),
    )
    return str(path)


def add_task(**kw: Any) -> dict[str, str]:
    tasks_path, task_id = entities.add_task(
        sprint_id=kw["sprint_id"],
        description=kw["description"],
        assignee=kw.get("assignee"),
        status=kw.get("status", "pending"),
        linked_issues=_split_csv(kw.get("linked_issues", "")),
        linked_decisions=_split_csv(kw.get("linked_decisions", "")),
        repo_root=_to_repo_root(kw.get("repo_root")),
    )
    return {"tasks_path": str(tasks_path), "task_id": task_id}


def capture_conversation(**kw: Any) -> str:
    """MCP variant of capture-conversation.

    Supports a subset of CLI modes: `verbatim` (direct text) + `verbatim_from_file`.
    The stdin-based modes (`verbatim_from_stdin`, `verbatim_records_json_from_stdin`)
    are CLI-only — MCP tools don't have a per-call stdin channel. Callers that
    need stdin-mode capture invoke `python3 .claude/scripts/dev-mgmt/cli.py
    capture-conversation` directly.
    """
    # Resolve verbatim source — exactly one of {verbatim, verbatim_from_file}.
    verbatim_text: str | None = None
    if kw.get("verbatim"):
        verbatim_text = kw["verbatim"]
    elif kw.get("verbatim_from_file"):
        verbatim_text = Path(kw["verbatim_from_file"]).read_text(encoding="utf-8")
    elif kw.get("verbatim_from_stdin") or kw.get("verbatim_records_json_from_stdin"):
        raise ValueError(
            "MCP capture_conversation does not support stdin modes "
            "(verbatim_from_stdin / verbatim_records_json_from_stdin); "
            "use --verbatim (direct text) or --verbatim-from-file (file path), "
            "or invoke the CLI directly for stdin-based capture"
        )
    else:
        raise ValueError(
            "exactly one of verbatim or verbatim_from_file is required"
        )
    if not (verbatim_text or "").strip():
        raise ValueError(
            "refusing to write a Conversation with an empty verbatim body "
            "(issue 2026-05-15-05 silent-empty-capture guard)"
        )
    assert verbatim_text is not None  # narrow for downstream call

    # verbatim_msg_range parsing matches cli.py format "msg-first,msg-last".
    verbatim_msg_range: list[str | None] = [None, None]
    if kw.get("verbatim_msg_range"):
        pair = kw["verbatim_msg_range"].split(",")
        if len(pair) != 2:
            raise ValueError(
                "verbatim_msg_range must be 'msg-first,msg-last'"
            )
        verbatim_msg_range = [
            pair[0].strip() or None,
            pair[1].strip() or None,
        ]

    # D25: zone auto-detect (active sprint folder → 'sprint', else 'cross-sprint').
    zone = kw.get("zone")
    if zone is None:
        repo_for_zone = _to_repo_root(kw.get("repo_root")) or Path.cwd()
        active_dir = repo_for_zone / "docs" / "sprints" / "active"
        active_sprints = (
            [d for d in active_dir.iterdir() if d.is_dir()
             and d.name.startswith("sprint-")]
            if active_dir.exists() else []
        )
        zone = "sprint" if active_sprints else "cross-sprint"

    participants = _split_csv(kw.get("participants", "")) or []

    path = entities.capture_conversation(
        title=kw["title"],
        topic=kw["topic"],
        verbatim_text=verbatim_text,
        verbatim_msg_range=verbatim_msg_range,
        participants=participants,
        zone=zone,
        sprint_id=kw.get("sprint_id"),
        stage=kw.get("stage"),
        started_at=kw.get("started_at"),
        ended_at=kw.get("ended_at"),
        repo_root=_to_repo_root(kw.get("repo_root")),
        body=kw.get("body"),
        body_from_path=kw.get("body_from_file"),
        linked_design_docs=_split_csv(kw.get("linked_design_docs", "")),
        linked_decisions=_split_csv(kw.get("linked_decisions", "")),
        linked_reviews=_split_csv(kw.get("linked_reviews", "")),
        linked_issues=_split_csv(kw.get("linked_issues", "")),
        linked_handoffs=_split_csv(kw.get("linked_handoffs", "")),
        linked_msg_ids=_split_csv(kw.get("linked_msg_ids", "")),
    )
    return str(path)


# ---------------------------------------------------------------------------
# Tool registration entry-point (called from mcp_server.register_chunk2_*)
# ---------------------------------------------------------------------------


# (cli-subparser-name, mcp-tool-name, adapter-callable, description, kind)
_CHUNK2_BINDINGS: list[tuple[str, str, Any, str, str]] = [
    (
        "record-decision",
        "record_decision",
        record_decision,
        "Write a Decision entity to docs/decisions/<id>.md.",
        "write",
    ),
    (
        "start-sprint",
        "start_sprint",
        start_sprint,
        "Scaffold docs/sprints/active/sprint-<id>/ for a new sprint.",
        "write",
    ),
    (
        "end-sprint",
        "end_sprint",
        end_sprint,
        "Write retro.md (if absent), archive the sprint folder, re-INDEX. "
        "(MCP variant skips the sub-spec §4.2 end-sprint gate; use CLI for gated end.)",
        "write",
    ),
    (
        "handoff",
        "record_handoff",
        record_handoff,
        "Write a Handoff entity to docs/handoffs/<id>.md.",
        "write",
    ),
    (
        "record-issue",
        "record_issue",
        record_issue,
        "Write an Issue entity to docs/issues/<id>.md.",
        "write",
    ),
    (
        "record-review",
        "record_review",
        record_review,
        "Write a Review entity to docs/reviews/<id>.md.",
        "write",
    ),
    (
        "add-task",
        "add_task",
        add_task,
        "Append a Task line to the named sprint's tasks.md.",
        "write",
    ),
    (
        "capture-conversation",
        "capture_conversation",
        capture_conversation,
        "Write a Conversation entity to docs/conversations/<id>.md. "
        "(MCP variant supports `verbatim` or `verbatim_from_file`; "
        "stdin modes are CLI-only.)",
        "write",
    ),
]


def chunk2_bindings() -> list[tuple[str, str, Any, str, str]]:
    """Return the (cli_name, mcp_name, adapter, description, kind) tuples for
    chunk-2 verb registration. Consumed by `mcp_server.register_chunk2_write_verbs`.
    """
    return list(_CHUNK2_BINDINGS)


# ===========================================================================
# CHUNK-3 — Read tools (4 charter slots / 7 MCP tools per decision 2026-06-04-07)
# wl_whereami + wl_list_pending (4 variants) + wl_read_entity + wl_cross_links_walk
# ===========================================================================


def _repo_or_cwd(repo_root: str | None) -> Path:
    return Path(repo_root) if repo_root else Path.cwd()


def _ls_recent(dir_: Path, n: int = 5) -> list[str]:
    """Return the N most-recently-IDed entity ids in `dir_` (filename stem)."""
    if not dir_.exists():
        return []
    ids = [
        p.stem for p in dir_.iterdir()
        if p.is_file() and p.suffix == ".md" and not p.name.startswith("INDEX")
    ]
    ids.sort(reverse=True)
    return ids[:n]


def wl_whereami(**kw: Any) -> dict[str, Any]:
    """Structured snapshot of project state for an MCP-side agent.

    Composes from existing library callables — active sprint folder list +
    recent decisions / open issues / active dispatches / active wip / recent
    handoffs. NO substrate-router routing (the SKILL.md handles peer-pane
    routing; the MCP tool runs against the cwd-substrate by default).
    """
    repo = _repo_or_cwd(kw.get("repo_root"))

    # Active sprint(s): look in docs/sprints/active/sprint-*/
    active_dir = ledger_paths.compat_sprints_dir(repo) / "active"
    active_sprints: list[str] = []
    if active_dir.exists():
        active_sprints = sorted(
            d.name.removeprefix("sprint-")
            for d in active_dir.iterdir()
            if d.is_dir() and d.name.startswith("sprint-")
        )

    # Recent + open issues — walk docs/issues/ and filter.
    issues_dir = ledger_paths.compat_kind_dir(repo, "issues")
    open_issues: list[dict[str, Any]] = []
    if issues_dir.exists():
        for p in issues_dir.iterdir():
            if not p.is_file() or p.suffix != ".md" or p.name.startswith("INDEX"):
                continue
            try:
                fm, _body = fm_mod.parse(p)
            except Exception:
                continue
            if fm.get("status") == "open":
                open_issues.append({
                    "id": fm.get("id") or p.stem,
                    "title": fm.get("title"),
                    "severity": fm.get("severity"),
                    "scope": fm.get("scope"),
                })

    # Active dispatches via load_standing_dispatches.
    try:
        all_dispatches = dispatch_mod.load_standing_dispatches(repo)
    except Exception:
        all_dispatches = []
    active_dispatches = [
        {
            "id": d.get("id"),
            "title": d.get("title"),
            "kind": d.get("kind"),
            "recipients": d.get("recipients") or d.get("target_member_id_set"),
        }
        for d in all_dispatches
        if d.get("status") in (None, "open", "active")
    ]

    # Active WIP claims via load_active_claims.
    try:
        active_wip_claims = wip_claim_mod.load_active_claims(repo)
    except Exception:
        active_wip_claims = []
    active_wip = [
        {
            "id": c.get("id"),
            "seat": c.get("seat"),
            "scope_paths": c.get("scope_paths"),
            "expires_iso": c.get("expires_iso"),
        }
        for c in active_wip_claims
    ]

    return {
        "active_sprints": active_sprints,
        "recent_decisions": _ls_recent(ledger_paths.compat_kind_dir(repo, "decisions")),
        "open_issues": open_issues,
        "active_dispatches": active_dispatches,
        "active_wip": active_wip,
        "recent_handoffs": _ls_recent(ledger_paths.compat_kind_dir(repo, "handoffs")),
    }


def wl_list_open_issues(**kw: Any) -> list[dict[str, Any]]:
    """Return all open issues in docs/issues/, sorted by id desc."""
    repo = _repo_or_cwd(kw.get("repo_root"))
    issues_dir = ledger_paths.compat_kind_dir(repo, "issues")
    if not issues_dir.exists():
        return []
    out: list[dict[str, Any]] = []
    for p in sorted(issues_dir.iterdir(), reverse=True):
        if not p.is_file() or p.suffix != ".md" or p.name.startswith("INDEX"):
            continue
        try:
            fm, _body = fm_mod.parse(p)
        except Exception:
            continue
        if fm.get("status") != "open":
            continue
        out.append({
            "id": fm.get("id") or p.stem,
            "title": fm.get("title"),
            "severity": fm.get("severity"),
            "scope": fm.get("scope"),
            "reporter": fm.get("reporter"),
            "created_at": fm.get("created_at"),
        })
    return out


def wl_list_active_dispatches(**kw: Any) -> list[dict[str, Any]]:
    """Return all active (non-satisfied, non-superseded) standing dispatches.

    Optional `seat` arg routes through `pending_views.list_pending_dispatches`
    (returning only dispatches the named seat hasn't acted on); omitted seat
    returns the full active-dispatch list.
    """
    repo = _repo_or_cwd(kw.get("repo_root"))
    seat = kw.get("seat")
    if seat:
        return pending_views.list_pending_dispatches(repo, seat)
    try:
        return dispatch_mod.load_standing_dispatches(repo)
    except Exception:
        return []


def wl_list_active_wip(**kw: Any) -> list[dict[str, Any]]:
    """Return all active WIP claims (non-released, non-expired).

    Optional `seat` filters to that seat's claims only.
    """
    repo = _repo_or_cwd(kw.get("repo_root"))
    seat = kw.get("seat")
    try:
        claims = wip_claim_mod.load_active_claims(repo)
    except Exception:
        return []
    if seat:
        claims = [c for c in claims if c.get("seat") == seat]
    return claims


def wl_list_sprint_tasks(**kw: Any) -> list[dict[str, Any]]:
    """Return parsed task lines from `docs/sprints/active/sprint-<id>/tasks.md`.

    Returns [] if the sprint folder or tasks.md doesn't exist.
    """
    repo = _repo_or_cwd(kw.get("repo_root"))
    sprint_id = kw["sprint_id"]
    tasks_path = (
        ledger_paths.compat_sprints_dir(repo) / "active" / f"sprint-{sprint_id}" / "tasks.md"
    )
    if not tasks_path.exists():
        return []
    # Use entities._scan_tasks (the same parser cli.py + add_task use).
    return entities._scan_tasks(tasks_path, sprint_id)


def wl_read_entity(**kw: Any) -> dict[str, Any]:
    """Read an entity by (type, id) and return its frontmatter + body."""
    entity_type = kw["entity_type"]
    entity_id = kw["entity_id"]
    if entity_type not in _ENTITY_TYPE_TO_DIR:
        raise ValueError(
            f"unknown entity_type {entity_type!r}; "
            f"expected one of {sorted(_ENTITY_TYPE_TO_DIR.keys())}"
        )
    repo = _repo_or_cwd(kw.get("repo_root"))
    sub = _ENTITY_TYPE_TO_DIR[entity_type]
    path = ledger_paths.compat_kind_dir(repo, sub) / f"{entity_id}.md"
    if not path.exists():
        # Try with .md already present in entity_id (caller may pass either form)
        alt = ledger_paths.compat_kind_dir(repo, sub) / entity_id
        if alt.exists():
            path = alt
        else:
            raise FileNotFoundError(
                f"entity not found: {entity_type}/{entity_id} "
                f"(looked at {path})"
            )
    fm, body = fm_mod.parse(path)
    return {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "path": str(path),
        "frontmatter": fm,
        "body": body,
    }


def wl_cross_links_walk(**kw: Any) -> dict[str, Any]:
    """Walk linked_X cross-links from an entity.

    direction='forward': return the entity's own `linked_<kind>` fields.
    direction='reverse': return every entity that forward-links AT this one
    (derived projection via the maintained link index exposed by
    `cross_links.derived_reverse_links`).
    """
    entity_kind = kw["entity_kind"]
    entity_slug = kw["entity_slug"]
    direction = kw.get("direction", "forward")
    repo = _repo_or_cwd(kw.get("repo_root"))

    if direction == "forward":
        sub = _ENTITY_TYPE_TO_DIR.get(entity_kind)
        if sub is None:
            raise ValueError(
                f"unknown entity_kind {entity_kind!r}; "
                f"expected one of {sorted(_ENTITY_TYPE_TO_DIR.keys())}"
            )
        path = ledger_paths.compat_kind_dir(repo, sub) / f"{entity_slug}.md"
        if not path.exists():
            raise FileNotFoundError(
                f"entity not found: {entity_kind}/{entity_slug}"
            )
        fm, _body = fm_mod.parse(path)
        return {
            "entity_kind": entity_kind,
            "entity_slug": entity_slug,
            "direction": "forward",
            "linked_decisions": list(fm.get("linked_decisions") or []),
            "linked_reviews": list(fm.get("linked_reviews") or []),
            "linked_issues": list(fm.get("linked_issues") or []),
            "linked_tasks": list(fm.get("linked_tasks") or []),
            "linked_handoffs": list(fm.get("linked_handoffs") or []),
            "linked_msg_ids": list(fm.get("linked_msg_ids") or []),
            "linked_design_docs": list(fm.get("linked_design_docs") or []),
        }
    if direction == "reverse":
        try:
            reverse_map = cross_links.derived_reverse_links(repo)
        except Exception as exc:
            raise ValueError(
                f"failed to derive reverse links: {exc.__class__.__name__}: {exc}"
            ) from exc
        key = (entity_kind, entity_slug)
        return {
            "entity_kind": entity_kind,
            "entity_slug": entity_slug,
            "direction": "reverse",
            "incoming_links": reverse_map.get(key, []),
        }
    raise ValueError(
        f"direction must be 'forward' or 'reverse'; got {direction!r}"
    )


# ---------------------------------------------------------------------------
# Chunk-3 schemas (hand-written; no CLI counterpart per charter -07)
# ---------------------------------------------------------------------------


_SCHEMA_REPO_ROOT_OPT: dict[str, Any] = {
    "type": "string",
    "description": "Optional path to the workshop-lite repo root; defaults to cwd.",
}
_SCHEMA_SEAT_OPT: dict[str, Any] = {
    "type": "string",
    "description": "Optional @<seat-id> to filter for pending-for-seat semantics.",
}


_CHUNK3_BINDINGS: list[tuple[str, Any, str, dict[str, Any]]] = [
    (
        "wl_whereami",
        wl_whereami,
        "Structured snapshot of workshop-lite project state: active sprint(s), "
        "recent decisions, open issues, active dispatches, active WIP claims, "
        "recent handoffs. Composed from local on-disk substrate (cwd-rooted).",
        {
            "type": "object",
            "properties": {"repo_root": _SCHEMA_REPO_ROOT_OPT},
            "additionalProperties": False,
        },
    ),
    (
        "wl_list_open_issues",
        wl_list_open_issues,
        "Return all open Issue entities in docs/issues/, sorted by id desc.",
        {
            "type": "object",
            "properties": {"repo_root": _SCHEMA_REPO_ROOT_OPT},
            "additionalProperties": False,
        },
    ),
    (
        "wl_list_active_dispatches",
        wl_list_active_dispatches,
        "Return all active (non-satisfied, non-superseded) standing dispatches. "
        "Optional seat filters to dispatches the named seat hasn't acted on.",
        {
            "type": "object",
            "properties": {
                "repo_root": _SCHEMA_REPO_ROOT_OPT,
                "seat": _SCHEMA_SEAT_OPT,
            },
            "additionalProperties": False,
        },
    ),
    (
        "wl_list_active_wip",
        wl_list_active_wip,
        "Return all active WIP claims. Optional seat filters to that seat's claims.",
        {
            "type": "object",
            "properties": {
                "repo_root": _SCHEMA_REPO_ROOT_OPT,
                "seat": _SCHEMA_SEAT_OPT,
            },
            "additionalProperties": False,
        },
    ),
    (
        "wl_list_sprint_tasks",
        wl_list_sprint_tasks,
        "Return parsed task lines from a sprint's tasks.md.",
        {
            "type": "object",
            "properties": {
                "sprint_id": {
                    "type": "string",
                    "description": "The sprint id (e.g. 'workshop-lite.27').",
                },
                "repo_root": _SCHEMA_REPO_ROOT_OPT,
            },
            "required": ["sprint_id"],
            "additionalProperties": False,
        },
    ),
    (
        "wl_read_entity",
        wl_read_entity,
        "Read an entity by (entity_type, entity_id) and return its frontmatter "
        "+ body. Supported types: decision, issue, review, handoff, conversation, "
        "dispatch, prd, wip, gate.",
        {
            "type": "object",
            "properties": {
                "entity_type": {
                    "type": "string",
                    "enum": list(_ENTITY_TYPE_TO_DIR.keys()),
                    "description": "The entity type to read.",
                },
                "entity_id": {
                    "type": "string",
                    "description": "The entity id (filename stem; without .md extension).",
                },
                "repo_root": _SCHEMA_REPO_ROOT_OPT,
            },
            "required": ["entity_type", "entity_id"],
            "additionalProperties": False,
        },
    ),
    (
        "wl_cross_links_walk",
        wl_cross_links_walk,
        "Walk linked_X cross-links from an entity. direction='forward' returns "
        "the entity's own linked_<kind> fields. direction='reverse' returns every "
        "entity that forward-links AT this one (derived projection — never stored "
        "on target frontmatter; served from the maintained link index).",
        {
            "type": "object",
            "properties": {
                "entity_kind": {
                    "type": "string",
                    "enum": list(_ENTITY_TYPE_TO_DIR.keys()),
                },
                "entity_slug": {"type": "string"},
                "direction": {
                    "type": "string",
                    "enum": ["forward", "reverse"],
                    "default": "forward",
                },
                "repo_root": _SCHEMA_REPO_ROOT_OPT,
            },
            "required": ["entity_kind", "entity_slug"],
            "additionalProperties": False,
        },
    ),
]


def chunk3_bindings() -> list[tuple[str, Any, str, dict[str, Any]]]:
    """Return (mcp_name, adapter, description, input_schema) tuples for chunk-3
    read-tool registration. Consumed by `mcp_server.register_chunk3_read_tools`.
    """
    return list(_CHUNK3_BINDINGS)


# ===========================================================================
# CHUNK-4 — Transition verbs (11 per decision 2026-06-05-01)
#
# 3 dispatch: record_dispatch / record_dispatch_satisfy / record_dispatch_supersede
# 5 prd:      record_prd / record_prd_ratify / record_prd_convert /
#             record_prd_technical_plan_ready / record_prd_ship
# 3 wip:      record_wip / record_wip_release / record_wip_extend
#
# Same q2=(c) argparse-introspection pattern as chunk-2: bindings carry a
# cli-subparser name; mcp_server registers via `get_subparser` + adapter.
# Each adapter replays the cli.py main() per-verb post-parse block (csv split,
# duration parsing, iso-timestamp parsing) before calling the dispatch_mod /
# prd_mod / wip_claim_mod handler.
#
# Note: 8 of these 11 verbs use POSITIONAL ids (claim_id, dispatch_id, prd_id,
# new_id, old_id, duration). The chunk-4 mcp_schema_derive extension emits
# positional dests as `required: true` properties in the derived JSON Schema.
# ===========================================================================


from datetime import datetime as _dt, timezone as _tz  # noqa: E402


def _parse_iso(name: str, value: str | None):
    """Parse an ISO-8601 timestamp string into a datetime, with Z→+00:00
    normalization. Mirrors cli.py record-dispatch's nested `_parse_iso_arg`.
    Returns None for None/empty input.
    """
    if value is None or value == "":
        return None
    try:
        return _dt.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError) as exc:
        raise ValueError(
            f"--{name} must be an ISO 8601 timestamp, got: {value!r} ({exc})"
        )


# ---- 3 dispatch adapters ---------------------------------------------------


def record_dispatch(**kw: Any) -> str:
    recipients_list = _split_csv(kw.get("recipients", "")) or []
    if not recipients_list:
        raise ValueError(
            "recipients must be a non-empty comma-separated list of FQID strings"
        )
    deadline = _parse_iso("deadline", kw.get("deadline"))
    expires_at = _parse_iso("expires-at", kw.get("expires_at"))
    path = dispatch_mod.record_standing_dispatch(
        repo_root=_to_repo_root(kw.get("repo_root")) or Path.cwd(),
        slug=kw["slug"],
        purpose=kw["purpose"],
        recipients=recipients_list,
        expected_outcome=kw["expected_outcome"],
        scope=kw["scope"],
        deadline=deadline,
        expires_at=expires_at,
        linked_msg_ids=list(kw.get("linked_msg_ids") or []),
        linked_decisions=_split_csv(kw.get("linked_decisions", "")),
        linked_handoffs=_split_csv(kw.get("linked_handoffs", "")),
        linked_reviews=_split_csv(kw.get("linked_reviews", "")),
        supersedes=kw.get("supersedes"),
        satisfy_quorum=kw.get("satisfy_quorum"),
        sprint_id=kw.get("sprint_id"),
        stage=kw.get("stage"),
        created_by=kw.get("created_by", "@unknown"),
        owner_user=kw.get("owner_user", "user/local"),
        title=kw.get("title"),
    )
    return str(path)


def record_dispatch_satisfy(**kw: Any) -> str:
    path = dispatch_mod.satisfy_dispatch(
        repo_root=_to_repo_root(kw.get("repo_root")) or Path.cwd(),
        dispatch_id=kw["dispatch_id"],
        by_seat=kw.get("by_seat"),
        rationale=kw.get("rationale"),
    )
    return str(path)


def record_dispatch_supersede(**kw: Any) -> str:
    path = dispatch_mod.supersede_dispatch(
        repo_root=_to_repo_root(kw.get("repo_root")) or Path.cwd(),
        new_id=kw["new_id"],
        old_id=kw["old_id"],
    )
    return str(path)


# ---- 5 prd adapters --------------------------------------------------------


def record_prd(**kw: Any) -> str:
    path = prd_mod.record_prd(
        repo_root=_to_repo_root(kw.get("repo_root")) or Path.cwd(),
        slug=kw["slug"],
        title=kw["title"],
        scope=kw["scope"],
        author=kw.get("author", "@unknown"),
        owner_user=kw.get("owner_user", "user/local"),
        pm_summary=kw.get("pm_summary"),
        linked_msg_ids=list(kw.get("linked_msg_ids") or []),
        linked_decisions=_split_csv(kw.get("linked_decisions", "")),
        cross_repo_prds=_split_csv(kw.get("cross_repo_prds", "")),
    )
    return str(path)


def record_prd_ratify(**kw: Any) -> str:
    path = prd_mod.ratify_prd(
        repo_root=_to_repo_root(kw.get("repo_root")) or Path.cwd(),
        prd_id=kw["prd_id"],
        by_seat=kw["by_seat"],
        rationale=kw.get("rationale"),
    )
    return str(path)


def record_prd_convert(**kw: Any) -> str:
    path = prd_mod.convert_prd(
        repo_root=_to_repo_root(kw.get("repo_root")) or Path.cwd(),
        prd_id=kw["prd_id"],
        by_seat=kw.get("by_seat"),
        rationale=kw.get("rationale"),
    )
    return str(path)


def record_prd_technical_plan_ready(**kw: Any) -> str:
    path = prd_mod.mark_technical_plan_ready(
        repo_root=_to_repo_root(kw.get("repo_root")) or Path.cwd(),
        prd_id=kw["prd_id"],
        technical_plan_url=kw["technical_plan_url"],
        by_seat=kw.get("by_seat"),
        rationale=kw.get("rationale"),
    )
    return str(path)


def record_prd_ship(**kw: Any) -> str:
    path = prd_mod.ship_prd(
        repo_root=_to_repo_root(kw.get("repo_root")) or Path.cwd(),
        prd_id=kw["prd_id"],
        shipped_sha=kw["shipped_sha"],
        by_seat=kw.get("by_seat"),
        rationale=kw.get("rationale"),
    )
    return str(path)


# ---- 3 wip adapters --------------------------------------------------------


def record_wip(**kw: Any) -> str:
    paths_list = _split_csv(kw.get("paths", "")) or []
    if not paths_list:
        raise ValueError("paths must be a non-empty comma-separated list")
    duration = _parse_duration(kw.get("expires", "4h"))
    created_at = _dt.now(_tz.utc).replace(microsecond=0)
    expires_at = created_at + duration
    path = wip_claim_mod.record_wip_claim(
        repo_root=_to_repo_root(kw.get("repo_root")) or Path.cwd(),
        slug=kw["slug"],
        paths=paths_list,
        scope=kw["scope"],
        expires_at=expires_at,
        seat=kw["seat"],
        sprint_id=kw.get("sprint_id"),
        stage=kw.get("stage"),
        linked_msg_ids=_split_csv(kw.get("linked_msg_ids", "")),
        linked_sprints=_split_csv(kw.get("linked_sprints", "")),
        linked_decisions=_split_csv(kw.get("linked_decisions", "")),
        created_at=created_at,
        owner_user=kw.get("owner_user", "user/local"),
        title=kw.get("title"),
    )
    return str(path)


def record_wip_release(**kw: Any) -> str:
    path = wip_claim_mod.release_wip_claim(
        repo_root=_to_repo_root(kw.get("repo_root")) or Path.cwd(),
        claim_id=kw["claim_id"],
        rationale=kw.get("rationale"),
    )
    return str(path)


def record_wip_extend(**kw: Any) -> str:
    duration = _parse_duration(kw["duration"])
    path = wip_claim_mod.extend_wip_claim(
        repo_root=_to_repo_root(kw.get("repo_root")) or Path.cwd(),
        claim_id=kw["claim_id"],
        duration=duration,
    )
    return str(path)


# (cli-subparser-name, mcp-tool-name, adapter-callable, description, kind)
_CHUNK4_BINDINGS: list[tuple[str, str, Any, str, str]] = [
    (
        "record-dispatch",
        "record_dispatch",
        record_dispatch,
        "Write a standing_dispatch entity to docs/dispatches/<id>.md.",
        "transition",
    ),
    (
        "record-dispatch-satisfy",
        "record_dispatch_satisfy",
        record_dispatch_satisfy,
        "Transition a standing_dispatch to status:satisfied.",
        "transition",
    ),
    (
        "record-dispatch-supersede",
        "record_dispatch_supersede",
        record_dispatch_supersede,
        "Mark <old_id> superseded by <new_id> with bidirectional refs.",
        "transition",
    ),
    (
        "record-prd",
        "record_prd",
        record_prd,
        "Write a PRD entity to docs/prds/<id>.md in 'draft' state.",
        "transition",
    ),
    (
        "record-prd-ratify",
        "record_prd_ratify",
        record_prd_ratify,
        "Transition a PRD draft → ratified; stamp ratified_at + ratified_by.",
        "transition",
    ),
    (
        "record-prd-convert",
        "record_prd_convert",
        record_prd_convert,
        "Transition a PRD ratified → converting (technical-plan dispatch fired).",
        "transition",
    ),
    (
        "record-prd-technical-plan-ready",
        "record_prd_technical_plan_ready",
        record_prd_technical_plan_ready,
        "Transition a PRD converting → technical_plan_ready; stamp technical_plan_url.",
        "transition",
    ),
    (
        "record-prd-ship",
        "record_prd_ship",
        record_prd_ship,
        "Transition a PRD technical_plan_ready → shipped (terminal); stamp shipped_sha.",
        "transition",
    ),
    (
        "record-wip",
        "record_wip",
        record_wip,
        "Write a WIP-claim entity to docs/wip/<id>.md.",
        "transition",
    ),
    (
        "record-wip-release",
        "record_wip_release",
        record_wip_release,
        "Transition a WIP-claim to status:released.",
        "transition",
    ),
    (
        "record-wip-extend",
        "record_wip_extend",
        record_wip_extend,
        "Extend a WIP-claim's expires_at by a duration string (e.g. '2h', '30m', '1h30m').",
        "transition",
    ),
]


def chunk4_bindings() -> list[tuple[str, str, Any, str, str]]:
    """Return (cli_name, mcp_name, adapter, description, kind) tuples for the
    chunk-4 transition-verb registration. Consumed by
    `mcp_server.register_chunk4_transition_verbs`.
    """
    return list(_CHUNK4_BINDINGS)
