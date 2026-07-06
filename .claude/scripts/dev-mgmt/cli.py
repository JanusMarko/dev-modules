"""Thin CLI exposing the dev-mgmt entity writers as subcommands.

Invoked from skills (e.g., ``/record-decision``) and from the test suite's
CLI smoke test.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# OBS-G Part 2.2 — venv-aware re-exec (workshop-lite-obs-g-part-2 charter,
# Component B1). When cli.py is invoked under a Python interpreter that is
# NOT under a project ``.venv/`` (e.g. ``python3 .claude/scripts/dev-mgmt/
# cli.py …``), search ancestors of cli.py and cwd for ``.venv/bin/python``
# and re-exec under it so project deps (``pyyaml``, ``pathspec``) resolve.
# Silent no-op when already venv-resident, no venv reachable, or the
# escape env var ``WORKSHOP_LITE_SKIP_VENV_REEXEC`` is set.
# ---------------------------------------------------------------------------

def _running_in_project_venv() -> bool:
    """Return True iff ``sys.executable`` resolves under a ``.venv`` dir."""
    return ".venv" in Path(sys.executable).resolve().parts


def _find_project_venv_python(
    *, here: Path | None = None,
) -> Path | None:
    """Walk from cli.py location upward looking for ``.venv/bin/python``.

    Bounded by the project root: the walk stops once any of three
    root-anchor markers is encountered — ``pyproject.toml`` (the
    pyproject-consumer case), ``.git`` (any git-tracked repo, file or
    dir to cover the worktree case), or ``.claude/`` directly under
    the candidate dir (the workshop-lite-adopted-repo case). This
    closes wl:2026-06-06-08 finding F2: in a non-pyproject consumer
    (e.g. antigravity-expert pre-fix), the walk previously leaked
    past the repo root in search of pyproject.toml and could resolve
    to an unrelated parent-directory venv. Returns the first hit;
    None if no project venv is reachable within the project boundary.
    """
    here = (here or Path(__file__).resolve())
    for d in (here.parent, *here.parent.parents):
        candidate = d / ".venv" / "bin" / "python"
        if candidate.is_file():
            return candidate.resolve()
        if (d / "pyproject.toml").is_file():
            break
        if (d / ".git").exists():
            break
        if (d / ".claude").is_dir():
            break
    return None


def _maybe_reexec_via_venv() -> None:
    """OBS-G Part 2.2 fix: route bare-``python3`` invocations through ``.venv``.

    ``os.execv`` swaps the running interpreter so the rest of cli.py loads
    under the project venv where deps are installed. No-op when already
    inside a venv, when the escape env var is set, or when no project
    ``.venv`` is reachable (operator's responsibility in that case — the
    A-side missing-dep guard surfaces the bootstrap instructions).
    """
    if os.environ.get("WORKSHOP_LITE_SKIP_VENV_REEXEC"):
        return
    if _running_in_project_venv():
        return
    venv_python = _find_project_venv_python()
    if venv_python is None:
        return
    current = Path(sys.executable).resolve()
    if venv_python == current:
        return
    os.execv(str(venv_python), [str(venv_python), *sys.argv])


_maybe_reexec_via_venv()


import argparse  # noqa: E402
import json  # noqa: E402

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

# WL.29 D1: state-digest CLI subcommand factors `state_digest.render_digest`
# from `.claude/hooks/state_digest.py`. Add the hooks dir to sys.path so the
# module is importable from cli.py.
_HOOKS_DIR = _HERE.parent.parent / "hooks"
if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))


def _emit_missing_dep_instructions(exc: ImportError) -> None:
    """OBS-G Part 2.1 fix: actionable bootstrap instructions on ImportError.

    When the re-exec path could not engage (no ``.venv`` reachable) AND a
    project dep is missing, surface a clear ``pip install -e .`` step
    rooted at the discovered project root instead of a raw
    ``ModuleNotFoundError``.
    """
    # Walk up from cli.py (.claude/scripts/dev-mgmt/) to find the project
    # root (the dir containing pyproject.toml). Fall back to cwd if we
    # cannot infer it.
    project_root: Path = Path.cwd().resolve()
    for d in (_HERE, *_HERE.parents):
        if (d / "pyproject.toml").is_file():
            project_root = d
            break
    name = getattr(exc, "name", None) or str(exc)
    sys.stderr.write(
        f"workshop-lite cli.py: missing dependency {name!r}.\n"
        f"\n"
        f"This usually means the workshop-lite substrate was adopted into "
        f"this repo but `pip install -e .` was never run.\n"
        f"\n"
        f"From {project_root}:\n"
        f"\n"
        f"    python3 -m venv .venv\n"
        f"    .venv/bin/pip install -e .\n"
        f"\n"
        f"Then retry — cli.py auto-detects an adjacent ``.venv`` and "
        f"re-execs under it (so plain `python3 .claude/scripts/dev-mgmt/"
        f"cli.py …` will work).\n"
    )


try:
    import codex_host_content as codex_host_content_mod  # noqa: E402
    import workshop_lite_content as workshop_lite_content_mod  # noqa: E402
    import workshop_lite_pack as workshop_lite_pack_mod  # noqa: E402
    import consult as consult_mod  # noqa: E402
    import consult_context  # noqa: E402
    import dispatch as dispatch_mod  # noqa: E402
    import entities  # noqa: E402
    import index  # noqa: E402
    import ledger_paths  # noqa: E402
    import pending_views  # noqa: E402
    import prd as prd_mod  # noqa: E402
    import sprint_state as sprint_state_mod  # noqa: E402
    import state_digest as state_digest_mod  # noqa: E402
    import validate as validate_mod  # noqa: E402
    import validators  # noqa: E402
    import wip_claim as wip_claim_mod  # noqa: E402
except ImportError as _exc:
    _emit_missing_dep_instructions(_exc)
    sys.exit(2)


_REINDEX_KINDS: dict[str, tuple[str, str, str, object]] = {
    "decisions":     ("docs/decisions",     "Decisions",     "default", "DECISION_COLUMNS"),
    "sprints":       ("docs/sprints",       "Sprints",       "sprint",  "SPRINT_COLUMNS"),
    "handoffs":      ("docs/handoffs",      "Handoffs",      "default", "HANDOFF_COLUMNS"),
    "issues":        ("docs/issues",        "Issues",        "default", "ISSUE_COLUMNS"),
    "reviews":       ("docs/reviews",       "Reviews",       "default", "REVIEW_COLUMNS"),
    "conversations": ("docs/conversations", "Conversations", "default", "CONVERSATION_COLUMNS"),
    "wip":           ("docs/wip",           "WIP-claims",    "wip",     "WIP_CLAIM_COLUMNS"),
    "dispatches":    ("docs/dispatches",    "Standing-dispatches", "dispatch", None),
    # PRD (charter docs/inbox/2026-06-02-prd-entity-cross-repo-pm-bridge-
    # charter.md): bespoke multi-section INDEX (5 state groups, sorted
    # by created_at ASC within each). Delegates to prd_mod renderer.
    "prds":          ("docs/prds",          "PRDs",          "prd",     None),
}


def _install_codex_mcp_block(
    cfg_path: Path, wl_bin: Path, *, approval_mode: str = "approve",
) -> tuple[str, str]:
    """Compute the desired .codex/config.toml text + action for the canonical
    [mcp_servers.workshop_lite] block. Idempotent across the four states:

      - file absent → action="create-file", text = canonical block only
      - file present, block absent → action="append-block", text = existing + block
      - file present, block present, approval-mode line absent → action=
        "insert-approval-line", text = existing with approval line inserted
        directly after the block's `command = ...` line
      - file present, block present, approval-mode line present → action="noop",
        text = existing (caller skips the write)

    Block emitted on create / append:

        # workshop-lite MCP server entry point (wl-mcp shim).
        # Installed by `wl install-codex-mcp-block`.
        [mcp_servers.workshop_lite]
        command = "<wl_bin>"
        default_tools_approval_mode = "<approval_mode>"

    The function never reads/parses TOML — string-anchored detection is
    sufficient because the block shape is canonical + every consumer's
    config.toml that has the block uses the same `[mcp_servers.workshop_lite]`
    header. Closes wl:2026-06-07 ask-2b (@user msg-794a58e6569a).
    """
    header = "[mcp_servers.workshop_lite]"
    approval_key = "default_tools_approval_mode"
    block_lines = [
        "# workshop-lite MCP server entry point (wl-mcp shim).",
        "# Installed by `wl install-codex-mcp-block` "
        "(wl:2026-06-07 ask-2b durable entry-point).",
        header,
        f'command = "{wl_bin}"',
        f'{approval_key} = "{approval_mode}"',
    ]
    canonical_block = "\n".join(block_lines) + "\n"

    if not cfg_path.exists():
        return canonical_block, "create-file"

    existing = cfg_path.read_text(encoding="utf-8")
    lines = existing.split("\n")

    header_idx = None
    for i, ln in enumerate(lines):
        if ln.strip() == header:
            header_idx = i
            break

    if header_idx is None:
        if not existing:
            return canonical_block, "append-block"
        # Ensure exactly one blank line between previous content and the
        # new block for canonical TOML style.
        return existing.rstrip("\n") + "\n\n" + canonical_block, "append-block"

    # Block exists — scan forward to next section header or EOF to find
    # the block's content range, then check for approval line + command line.
    block_end = len(lines)
    for j in range(header_idx + 1, len(lines)):
        s = lines[j].strip()
        if s.startswith("[") and s.endswith("]"):
            block_end = j
            break

    block_body = lines[header_idx + 1:block_end]
    has_approval = any(
        ln.strip().startswith(approval_key + " ") or
        ln.strip().startswith(approval_key + "=")
        for ln in block_body
    )
    if has_approval:
        return existing, "noop"

    # Find the command line within the block to anchor the insertion.
    cmd_offset = None
    for k, ln in enumerate(block_body):
        if ln.strip().startswith("command ") or ln.strip().startswith("command="):
            cmd_offset = k
            break
    insert_at = (header_idx + 1 + cmd_offset + 1) if cmd_offset is not None else (header_idx + 1)
    new_lines = (
        lines[:insert_at]
        + [f'{approval_key} = "{approval_mode}"']
        + lines[insert_at:]
    )
    return "\n".join(new_lines), "insert-approval-line"


def _do_reindex(kind: str, repo_root: Path) -> bool:
    """Re-render a single INDEX.md. Returns True on success, False if dir absent.

    The ``sprints`` kind uses the special ``index.sprint_paths`` scanner since
    sprint folders live in ``active/`` + ``archive/`` subdirs, not as flat
    ``*.md`` files.
    """
    if kind not in _REINDEX_KINDS:
        raise ValueError(f"unknown kind: {kind!r}")
    _rel_dir, title, scanner_kind, columns_name = _REINDEX_KINDS[kind]
    target_dir = (
        ledger_paths.compat_sprints_dir(repo_root)
        if kind == "sprints"
        else ledger_paths.compat_kind_dir(repo_root, kind)
    )
    if not target_dir.exists():
        return False
    if scanner_kind == "wip":
        # WIP-claim has a bespoke §8 INDEX shape (two-section list with
        # active / closed (trailing Nd) + rolling-collapse), not a flat
        # markdown table. Delegate to the wip_claim module's renderer.
        wip_claim_mod._render_wip_index(target_dir)
        return True
    if scanner_kind == "dispatch":
        # Standing-dispatch has a bespoke §8 INDEX shape (multi-section
        # markdown table with Standing / Satisfied (trailing Nd) /
        # Superseded / Expired). Delegate to the dispatch module's
        # renderer.
        dispatch_mod._render_dispatch_index(target_dir)
        return True
    if scanner_kind == "prd":
        # PRD has a bespoke 5-state INDEX shape (Draft / Ratified /
        # Converting / Technical-plan-ready / Shipped). Delegate to the
        # prd module's renderer.
        prd_mod._render_prd_index(target_dir)
        return True
    if kind == "handoffs":
        # Phase 1 Cycle 2 (wl-rearch §4.6): route through the rolling-
        # collapse aware renderer. Config-OFF (default) delegates back
        # to the classical flat-table path — no behavior change.
        index.render_handoffs_index_with_rolling_collapse(repo_root=repo_root)
        return True
    columns_obj = getattr(index, str(columns_name), None)
    if columns_obj is None:
        columns_obj = getattr(wip_claim_mod, str(columns_name))
    scanner = index.sprint_paths if scanner_kind == "sprint" else None
    # wl:2026-06-05-01: decisions + reviews use CURATED rendering (cohort D D2
    # par:2026-06-04-13; auto-rotation + INDEX-archive.md). Match the writer
    # path used by record_decision/record_review so re-index is idempotent
    # vs an entity-record refresh of the same INDEX.
    if kind == "decisions":
        index.render_curated(
            target_dir, title=title, columns=columns_obj,
            exclude_patterns=("*.canonical.md",),
            preserve_manual_rows=True,
        )
        return True
    if kind == "reviews":
        index.render_curated(
            target_dir, title=title, columns=columns_obj,
            preserve_manual_rows=True,
        )
        return True
    index.render(target_dir, title=title, columns=columns_obj, scanner=scanner)
    return True


def _split_csv(value: str) -> list[str] | None:
    if not value:
        return None
    return [p.strip() for p in value.split(",") if p.strip()] or None


_DURATION_RE = __import__("re").compile(
    r"^(?:(\d+)h)?(?:(\d+)m)?$"
)


def _parse_duration(value: str):
    """Parse ``Xh`` / ``Xm`` / ``XhYm`` into a ``timedelta``. Raises
    ``ValueError`` on a malformed string.
    """
    from datetime import timedelta
    if not value:
        raise ValueError("duration must be non-empty")
    m = _DURATION_RE.match(value.strip())
    if not m or (m.group(1) is None and m.group(2) is None):
        raise ValueError(
            f"duration must be Xh, Xm, or XhYm (got: {value!r})"
        )
    hours = int(m.group(1) or 0)
    minutes = int(m.group(2) or 0)
    return timedelta(hours=hours, minutes=minutes)


def _maybe_run_end_sprint_gate(
    repo_root: Path, sprint_id: str,
) -> str | None:
    """Run the /end-sprint spec.yaml gate per sub-spec §4.2.

    Returns ``None`` when the gate passes (either no spec.yaml present,
    or sprint_kind has ``gate_at_end=False``, or no strict warnings).
    Returns the formatted warning block as a string when the gate fails
    (caller writes to stderr + aborts).

    Per §4.2 + §8.2:

    - kris-binding: any V3/V6 strict warning ABORTS.
    - autonomous-arc: INFO-log only (returns None even with warnings).
    - routine: no gate (returns None).
    """
    import sprint_spec as _sprint_spec_mod
    spec_path = (
        ledger_paths.compat_sprints_dir(repo_root) / "active"
        / f"sprint-{sprint_id}" / "spec.yaml"
    )
    if not spec_path.is_file():
        return None  # no spec.yaml; legacy behavior
    spec, parse_errors = _sprint_spec_mod.load_spec_yaml(spec_path)
    if spec is None:
        # Schema-busted spec.yaml is itself a strict error per V1; run
        # the full check to report it.
        warnings = validate_mod.run_checks(
            repo_root,
            only_check="sprint-specs",
            end_sprint_id=sprint_id,
        )
        strict = validate_mod.strict_exit_warnings(warnings)
        if strict:
            return validate_mod.format_warnings(warnings)
        return None
    sprint_kind = spec.get("sprint_kind")
    kinds = _sprint_spec_mod._registered_kinds(repo_root)
    kind_info = kinds.get(sprint_kind) if isinstance(sprint_kind, str) else None
    gate_at_end = bool(kind_info.get("gate_at_end", False)) if kind_info else False
    if not gate_at_end:
        # autonomous-arc / routine / unknown-kind: INFO-log only, never abort.
        # Still surface the warnings on stderr for visibility but return None.
        warnings = validate_mod.run_checks(
            repo_root,
            only_check="sprint-specs",
            end_sprint_id=sprint_id,
        )
        if warnings:
            sys.stderr.write(
                f"[end-sprint INFO] spec.yaml gate not enforced for "
                f"sprint_kind={sprint_kind!r} (gate_at_end=False); "
                f"surfacing advisory warnings:\n"
            )
            sys.stderr.write(validate_mod.format_warnings(warnings))
        return None
    warnings = validate_mod.run_checks(
        repo_root,
        only_check="sprint-specs",
        end_sprint_id=sprint_id,
    )
    strict = validate_mod.strict_exit_warnings(warnings)
    if strict:
        return validate_mod.format_warnings(warnings)
    return None


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dev-mgmt")
    sub = parser.add_subparsers(dest="command", required=True)

    rd = sub.add_parser(
        "record-decision",
        help="Write a Decision entity to docs/decisions/<id>.md",
    )
    rd.add_argument("--title", required=True)
    rd.add_argument("--rationale", required=True)
    rd.add_argument("--scope", required=True,
                    help='e.g. "design:LIGHTWEIGHT-DEV-MGMT-SYSTEM" or "sprint:dev-mgmt.1"')
    rd.add_argument("--options-json", required=True,
                    help='JSON array of {label, chosen, reasoning} objects')
    rd.add_argument("--author", required=True, help='e.g. "@plan"')
    rd.add_argument("--authored-with", default="",
                    help="Comma-separated co-author @ids")
    rd.add_argument("--linked-decisions", default="",
                    help="Comma-separated decision ids (cross-cutting peer "
                         "decisions)")
    rd.add_argument("--linked-reviews", default="",
                    help="Comma-separated review ids (reviews that informed "
                         "this decision)")
    rd.add_argument("--linked-msg-ids", default="",
                    help="Comma-separated parley msg-IDs")
    rd.add_argument("--affects", default=None,
                    help="Content for the '## What this affects' body "
                         "section (replaces the '(not yet specified)' "
                         "placeholder)")
    rd.add_argument("--sprint-id", default=None)
    rd.add_argument("--stage", default=None, choices=[None, "plan", "execute", "retro"])
    rd.add_argument("--supersedes", default=None)
    rd.add_argument("--status", default="accepted",
                    choices=["accepted", "rejected", "superseded", "open"])
    rd.add_argument("--repo-root", default=None,
                    help="Defaults to current working directory")

    ss = sub.add_parser(
        "start-sprint",
        help="Scaffold docs/sprints/active/sprint-<id>/ for a new sprint",
    )
    ss.add_argument("--sprint-id", required=True,
                    help='e.g. "dev-mgmt.2"')
    ss.add_argument("--title", required=True)
    ss.add_argument("--author", required=True, help='e.g. "@plan"')
    ss.add_argument("--from-plan", default=None,
                    help="Path to an approved plan-mode plan file to use as plan.md body")
    ss.add_argument("--linked-design-docs", default="",
                    help="Comma-separated design-doc references")
    ss.add_argument("--spec", default=None,
                    help="Phase 3 (sub-spec §8.1): create an initial "
                         "spec.yaml with role-kind defaults. Pass one of "
                         "{kris-binding, autonomous-arc, routine} or a "
                         "per-repo registered kind. Omitted: legacy "
                         "behavior (no spec.yaml created).")
    ss.add_argument("--spec-has-user-journey", action="store_true",
                    help="Set has_user_journey: true in the scaffolded "
                         "spec.yaml (auto-upgrades golden_path_verifier "
                         "to required: true per sub-spec §3.3). No effect "
                         "without --spec.")
    ss.add_argument("--spec-charter-ref", default="",
                    help="Comma-separated charter_ref entries to seed the "
                         "spec.yaml (markdown path or parley://charters/<id> "
                         "URI). No effect without --spec.")
    ss.add_argument("--force", action="store_true",
                    help="Overwrite plan.md if it already exists")
    ss.add_argument("--repo-root", default=None,
                    help="Defaults to current working directory")

    es = sub.add_parser(
        "end-sprint",
        help="Write retro.md (if absent), archive the sprint folder, re-INDEX",
    )
    es.add_argument("--sprint-id", required=True)
    es.add_argument("--author", required=True)
    es.add_argument("--retro-title", default=None,
                    help="Title for retro.md; defaults to 'sprint-<id> retrospective'")
    es.add_argument("--retro-body-path", default=None,
                    help="Optional path to a file whose content becomes retro.md body")
    es.add_argument("--test-results-json", default=None,
                    help="JSON object with passed/skipped/xfailed/xpassed/failed counts")
    es.add_argument("--linked-decisions", default="",
                    help="Comma-separated decision ids")
    es.add_argument("--linked-reviews", default="",
                    help="Comma-separated review ids")
    es.add_argument("--force", action="store_true",
                    help="Overwrite retro.md if it already exists")
    es.add_argument("--repo-root", default=None,
                    help="Defaults to current working directory")

    hd = sub.add_parser(
        "handoff",
        help="Write a Handoff entity to docs/handoffs/<YYYY-MM-DD-HHMM>-<slug>.md",
    )
    hd.add_argument("--title", required=True)
    hd.add_argument("--topic", required=True,
                    help="Short free-form identifier; slugified for the filename")
    hd.add_argument("--author", required=True, help='e.g. "@work"')
    hd.add_argument("--trigger", default="manual",
                    choices=["manual", "pre_compact", "session_end"])
    hd.add_argument("--sprint-id", default=None,
                    help="Set if there is an active sprint; must be paired with --stage")
    hd.add_argument("--stage", default=None, choices=[None, "plan", "execute", "retro"],
                    help="Must be paired with --sprint-id")
    hd.add_argument("--since-handoff-id", default=None,
                    help="ID of the prior handoff (cursor for 'since last handoff')")
    hd.add_argument("--since-msg-id", default=None,
                    help="Parley msg-id cursor; populated by the caller, not the lib")
    hd.add_argument("--body", default=None,
                    help="Inline markdown body; takes precedence over --body-from-file")
    hd.add_argument("--body-from-file", default=None,
                    help="Path to a file whose content becomes the handoff body")
    hd.add_argument("--linked-decisions", default="",
                    help="Comma-separated decision ids")
    hd.add_argument("--linked-issues", default="",
                    help="Comma-separated issue ids")
    hd.add_argument("--linked-tasks", default="",
                    help="Comma-separated task ids")
    hd.add_argument("--linked-msg-ids", default="",
                    help="Comma-separated parley msg-IDs")
    hd.add_argument("--next-action", default=None,
                    help="One-sentence resume hint for the next reader")
    hd.add_argument("--repo-root", default=None,
                    help="Defaults to current working directory")

    ri = sub.add_parser(
        "record-issue",
        help="Write an Issue entity to docs/issues/<YYYY-MM-DD-NN>-<slug>.md",
    )
    ri.add_argument("--title", required=True)
    ri.add_argument("--severity", required=True,
                    choices=["high", "medium", "low"])
    ri.add_argument("--scope", required=True,
                    help='e.g. "repo:dev-mgmt-lib" or "sprint:dev-mgmt.4" or "design:<doc>"')
    ri.add_argument("--reporter", required=True, help='e.g. "@work"')
    ri.add_argument("--status", default="open",
                    choices=["open", "investigating", "resolved", "wontfix"])
    ri.add_argument("--sprint-id", default=None,
                    help="Set if scope=sprint:<id>; must be paired with --stage")
    ri.add_argument("--stage", default=None, choices=[None, "plan", "execute", "retro"],
                    help="Must be paired with --sprint-id")
    ri.add_argument("--class", default=None, dest="klass",
                    help="Optional free-form per-repo taxonomy string (D12)")
    ri.add_argument("--body", default=None,
                    help="Inline markdown body; takes precedence over --body-from-file")
    ri.add_argument("--body-from-file", default=None,
                    help="Path to a file whose content becomes the issue body")
    ri.add_argument("--linked-decisions", default="",
                    help="Comma-separated decision ids")
    ri.add_argument("--linked-reviews", default="",
                    help="Comma-separated review ids")
    ri.add_argument("--linked-msg-ids", default="",
                    help="Comma-separated parley msg-IDs")
    ri.add_argument("--repo-root", default=None,
                    help="Defaults to current working directory")

    rv = sub.add_parser(
        "record-review",
        help="Write a Review entity to docs/reviews/<YYYY-MM-DD-NN>-<slug>.md",
    )
    rv.add_argument("--title", required=True)
    rv.add_argument("--review-type", required=True,
                    choices=["adversarial", "collaborative", "synthesis",
                             "research", "cross-check-resolution"])
    rv.add_argument("--accurate-trail-json", default=None,
                    help="Sprint S-B D1=A: REQUIRED for "
                         "--review-type cross-check-resolution — the "
                         "mandatory structured 4.6f accurate-trail "
                         "(adjudications-both-ways / scrum-master-own-"
                         "errors / dual-independent-verdicts); JSON "
                         "object or array, validator-enforced non-empty")
    rv.add_argument("--scope", required=True,
                    help='e.g. "sprint:dev-mgmt.4" or "repo:<area>" or "design:<doc>"')
    rv.add_argument("--author", required=True, help='e.g. "@plan"')
    rv.add_argument("--status", default="completed",
                    choices=["in_progress", "completed"])
    rv.add_argument("--sprint-id", default=None,
                    help="Set if scope=sprint:<id>; must be paired with --stage")
    rv.add_argument("--stage", default=None, choices=[None, "plan", "execute", "retro"],
                    help="Must be paired with --sprint-id")
    rv.add_argument("--findings-json", default="[]",
                    help='JSON array of finding objects; each requires '
                         '{severity (high|medium|low), summary}; extra keys allowed')
    rv.add_argument("--body", default=None,
                    help="Inline markdown body; takes precedence over --body-from-file")
    rv.add_argument("--body-from-file", default=None,
                    help="Path to a file whose content becomes the review body")
    rv.add_argument("--linked-decisions", default="",
                    help="Comma-separated decision ids")
    rv.add_argument("--linked-reviews", default="",
                    help="Comma-separated review ids (e.g. prior audits in "
                         "an audit-series continuation)")
    rv.add_argument("--linked-msg-ids", default="",
                    help="Comma-separated parley msg-IDs")
    rv.add_argument("--repo-root", default=None,
                    help="Defaults to current working directory")

    at = sub.add_parser(
        "add-task",
        help="Append a task line to docs/sprints/.../sprint-<id>/tasks.md (D19-D21)",
    )
    at.add_argument("--sprint-id", required=True, help='e.g. "dev-mgmt.5"')
    at.add_argument("--description", required=True,
                    help="Free-form task description (must be non-empty)")
    at.add_argument("--assignee", default=None, help='e.g. "@work"')
    at.add_argument("--status", default="created",
                    choices=["created", "picked-up", "in-progress",
                             "verified", "done", "cleaned-up"],
                    help="R6 task status (spec §2.3 / §11). Checkbox derived: "
                         "[ ]=created/picked-up, [~]=in-progress/verified, "
                         "[x]=done/cleaned-up. Legacy v1 values "
                         "(pending/in_progress/completed/blocked) are accepted "
                         "by the parser and mapped on read; run migrate-tasks "
                         "to canonicalize on-disk files.")
    at.add_argument("--linked-issues", default="",
                    help="Comma-separated issue ids")
    at.add_argument("--linked-decisions", default="",
                    help="Comma-separated decision ids")
    at.add_argument("--repo-root", default=None,
                    help="Defaults to current working directory")

    cc = sub.add_parser(
        "capture-conversation",
        help="Write a Conversation entity to docs/conversations/<YYYY-MM-DD-NN>-<slug>.md",
    )
    cc.add_argument("--title", required=True)
    cc.add_argument("--topic", required=True,
                    help="Short slug for the filename")
    cc.add_argument("--participants", default=None,
                    help='Comma-separated @ids (e.g., "@work,@plan"); '
                         "auto-derived from records in records-json mode if omitted (D24)")
    cc.add_argument("--zone", default=None,
                    choices=["sprint", "cross-sprint", "pre-sprint"],
                    help="Defaults to 'sprint' if an active sprint folder is "
                         "present in repo_root, else 'cross-sprint' (D25)")
    cc.add_argument("--sprint-id", default=None,
                    help="Required if zone=sprint")
    cc.add_argument("--stage", default=None, choices=[None, "plan", "execute", "retro"],
                    help="Required if zone=sprint")
    cc.add_argument("--started-at", default=None,
                    help="ISO timestamp of first record (auto-filled in records-json mode)")
    cc.add_argument("--ended-at", default=None,
                    help="ISO timestamp of last record (auto-filled in records-json mode)")
    cc.add_argument("--verbatim", default=None,
                    help="Inline pre-rendered verbatim chat markdown")
    cc.add_argument("--verbatim-from-file", default=None,
                    help="Path to pre-rendered verbatim chat markdown")
    cc.add_argument("--verbatim-from-stdin", action="store_true",
                    help="Read pre-rendered verbatim chat markdown from stdin")
    cc.add_argument("--verbatim-records-json-from-stdin", action="store_true",
                    help="Read parley get --json output from stdin; render + "
                         "auto-fill msg_range/started_at/ended_at (D27 dict-processor)")
    cc.add_argument("--verbatim-msg-range", default=None,
                    help='Comma-separated "msg-first,msg-last"; required in '
                         "non-records modes (or pass empty for [null, null])")
    cc.add_argument("--body", default=None,
                    help="Inline curated-summary markdown; takes precedence over --body-from-file")
    cc.add_argument("--body-from-file", default=None,
                    help="Path to curated-summary markdown body")
    cc.add_argument("--linked-design-docs", default="")
    cc.add_argument("--linked-decisions", default="")
    cc.add_argument("--linked-reviews", default="")
    cc.add_argument("--linked-issues", default="")
    cc.add_argument("--linked-handoffs", default="")
    cc.add_argument("--linked-msg-ids", default="")
    cc.add_argument("--repo-root", default=None,
                    help="Defaults to current working directory")

    rw = sub.add_parser(
        "record-wip",
        help="Write a WIP-claim entity to docs/wip/<id>.md "
             "(sub-spec docs/design/2026-05-29-wl-wip-claim-spec.md)",
    )
    rw.add_argument("--slug", required=True,
                    help="Short slug for the claim (combined with date/seat "
                         "to form the filename)")
    rw.add_argument("--seat", required=True,
                    help='FQID member id (e.g. "wl-rearch:wl-plan"); the '
                         "skill layer derives this from `parley whoami`")
    rw.add_argument("--paths", required=True,
                    help="Comma-separated repo-relative paths the seat is "
                         "mid-work on (non-empty per sub-spec §3)")
    rw.add_argument("--scope", required=True,
                    help='e.g. "arc:wl-rearch" or "sprint:<id>" or "repo:<area>"')
    rw.add_argument("--expires", default="4h",
                    help="Duration from now; default 4h (Q-WL-3 resolution). "
                         'Format: "<int>h" or "<int>m" or "<int>h<int>m".')
    rw.add_argument("--sprint-id", default=None,
                    help="Set if scope=sprint:<id>; must be paired with --stage")
    rw.add_argument("--stage", default=None,
                    choices=[None, "plan", "execute", "retro"],
                    help="Must be paired with --sprint-id")
    rw.add_argument("--linked-msg-ids", default="",
                    help="Comma-separated parley msg-IDs that authorized the work")
    rw.add_argument("--linked-decisions", default="",
                    help="Comma-separated decision ids")
    rw.add_argument("--linked-sprints", default="",
                    help="Comma-separated sprint ids")
    rw.add_argument("--owner-user", default="user/local",
                    help='Per D-RA-4; defaults "user/local"')
    rw.add_argument("--title", default=None,
                    help="Optional human-readable title (default derives "
                         "from seat + slug)")
    rw.add_argument("--repo-root", default=None,
                    help="Defaults to current working directory")

    rwr = sub.add_parser(
        "record-wip-release",
        help="Transition a WIP-claim to status:released",
    )
    rwr.add_argument("claim_id", help="The claim id (file stem under docs/wip/)")
    rwr.add_argument("--rationale", default=None,
                     help="Optional short rationale for the release")
    rwr.add_argument("--repo-root", default=None,
                     help="Defaults to current working directory")

    rwe = sub.add_parser(
        "record-wip-extend",
        help="Extend a WIP-claim's expires_at by duration",
    )
    rwe.add_argument("claim_id", help="The claim id (file stem under docs/wip/)")
    rwe.add_argument("duration",
                     help='Duration to extend by, e.g. "2h" or "30m" or "1h30m"')
    rwe.add_argument("--repo-root", default=None,
                     help="Defaults to current working directory")

    rds = sub.add_parser(
        "record-dispatch",
        help="Write a standing_dispatch entity to docs/dispatches/<id>.md "
             "(sub-spec docs/design/2026-05-29-wl-standing-dispatch-spec.md)",
    )
    rds.add_argument("--slug", required=True,
                     help="Short slug (combined with date+NN to form id)")
    rds.add_argument("--purpose", required=True,
                     choices=["charter", "brief", "governance",
                              "routing", "other"],
                     help="Dispatch purpose enum (sub-spec §3)")
    rds.add_argument("--recipients", required=True,
                     help="Comma-separated FQID list (D-RA-4); multi-recipient "
                          "by construction per D-WL-19 element 1")
    rds.add_argument("--expected", required=True, dest="expected_outcome",
                     help="Free-text expected outcome (what counts as satisfied)")
    rds.add_argument("--scope", required=True,
                     help='e.g. "arc:wl-rearch" / "sprint:<id>" / "repo:<area>"')
    rds.add_argument("--deadline", default=None,
                     help='ISO timestamp (e.g. "2026-06-02T18:00:00Z"); '
                          'process signal — INFO-only validator surface')
    rds.add_argument("--expires-at", default=None, dest="expires_at",
                     help='ISO timestamp; structural — WARN past 24h grace')
    rds.add_argument("--linked-msg-id", action="append", default=None,
                     dest="linked_msg_ids",
                     help="Repeatable; the parley msgs carrying this dispatch")
    rds.add_argument("--linked-decisions", default="",
                     help="Comma-separated decision ids")
    rds.add_argument("--linked-handoffs", default="",
                     help="Comma-separated handoff ids")
    rds.add_argument("--linked-reviews", default="",
                     help="Comma-separated review ids")
    rds.add_argument("--supersedes", default=None,
                     help="Prior dispatch id this replaces (bidirectional "
                          "supersedes ref auto-added; prior flipped to "
                          "status: superseded)")
    rds.add_argument("--satisfy-quorum", type=int, default=None,
                     dest="satisfy_quorum",
                     help="Integer N; when N recipients ack, validator fires "
                          "V5-QUORUM (sub-spec Q-SD-3)")
    rds.add_argument("--sprint-id", default=None)
    rds.add_argument("--stage", default=None,
                     choices=[None, "plan", "execute", "retro"])
    rds.add_argument("--created-by", default="@unknown",
                     help='Author FQID (e.g. "@wl-plan"); skill layer derives '
                          'via parley whoami')
    rds.add_argument("--owner-user", default="user/local",
                     help='Per D-RA-4; defaults "user/local"')
    rds.add_argument("--title", default=None,
                     help="Optional human-readable title (default derives "
                          "from purpose + slug)")
    rds.add_argument("--repo-root", default=None,
                     help="Defaults to current working directory")

    rds_sat = sub.add_parser(
        "record-dispatch-satisfy",
        help="Transition a standing_dispatch to status:satisfied",
    )
    rds_sat.add_argument("dispatch_id",
                         help="The dispatch id (file stem under docs/dispatches/)")
    rds_sat.add_argument("--by", default=None, dest="by_seat",
                         help="FQID of the seat that satisfied (frontmatter "
                              "field 'satisfied_by')")
    rds_sat.add_argument("--rationale", default=None,
                         help="Optional short rationale captured in the "
                              "transition log")
    rds_sat.add_argument("--repo-root", default=None,
                         help="Defaults to current working directory")

    rds_sup = sub.add_parser(
        "record-dispatch-supersede",
        help="Mark <old_id> superseded by <new_id> with bidirectional refs",
    )
    rds_sup.add_argument("new_id",
                         help="The id of the new (superseding) dispatch — "
                              "must already exist under docs/dispatches/")
    rds_sup.add_argument("old_id",
                         help="The id of the prior dispatch being superseded")
    rds_sup.add_argument("--repo-root", default=None,
                         help="Defaults to current working directory")

    # PRD (charter docs/inbox/2026-06-02-prd-entity-cross-repo-pm-bridge-
    # charter.md): 5 subcommands per chunk-0 open-Q ratify —
    # record-prd (create draft) + 4 state-transition verbs (ratify /
    # convert / technical-plan-ready / ship).
    rpd = sub.add_parser(
        "record-prd",
        help="Write a PRD entity to docs/prds/<id>.md in 'draft' state "
             "(charter docs/inbox/2026-06-02-prd-entity-cross-repo-pm-"
             "bridge-charter.md)",
    )
    rpd.add_argument("--slug", required=True,
                     help="Short slug (combined with date+NN to form id)")
    rpd.add_argument("--title", required=True,
                     help="Human-readable PRD title")
    rpd.add_argument("--scope", required=True,
                     help='e.g. "arc:<id>" / "sprint:<id>" / "repo:<area>" '
                          '/ "design:<doc>" / "decision:<id>"')
    rpd.add_argument("--pm-summary", default=None, dest="pm_summary",
                     help="Initial body text for the REQUIRED '## PM Summary' "
                          "section (charter AXIS-12); template default used "
                          "if omitted")
    rpd.add_argument("--linked-msg-id", action="append", default=None,
                     dest="linked_msg_ids",
                     help="Repeatable; parley msg-ids carrying the PM "
                          "requirement")
    rpd.add_argument("--linked-decisions", default="",
                     help="Comma-separated decision ids")
    rpd.add_argument("--cross-repo-prds", default="", dest="cross_repo_prds",
                     help="Comma-separated <repo>:<id> refs per charter "
                          "AXIS-13 + par-p0-defect-56 multi-repo convention")
    rpd.add_argument("--author", default="@unknown",
                     help='Author FQID (e.g. "@pm-jane"); skill layer derives '
                          'via parley whoami')
    rpd.add_argument("--owner-user", default="user/local",
                     help='Per D-RA-4; defaults "user/local"')
    rpd.add_argument("--repo-root", default=None,
                     help="Defaults to current working directory")

    rpd_rat = sub.add_parser(
        "record-prd-ratify",
        help="Transition a PRD from state:draft to state:ratified; stamp "
             "ratified_at + ratified_by (charter §2.2)",
    )
    rpd_rat.add_argument("prd_id",
                         help="The PRD id (file stem under docs/prds/)")
    rpd_rat.add_argument("--by", required=True, dest="by_seat",
                         help="FQID of the seat ratifying (CTO / scrum-master "
                              "per charter §2.2)")
    rpd_rat.add_argument("--rationale", default=None,
                         help="Optional short rationale captured in the "
                              "transition log")
    rpd_rat.add_argument("--repo-root", default=None,
                         help="Defaults to current working directory")

    rpd_conv = sub.add_parser(
        "record-prd-convert",
        help="Transition a PRD from state:ratified to state:converting "
             "(technical-plan dispatch fired)",
    )
    rpd_conv.add_argument("prd_id",
                          help="The PRD id (file stem under docs/prds/)")
    rpd_conv.add_argument("--by", default=None, dest="by_seat",
                          help="Optional FQID of the seat converting")
    rpd_conv.add_argument("--rationale", default=None,
                          help="Optional short rationale captured in the "
                               "transition log")
    rpd_conv.add_argument("--repo-root", default=None,
                          help="Defaults to current working directory")

    rpd_tpr = sub.add_parser(
        "record-prd-technical-plan-ready",
        help="Transition a PRD from state:converting to state:"
             "technical_plan_ready; stamp technical_plan_url (charter §2.2)",
    )
    rpd_tpr.add_argument("prd_id",
                         help="The PRD id (file stem under docs/prds/)")
    rpd_tpr.add_argument("--technical-plan-url", required=True,
                         dest="technical_plan_url",
                         help="URL to the technical plan artifact (sprint "
                              "plan / design doc / external link)")
    rpd_tpr.add_argument("--by", default=None, dest="by_seat",
                         help="Optional FQID of the seat marking ready")
    rpd_tpr.add_argument("--rationale", default=None,
                         help="Optional short rationale captured in the "
                              "transition log")
    rpd_tpr.add_argument("--repo-root", default=None,
                         help="Defaults to current working directory")

    rpd_ship = sub.add_parser(
        "record-prd-ship",
        help="Transition a PRD from state:technical_plan_ready to "
             "state:shipped (terminal); stamp shipped_sha (charter §2.2)",
    )
    rpd_ship.add_argument("prd_id",
                          help="The PRD id (file stem under docs/prds/)")
    rpd_ship.add_argument("--sha", required=True, dest="shipped_sha",
                          help="The LAND commit SHA shipping the PRD")
    rpd_ship.add_argument("--by", default=None, dest="by_seat",
                          help="Optional FQID of the seat shipping")
    rpd_ship.add_argument("--rationale", default=None,
                          help="Optional short rationale captured in the "
                               "transition log")
    rpd_ship.add_argument("--repo-root", default=None,
                          help="Defaults to current working directory")

    # consult-skill-platform — Gemini-CLI-mediated AI fan-out (charter
    # docs/inbox/2026-06-02-consult-skill-platform-gemini-fanout-charter.md).
    # Three verbs:
    #   consult <persona> <target>      — full gemini flow + Review write
    #   consult-with-response <p> <t>   — Y-branch fallback: skip gemini,
    #                                     write Review from a parsed JSON
    #                                     response file (model=claude-code).
    #   consult-supersede OLD NEW       — HR-#7 supersede transition.
    cs = sub.add_parser(
        "consult",
        help="Persona-mediated AI consult via backend CLI shell-out; "
             "writes a Review entity per charter §2.1 + chunk-0 PG-1(a). "
             "Exit codes: 11=GeminiUnavailable, 12=GeminiResponseParseError, "
             "13=MissingTargetStrict, 14=fail-on-large token-budget, "
             "15=AgyUnavailable, 16=AgyResponseParseError, "
             "17=codex backend not yet implemented. "
             "Skill layer orchestrates Y/n fallback on 11/12/15/16.",
    )
    cs.add_argument("persona", help="Persona slug (e.g. devil-advocate)")
    cs.add_argument("target",
                    help="Target entity-id (filename stem under docs/<kind>/)")
    # cohort R (wl:2026-06-05-06): multi-backend dispatch.
    # Default flipped gemini->agy 2026-06-11 (Kris-accepted, CTO dispatch
    # msg-a0c92adfacf4): gemini CLI shuts off 2026-06-18; explicit
    # `--backend gemini` remains available until then.
    cs.add_argument("--backend", default="agy",
                    choices=["gemini", "agy", "codex"],
                    help="Backend CLI to shell out to (default: agy). "
                         "gemini available until the 2026-06-18 shutoff; "
                         "codex=NotImplementedError (wl:2026-06-04-03 stub).")
    cs.add_argument("--model", default=None,
                    help="Override the per-backend default model. "
                         "gemini: defaults to persona.default_model or "
                         "DEFAULT_GEMINI_MODEL. agy: defaults to omitting "
                         "--model (agy built-in tenant-adapted default); "
                         "WL_AGY_MODEL env-var override layers on top.")
    cs.add_argument("--author", default="@unknown",
                    help='Author FQID (skill layer derives via parley whoami)')
    cs.add_argument("--owner-user", default="user/local",
                    help='Per D-RA-4; defaults "user/local"')
    cs.add_argument("--title", default=None,
                    help="Override the default Review title")
    cs.add_argument("--scope", default=None,
                    help="Override the auto-derived scope")
    cs.add_argument("--linked-msg-id", action="append", default=None,
                    dest="linked_msg_ids",
                    help="Repeatable; parley msg-ids carrying the consult call")
    cs.add_argument("--linked-decisions", default="",
                    help="Comma-separated decision ids")
    cs.add_argument("--supersedes", default=None,
                    help="Old review id this Review supersedes (HR-#7); "
                         "writes 'supersedes' back-pointer; old must be "
                         "transitioned separately via consult-supersede")
    cs.add_argument("--include-dirs", default=None, dest="include_dirs",
                    help="Comma-separated dirs to pass via --include-directories. "
                         "v2.0 default (flag omitted): repo root, filtered via "
                         ".gitignore + .consultignore (PRD R1). Pass empty string "
                         "(--include-dirs '') for the v1 explicit-empty escape "
                         "(no files; PRD R6 collaborator-insight-1).")
    cs.add_argument("--strict-context", action="store_true",
                    dest="strict_context",
                    help="R9: MissingTarget during auto context_bundle "
                         "assembly causes a non-zero exit (default: "
                         "warn-and-skip).")
    cs.add_argument("--verbose", action="store_true",
                    help="R13: print three filter stages (a=raw git ls-files, "
                         "b=post-.gitignore, c=post-.consultignore) to stderr "
                         "for debugging filter application.")
    cs.add_argument("--token-budget", type=int,
                    default=consult_context.DEFAULT_TOKEN_BUDGET,
                    dest="token_budget",
                    help=f"R13: token budget for the prompt + files payload "
                         f"(default {consult_context.DEFAULT_TOKEN_BUDGET}; "
                         f"byte-count // 4 estimate per R13). "
                         f"When exceeded: warning by default; see "
                         f"--confirm-large / --fail-on-large.")
    cs.add_argument("--confirm-large", action="store_true",
                    dest="confirm_large",
                    help="R7: silence the token-budget warning (operator "
                         "acknowledges the size).")
    cs.add_argument("--fail-on-large", action="store_true",
                    dest="fail_on_large",
                    help="R7: exit non-zero when the token-budget estimate "
                         "exceeds --token-budget (CI fail-fast).")
    cs.add_argument("--timeout", type=int, default=consult_mod.DEFAULT_TIMEOUT_S,
                    help="Backend subprocess timeout in seconds "
                         f"(default {consult_mod.DEFAULT_TIMEOUT_S})")
    cs.add_argument("--auto-fallback", action="store_true",
                    dest="auto_fallback",
                    help="wl:2026-06-05-03 SECONDARY: on backend subprocess "
                         "timeout, retry once with the frontmatter-derived "
                         "narrow scope (same scope the auto-narrow heuristic "
                         "would have used). Capped at 1 retry; default OFF "
                         "(opt-in for risk-tolerant batch workflows). "
                         "Suppressed when --include-dirs was explicit + "
                         "the derived narrow scope would not differ "
                         "meaningfully.")
    cs.add_argument("--gemini-bin", default="gemini",
                    help="Override the gemini binary name (test harnesses)")
    cs.add_argument("--agy-bin", default="agy",
                    help="Override the agy binary name (test harnesses); "
                         "only used when --backend agy")
    cs.add_argument("--repo-root", default=None,
                    help="Defaults to current working directory")

    cwr = sub.add_parser(
        "consult-with-response",
        help="Charter §2.4 Y-branch fallback: write a Review from a "
             "pre-parsed JSON response file (model=claude-code), skipping "
             "the gemini subprocess.",
    )
    cwr.add_argument("persona", help="Persona slug")
    cwr.add_argument("target", help="Target entity-id")
    cwr.add_argument("--response-from-file", required=True,
                     dest="response_from_file",
                     help="Path to a JSON file with the persona's parsed "
                          "response object (decision/findings/insights/notes)")
    cwr.add_argument("--model", default=consult_mod.FALLBACK_MODEL,
                     help=f"Model label (default {consult_mod.FALLBACK_MODEL})")
    cwr.add_argument("--author", default="@unknown")
    cwr.add_argument("--owner-user", default="user/local")
    cwr.add_argument("--title", default=None)
    cwr.add_argument("--scope", default=None)
    cwr.add_argument("--linked-msg-id", action="append", default=None,
                     dest="linked_msg_ids")
    cwr.add_argument("--linked-decisions", default="")
    cwr.add_argument("--supersedes", default=None,
                     help="Old review id this Review supersedes (HR-#7)")
    cwr.add_argument("--repo-root", default=None)

    css = sub.add_parser(
        "consult-supersede",
        help="HR-#7 supersede transition on the persona-mediated path: "
             "mark OLD review status=superseded + superseded_by=NEW.",
    )
    css.add_argument("old_id", help="The OLD Review id to supersede")
    css.add_argument("new_id", help="The NEW Review id that supersedes OLD")
    css.add_argument("--rationale", default=None)
    css.add_argument("--by", default=None, dest="by_seat",
                     help="Optional FQID of the seat invoking supersede")
    css.add_argument("--repo-root", default=None)

    ri_cmd = sub.add_parser(
        "re-index",
        help="Re-render a single entity-type INDEX.md (operator-facing — for "
             "rm-then-rebuild cleanup workflows; resolves Issue 2026-05-14-05)",
    )
    ri_cmd.add_argument(
        "kind",
        choices=list(_REINDEX_KINDS.keys()) + ["all"],
        help="Which INDEX to refresh; 'all' loops all six (skipping missing dirs)",
    )
    ri_cmd.add_argument("--repo-root", default=None,
                        help="Defaults to current working directory")

    ss_cmd = sub.add_parser(
        "sprint-status",
        help="Cross-repo sprint state snapshot (phase, pending decisions, "
             "open issues, tasks, recent boundary commits).",
    )
    ss_cmd.add_argument("sprint_id",
                        help='Sprint id without the "sprint-" folder prefix '
                             '(e.g., "workshop-lite.evals-first-doctrine")')
    ss_cmd.add_argument("--repo", action="append", default=None, dest="repos",
                        help="Repo root to scan; pass multiple times for "
                             "cross-repo sprints. Defaults to cwd if omitted.")
    ss_cmd.add_argument("--detail", action="store_true",
                        help="Include full task list + accepted decisions in "
                             "the text output (no-op in --json mode; JSON is "
                             "always full).")
    ss_cmd.add_argument("--json", action="store_true",
                        help="Emit JSON to stdout instead of human-readable text.")
    ss_cmd.add_argument("--commit-limit", type=int, default=10,
                        help="Max boundary commits to surface per repo (default 10).")

    # Master design §4.8 — pending-view CLI verbs (Sprint wl.14)
    dp = sub.add_parser(
        "decisions-pending",
        help="List decisions whose recipients[] names the seat AND seat "
             "is not in acted_on_by[] (read-only, per master design §4.8).",
    )
    dp.add_argument("--seat", required=True,
                    help="Seat FQID to query (exact-string match against "
                         "recipients[] elements).")
    dp.add_argument("--json", action="store_true",
                    help="Emit JSON array of frontmatter dicts instead of "
                         "human-readable text.")
    dp.add_argument("--repo-root", default=None,
                    help="Defaults to current working directory.")

    dsp = sub.add_parser(
        "dispatches-pending",
        help="List standing-dispatches whose recipients[] names the seat "
             "AND seat has not acted on the dispatch (read-only, per master "
             "design §4.8). Acted-on maps `acted_on_by[]` (future-compat) + "
             "`status==satisfied AND satisfied_by==seat` (shipped semantic) "
             "+ `status==superseded` (terminal).",
    )
    dsp.add_argument("--seat", required=True,
                     help="Seat FQID to query.")
    dsp.add_argument("--json", action="store_true",
                     help="Emit JSON array of frontmatter dicts.")
    dsp.add_argument("--repo-root", default=None,
                     help="Defaults to current working directory.")

    # Cohort W (wl:2026-06-03-06) — handoff aging / rolling-collapse policy.
    ag = sub.add_parser(
        "aging",
        help="Run the handoff aging policy: detect empty pre-compact stubs "
             "older than `[handoffs].empty_stub_age_hours` and "
             "archive / merge / delete them per "
             "`[handoffs].stub_collapse_strategy`. Defaults non-destructive. "
             "See `.claude/workshop-lite-config.toml` `[handoffs]` block.",
    )
    ag.add_argument(
        "--dry-run",
        action="store_true",
        help="Detect + report the eligible-stub count; never touch disk. "
             "Recommended for first-run audit before enabling cadence.",
    )
    ag.add_argument(
        "--strategy",
        default=None,
        choices=["archive", "merge-into-prev", "delete"],
        help="Override `[handoffs].stub_collapse_strategy` for this run "
             "(e.g., one-shot operator-driven merge). Omit to use config.",
    )
    ag.add_argument(
        "--json",
        action="store_true",
        help="Emit the run summary as JSON to stdout (otherwise plain text).",
    )
    ag.add_argument("--repo-root", default=None,
                    help="Defaults to current working directory.")

    vd = sub.add_parser(
        "validate",
        help="Run advisory dev-mgmt drift checks (D35 Sprint 6 subset: sprint "
             "folder coherence + INDEX coherence + frontmatter parse). Prints "
             "warnings to stderr; exits 0 unless --strict.",
    )
    vd.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero (1) if any warnings are emitted (CI-gate use)",
    )
    vd.add_argument(
        "--mtime-cutoff",
        type=int,
        default=None,
        help="Only apply frontmatter parse/validate (D35.3) to files modified "
             "in the last N seconds. Sprint/INDEX coherence (D35.1/D35.2) "
             "ignore this flag — they always run. Default: no cutoff (full).",
    )
    vd.add_argument(
        "--check",
        default=None,
        choices=["sprint-specs"],
        help="Run only a specific check subset. 'sprint-specs' runs the "
             "Phase 3 spec.yaml validators (V1-V8) and skips every other "
             "collector. Used by /end-sprint to gate sprint-close.",
    )
    vd.add_argument(
        "--sprint",
        default=None,
        help="Sprint id (without 'sprint-' prefix). When passed alongside "
             "--check sprint-specs, V3 required-artifact-missing warnings "
             "for that sprint upgrade to ERROR (the /end-sprint strict "
             "gate per sub-spec §4.2).",
    )
    vd.add_argument("--repo-root", default=None,
                    help="Defaults to current working directory")

    icmb = sub.add_parser(
        "install-codex-mcp-block",
        help="Install (or refresh) the canonical [mcp_servers.workshop_lite] "
             "block in <target>/.codex/config.toml with approval-mode "
             "configured for codex MCP-tool calls. Idempotent: creates the "
             "block if absent; inserts default_tools_approval_mode line if "
             "missing; no-op if the block is already canonical. Durable "
             "entry-point for the per-repo MCP wiring step that was "
             "previously a manual procedure (wl:2026-06-07 @user msg-794a58e6569a "
             "ask 2b).",
    )
    icmb.add_argument("--target", required=True,
                      help="Path to the consumer repo (e.g. /home/krisd/code/<repo>)")
    icmb.add_argument("--workshop-lite-bin", default=None,
                      help="Override the bin/wl-mcp path written into the block. "
                           "Default: <target>/bin/wl-mcp")
    icmb.add_argument("--approval-mode", default="approve",
                      choices=["auto", "prompt", "approve"],
                      help="Value for default_tools_approval_mode "
                           "(codex-rs/config/src/mcp_types.rs:117-220). "
                           "Default: approve")
    icmb.add_argument("--dry-run", action="store_true",
                      help="Print what would change without writing")

    # WL.29 D1: state-digest CLI subcommand
    sd = sub.add_parser(
        "state-digest",
        help="Emit the workshop-lite substrate orientation digest "
             "(active sprint, recent decisions, latest handoff, open "
             "issues, standing dispatches, WIP claims) to stdout. "
             "Primary contract is stdout-direct so any agent class "
             "(codex, antigravity, subprocess) can consume via shell-out. "
             "Backs the codex-host SessionStart hook installed by "
             "`wl install-codex-content` (WL.29 cohort).",
    )
    sd.add_argument("--repo-root", default=None,
                    help="Repo root (defaults to current working directory)")
    sd.add_argument("--current-seat", default=None,
                    help="FQID of the calling seat (e.g. 'wl-rearch:wl-plan'); "
                         "used to filter wip-claims + standing-dispatches "
                         "sections to the seat. Mirrors the existing "
                         "state_digest.py flag.")
    sd.add_argument("--output-mode", default="claude_code",
                    choices=["claude_code", "codex", "plain"],
                    help="Output framing. claude_code (default) preserves "
                         "the existing render_digest verbatim. codex "
                         "prepends a codex-host framing prefix. plain "
                         "strips markdown decorators for "
                         "lowest-common-denominator text consumers.")

    # WL.29 D2: install-codex-content verb
    icc = sub.add_parser(
        "install-codex-content",
        help="Install the full codex-host substrate-emission content set "
             "into a consumer repo so codex agents are first-class "
             "workshop-lite citizens: (1) user-global trust entry; "
             "(2) repo-local MCP server block (composes with "
             "install-codex-mcp-block); (3) 3 codex-host hook scripts "
             "in .codex/hooks/; (4) PascalCase [[hooks.<Event>]] "
             "registrations in .codex/config.toml; (5) AGENTS.md "
             "substrate-orientation section. Idempotent across all "
             "5 emission paths. WL.29 cohort D2 (subsumes "
             "install-codex-mcp-block per @plan Option B ruling).",
    )
    icc.add_argument("--target", required=True,
                     help="Path to the consumer repo")
    icc.add_argument("--workshop-lite-bin", default=None,
                     help="Override the bin/wl-mcp path written into the "
                          "MCP server block. Default: <target>/bin/wl-mcp")
    icc.add_argument("--user-config-path", default=None,
                     help="Override the user-global codex config path used "
                          "for the trust entry. Default: ~/.codex/config.toml. "
                          "Set this for test isolation.")
    icc.add_argument("--dry-run", action="store_true",
                     help="Print the planned changes without writing")

    # WL.30 D1: install-workshop-lite-content verb. Propagates the WL
    # substrate content set (helper lib + skills + hooks + conventions +
    # templates + bin/) to a non-parley consumer repo. Chunk-0 ratify
    # msg-d91261e535ed binds dynamic discovery + per-file-class drift
    # policy (CLASS-A whole-file + CLASS-B marker-delimited).
    iwlc = sub.add_parser(
        "install-workshop-lite-content",
        help="Install the workshop-lite substrate content set into a "
             "non-parley consumer repo: (1) .claude/scripts/dev-mgmt/ "
             "helper lib; (2) .claude/skills/ skills; (3) .claude/hooks/ "
             "hooks; (4) docs/conventions/ Tier-1 rules; (5) "
             "docs/.templates/ entity templates; (6) bin/ entry-point "
             "shims; (7) .claude/settings.json workshop-lite-* hook "
             "entries (marker-delimited merge); (8) CLAUDE.md fragment "
             "(marker-delimited). CLASS-A whole-file artifacts use "
             "file-level drift-detect; CLASS-B surfaces use marker-"
             "delimited regions. Idempotent across all categories. "
             "WL.30 cohort D1+D2.",
    )
    iwlc.add_argument("--target", required=True,
                      help="Absolute path to the consumer repo root")
    iwlc.add_argument("--source", default=None,
                      help="Absolute path to the workshop-lite substrate "
                           "source root. Default: detected via "
                           "resolve_workshop_lite_source_root() from "
                           "cli.py's location.")
    iwlc.add_argument("--dry-run", action="store_true",
                      help="Print the planned changes without writing")
    iwlc.add_argument("--accept-drift", action="store_true",
                      help="Override D3 PG-4 PRE-WRITE drift detection: "
                           "overwrite hand-edited CLASS-A whole-file "
                           "artifacts. Destructive — same semantics as "
                           "`parley adopt-workshop-lite --accept-drift`. "
                           "CLASS-B marker-delimited surfaces (settings.json "
                           "hook entries, CLAUDE.md fragment) ignore this "
                           "flag — outside-marker content is always "
                           "preserved by-construction.")

    # issue 2026-06-10-02: Layer-C prompt-pack payload emitter (WL half).
    epp = sub.add_parser(
        "emit-pack-payload",
        help="Emit the adapter-neutral Layer-C prompt-pack payload (YAML) to "
             "stdout. WL authors the pack content (constraints / "
             "evidence-obligation / memory-scope / persona sections); the "
             "render seam (par-plan surface) consumes this and writes the "
             "managed block into CLAUDE.md/AGENTS.md. HR-1: WL emits the "
             "payload only and never writes another agent's instructions "
             "file. Shell-out consumption surface (mirrors `wl state-digest`). "
             "issue 2026-06-10-02 / Layer-B registration prompt_pack (§4.4).",
    )
    epp.add_argument("--adapter", default=None,
                     choices=list(workshop_lite_pack_mod.SUPPORTED_ADAPTERS),
                     help="Render target. Default unset — the render seam "
                          "sets it per target; the same payload renders to "
                          "both (only the skill-ref path + phrasing differ).")
    epp.add_argument("--managed-block",
                     default=workshop_lite_pack_mod.MANAGED_BLOCK,
                     help="Managed-block marker name. Default 'workshop-lite-"
                          "pack' (suffix-disambiguated from the workshop-lite-"
                          "start/-end install-fragment marker; @plan "
                          "msg-e44efe2ed7af option (a) ratify). The render "
                          "seam may override per render target — see module "
                          "docstring MARKER CONVENTION.")
    epp.add_argument("--no-evidence-obligation", action="store_true",
                     help="Omit the rec #10 evidence_obligation section.")
    epp.add_argument("--no-memory-scope", action="store_true",
                     help="Omit the rec #14 memory_scope section.")
    epp.add_argument("--persona-reasoning", default=None,
                     help="persona dimension: reasoning (e.g. empirical).")
    epp.add_argument("--persona-register", default=None,
                     help="persona dimension: register (e.g. terse).")
    epp.add_argument("--persona-conflict", default=None,
                     help="persona dimension: conflict (e.g. adversarial).")

    # ----- BC1.2 — the 5 new kinds (spec §2.3) -----
    rwf = sub.add_parser(
        "record-workflow",
        help="Write a workflow library entry to "
             ".workshop-lite/ledger/workflows/<slug>.md",
    )
    rwf.add_argument("--title", required=True)
    rwf.add_argument("--stages-json", required=True,
                     help='JSON array of stage objects; each requires {name}; '
                          'optional {produces_artifact_kind, parallelizable}')
    rwf.add_argument("--author", required=True, help='e.g. "@wl-l"')
    rwf.add_argument("--status", default="active",
                     choices=["draft", "active", "superseded", "retired"])
    rwf.add_argument("--library-layer", default="user",
                     choices=["built-in", "project", "user"])
    rwf.add_argument("--is-default", action="store_true")
    rwf.add_argument("--supersedes", default=None)
    rwf.add_argument("--linked-decisions", default="",
                     help="Comma-separated decision ids")
    rwf.add_argument("--owner-user", default="user/local")
    rwf.add_argument("--body", default=None)
    rwf.add_argument("--repo-root", default=None)

    rrs = sub.add_parser(
        "record-role-set",
        help="Write a role-set library entry to "
             ".workshop-lite/ledger/role-sets/<slug>.md",
    )
    rrs.add_argument("--title", required=True)
    rrs.add_argument("--roles-json", required=True,
                     help='JSON array of role objects; each requires '
                          '{name, owns_stage}; optional {identity_predicate}')
    rrs.add_argument("--author", required=True)
    rrs.add_argument("--sod-predicates-json", default="[]",
                     help="JSON array of SoD/identity constraint strings (§12)")
    rrs.add_argument("--per-stage-markers-json", default="{}",
                     help='JSON object stage→{parallelizable, aggregation '
                          '∈ all-must-pass|merge|pick-one}')
    rrs.add_argument("--status", default="active",
                     choices=["draft", "active", "superseded", "retired"])
    rrs.add_argument("--library-layer", default="user",
                     choices=["built-in", "project", "user"])
    rrs.add_argument("--is-default", action="store_true")
    rrs.add_argument("--supersedes", default=None)
    rrs.add_argument("--owner-user", default="user/local")
    rrs.add_argument("--body", default=None)
    rrs.add_argument("--repo-root", default=None)

    rbs = sub.add_parser(
        "raise-block-signal",
        help="Raise a block-signal to "
             ".workshop-lite/ledger/block-signals/<id>.md",
    )
    rbs.add_argument("--blocked-subject", required=True,
                     help="ref to the blocked work-item")
    rbs.add_argument("--waits-on", required=True,
                     help="ref|event|condition the block waits on")
    rbs.add_argument("--class", dest="klass", required=True,
                     choices=["HALT", "wait_for"])
    rbs.add_argument("--created-by", required=True)
    rbs.add_argument("--status", default="raised",
                     choices=["raised", "resolved", "expired"])
    rbs.add_argument("--deadline", default=None)
    rbs.add_argument("--ttl", default=None,
                     help="REQUIRED for class=wait_for (indefinite forbidden); "
                          "must be ABSENT for class=HALT")
    rbs.add_argument("--inferred-by", default=None)
    rbs.add_argument("--body", default=None)
    rbs.add_argument("--repo-root", default=None)

    rrl = sub.add_parser(
        "write-resume-ledger",
        help="Write a resume-ledger to "
             ".workshop-lite/ledger/resume-ledgers/<id>.md",
    )
    rrl.add_argument("--worker", required=True, help="role/seat-id")
    rrl.add_argument("--in-flight-state", required=True)
    rrl.add_argument("--next-actions-json", required=True,
                     help="JSON array of next-action strings")
    rrl.add_argument("--author", required=True)
    rrl.add_argument("--canonical-pointer-ref", default=None)
    rrl.add_argument("--supersedes", default=None)
    rrl.add_argument("--owner-user", default="user/local")
    rrl.add_argument("--body", default=None)
    rrl.add_argument("--repo-root", default=None)

    rcp = sub.add_parser(
        "write-canonical-pointer",
        help="Write/update a canonical-pointer (mutable head) to "
             ".workshop-lite/ledger/pointers/<slug>.md",
    )
    rcp.add_argument("--names", required=True, help="the body-of-work name")
    rcp.add_argument("--points-to", required=True,
                     help="ref|path = the current source-of-truth")
    rcp.add_argument("--updated-by", required=True)
    rcp.add_argument("--owner-user", default="user/local")
    rcp.add_argument("--body", default=None)
    rcp.add_argument("--repo-root", default=None)

    mt = sub.add_parser(
        "migrate-tasks",
        help="Migrate v1 4-state task lines to R6 canonical form (BC1.5). "
             "Idempotent; non-task lines preserved. Without --sprint-id, "
             "walks every sprint's tasks.md.",
    )
    mt.add_argument("--sprint-id", default=None,
                    help="Migrate just this sprint's tasks.md; omit to migrate all.")
    mt.add_argument("--repo-root", default=None)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.command == "record-decision":
        options = json.loads(args.options_json)
        path = entities.record_decision(
            title=args.title,
            rationale=args.rationale,
            options=options,
            scope=args.scope,
            author=args.author,
            repo_root=Path(args.repo_root) if args.repo_root else None,
            authored_with=_split_csv(args.authored_with),
            linked_decisions=_split_csv(args.linked_decisions),
            linked_reviews=_split_csv(args.linked_reviews),
            linked_msg_ids=_split_csv(args.linked_msg_ids),
            sprint_id=args.sprint_id,
            stage=args.stage,
            supersedes=args.supersedes,
            status=args.status,
            affects=args.affects,
        )
        print(path)
        return 0

    if args.command == "start-sprint":
        path = entities.start_sprint(
            sprint_id=args.sprint_id,
            title=args.title,
            author=args.author,
            repo_root=Path(args.repo_root) if args.repo_root else None,
            plan_body_path=args.from_plan,
            force=args.force,
            linked_design_docs=_split_csv(args.linked_design_docs),
        )
        # Phase 3 (sub-spec §8.1): --spec <kind> creates initial
        # spec.yaml with role-kind defaults. Omitted: legacy behavior.
        if args.spec:
            import sprint_spec as _sprint_spec_mod
            repo = Path(args.repo_root) if args.repo_root else Path.cwd()
            charter_ref = _split_csv(args.spec_charter_ref) or []
            _sprint_spec_mod.write_initial_spec_yaml(
                repo_root=repo,
                sprint_id=args.sprint_id,
                sprint_kind=args.spec,
                author=args.author,
                has_user_journey=args.spec_has_user_journey,
                charter_ref=charter_ref,
            )
        print(path)
        return 0

    if args.command == "end-sprint":
        retro_body = None
        if args.retro_body_path:
            retro_body = Path(args.retro_body_path).read_text(encoding="utf-8")
        test_results = (
            json.loads(args.test_results_json) if args.test_results_json else None
        )
        # Phase 3 (sub-spec §4.2 + §8.2): if the sprint has a spec.yaml
        # AND its sprint_kind has gate_at_end=True, run the strict
        # spec-yaml gate BEFORE moving any files. Non-zero exit aborts
        # /end-sprint with validator output printed to stderr.
        repo_root_path = Path(args.repo_root) if args.repo_root else Path.cwd()
        gate_result = _maybe_run_end_sprint_gate(
            repo_root_path, args.sprint_id,
        )
        if gate_result is not None:
            sys.stderr.write(gate_result)
            sys.stderr.write(
                f"\nABORTED: /end-sprint gate failed for sprint "
                f"{args.sprint_id!r} (sub-spec §4.2). "
                "Resolve the spec.yaml errors above (populate missing "
                "artifact paths, or downgrade required: false with a "
                "recorded Decision) and re-run.\n"
            )
            return 1
        path = entities.end_sprint(
            sprint_id=args.sprint_id,
            author=args.author,
            repo_root=Path(args.repo_root) if args.repo_root else None,
            retro_title=args.retro_title,
            retro_body=retro_body,
            force=args.force,
            test_results=test_results,
            linked_decisions=_split_csv(args.linked_decisions),
            linked_reviews=_split_csv(args.linked_reviews),
        )
        print(path)
        return 0

    if args.command == "handoff":
        path = entities.record_handoff(
            title=args.title,
            topic=args.topic,
            author=args.author,
            trigger=args.trigger,
            sprint_id=args.sprint_id,
            stage=args.stage,
            since_handoff_id=args.since_handoff_id,
            since_msg_id=args.since_msg_id,
            repo_root=Path(args.repo_root) if args.repo_root else None,
            body=args.body,
            body_from_path=args.body_from_file,
            linked_decisions=_split_csv(args.linked_decisions),
            linked_issues=_split_csv(args.linked_issues),
            linked_tasks=_split_csv(args.linked_tasks),
            linked_msg_ids=_split_csv(args.linked_msg_ids),
            next_action=args.next_action,
        )
        print(path)
        return 0

    if args.command == "record-issue":
        path = entities.record_issue(
            title=args.title,
            severity=args.severity,
            scope=args.scope,
            reporter=args.reporter,
            status=args.status,
            sprint_id=args.sprint_id,
            stage=args.stage,
            klass=args.klass,
            repo_root=Path(args.repo_root) if args.repo_root else None,
            body=args.body,
            body_from_path=args.body_from_file,
            linked_decisions=_split_csv(args.linked_decisions),
            linked_reviews=_split_csv(args.linked_reviews),
            linked_msg_ids=_split_csv(args.linked_msg_ids),
        )
        print(path)
        return 0

    if args.command == "record-review":
        findings = json.loads(args.findings_json)
        # Sprint S-B D1=A — thread the structured accurate-trail for
        # the cross-check-resolution type (validator-mandatory non-empty
        # for that review_type; None for every other type ⇒ the
        # passthrough is inert / grandfathering by-construction).
        accurate_trail = (
            json.loads(args.accurate_trail_json)
            if args.accurate_trail_json else None
        )
        path = entities.record_review(
            title=args.title,
            review_type=args.review_type,
            scope=args.scope,
            author=args.author,
            status=args.status,
            sprint_id=args.sprint_id,
            stage=args.stage,
            repo_root=Path(args.repo_root) if args.repo_root else None,
            body=args.body,
            body_from_path=args.body_from_file,
            findings=findings,
            accurate_trail=accurate_trail,
            linked_decisions=_split_csv(args.linked_decisions),
            linked_reviews=_split_csv(args.linked_reviews),
            linked_msg_ids=_split_csv(args.linked_msg_ids),
        )
        print(path)
        return 0

    if args.command == "add-task":
        tasks_path, task_id = entities.add_task(
            sprint_id=args.sprint_id,
            description=args.description,
            assignee=args.assignee,
            status=args.status,
            linked_issues=_split_csv(args.linked_issues),
            linked_decisions=_split_csv(args.linked_decisions),
            repo_root=Path(args.repo_root) if args.repo_root else None,
        )
        print(f"{tasks_path}\t{task_id}")
        return 0

    if args.command == "capture-conversation":
        verbatim_text: str | None = None
        verbatim_msg_range: list[str | None] = [None, None]
        started_at = args.started_at
        ended_at = args.ended_at
        auto_participants: list[str] = []

        mode_flags = (
            bool(args.verbatim),
            bool(args.verbatim_from_file),
            bool(args.verbatim_from_stdin),
            bool(args.verbatim_records_json_from_stdin),
        )
        if sum(mode_flags) != 1:
            print(
                "error: exactly one of --verbatim, --verbatim-from-file, "
                "--verbatim-from-stdin, --verbatim-records-json-from-stdin "
                "must be provided",
                file=sys.stderr,
            )
            return 2

        if args.verbatim:
            verbatim_text = args.verbatim
        elif args.verbatim_from_file:
            verbatim_text = Path(args.verbatim_from_file).read_text(encoding="utf-8")
        elif args.verbatim_from_stdin:
            verbatim_text = sys.stdin.read()
        else:
            # records-json mode: read JSON-lines, render via entities._render_parley_verbatim
            records: list[dict] = []
            for line in sys.stdin:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError as e:
                    print(f"error: malformed JSON record on stdin: {e}",
                          file=sys.stderr)
                    return 2
            # Issue 2026-05-15-05: fail loud on an empty record set. The lib
            # (_render_parley_verbatim) intentionally returns a "(no records
            # in this range)" marker for the empty case — that is correct,
            # parley-agnostic library behavior. But at the CLI boundary an
            # empty capture is an operator error (errored/empty `parley get`,
            # bad --since, missing pipe), NOT a valid Conversation entity.
            # Refuse to write a defective participants:[]/[null,null] file;
            # mirror the record-* "ValidationError exits non-zero, writes
            # nothing" contract.
            if not records:
                print(
                    "error: no records on stdin — refusing to write an empty "
                    "Conversation entity. Check the `parley get` args "
                    "(--since / range) that feed this command; an errored or "
                    "empty `parley get` produces no records.",
                    file=sys.stderr,
                )
                return 2
            rendered, msg_range_auto, sat_auto, eat_auto = (
                entities._render_parley_verbatim(records)
            )
            verbatim_text = rendered
            verbatim_msg_range = msg_range_auto
            if started_at is None:
                started_at = sat_auto
            if ended_at is None:
                ended_at = eat_auto
            # D24: auto-derive participants from unique `from` field values
            seen: set[str] = set()
            for r in records:
                from_id = (r.get("from") or "").strip()
                if not from_id:
                    continue
                if not from_id.startswith("@"):
                    from_id = f"@{from_id}"
                if from_id not in seen:
                    seen.add(from_id)
                    auto_participants.append(from_id)

        if args.verbatim_msg_range is not None:
            pair = args.verbatim_msg_range.split(",")
            if len(pair) != 2:
                print("error: --verbatim-msg-range must be 'msg-first,msg-last'",
                      file=sys.stderr)
                return 2
            verbatim_msg_range = [
                pair[0].strip() or None,
                pair[1].strip() or None,
            ]

        # D24: --participants override beats auto-derive
        if args.participants is not None:
            participants = _split_csv(args.participants) or []
        else:
            participants = auto_participants

        # D25: zone auto-detect (active sprint folder → 'sprint', else 'cross-sprint')
        zone = args.zone
        if zone is None:
            repo_for_zone = Path(args.repo_root) if args.repo_root else Path.cwd()
            active_dir = repo_for_zone / "docs" / "sprints" / "active"
            active_sprints = (
                [d for d in active_dir.iterdir() if d.is_dir()
                 and d.name.startswith("sprint-")]
                if active_dir.exists() else []
            )
            zone = "sprint" if active_sprints else "cross-sprint"

        # Issue 2026-05-15-05 (defense-in-depth chokepoint): regardless of
        # input mode, refuse to persist a Conversation whose verbatim body is
        # structurally empty (empty/whitespace after strip). Catches the
        # --verbatim / --verbatim-from-file / --verbatim-from-stdin empty
        # paths and any future mode that resolves to an empty body.
        #
        # MOD-W-F1 (b) — @plan msg-1a89d7dbb688, locked: this guard keys off
        # a STRUCTURAL emptiness signal ONLY, mirroring guard-1's shape
        # (`if not records` in the records-json branch above — record-count,
        # no marker text). The earlier prose-equality clause (a `_vt ==`
        # comparison against the renderer's empty-range marker string) is
        # ELIMINATED, not centralized: the actual silent-empty footgun
        # (records-json fed by an errored/empty parley get — the exact
        # 2026-05-15-05 repro) is caught by guard-1 BEFORE
        # _render_parley_verbatim is ever called, so it stays closed under
        # ANY rewording of that renderer marker WITHOUT this guard
        # depending on its text. The marker lives solely as an
        # entities.py-local presentation literal now, NOT a cross-file
        # guard contract — removing the W-arc-W-F1 drift vector entirely
        # (cli.py deliberately does not name or import it). A caller that
        # deliberately passes the marker text as --verbatim is real
        # non-empty content and is correctly allowed (the old prose match
        # was a false-positive; (b) drops it on purpose).
        _vt = (verbatim_text or "").strip()
        if not _vt:
            print(
                "error: refusing to write a Conversation with an empty "
                "verbatim body (no captured chat). This is the "
                "silent-empty-capture footgun (issue 2026-05-15-05) — "
                "check the input/stdin feeding this command.",
                file=sys.stderr,
            )
            return 2

        path = entities.capture_conversation(
            title=args.title,
            topic=args.topic,
            verbatim_text=verbatim_text or "",
            verbatim_msg_range=verbatim_msg_range,
            participants=participants,
            zone=zone,
            sprint_id=args.sprint_id,
            stage=args.stage,
            started_at=started_at,
            ended_at=ended_at,
            repo_root=Path(args.repo_root) if args.repo_root else None,
            body=args.body,
            body_from_path=args.body_from_file,
            linked_design_docs=_split_csv(args.linked_design_docs),
            linked_decisions=_split_csv(args.linked_decisions),
            linked_reviews=_split_csv(args.linked_reviews),
            linked_issues=_split_csv(args.linked_issues),
            linked_handoffs=_split_csv(args.linked_handoffs),
            linked_msg_ids=_split_csv(args.linked_msg_ids),
        )
        print(path)
        return 0

    if args.command == "record-wip":
        from datetime import datetime as _dt, timezone as _tz
        paths_list = _split_csv(args.paths) or []
        if not paths_list:
            print(
                "error: --paths must be a non-empty comma-separated list",
                file=sys.stderr,
            )
            return 2
        try:
            duration = _parse_duration(args.expires)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        created_at = _dt.now(_tz.utc).replace(microsecond=0)
        expires_at = created_at + duration
        try:
            path = wip_claim_mod.record_wip_claim(
                repo_root=Path(args.repo_root) if args.repo_root else Path.cwd(),
                slug=args.slug,
                paths=paths_list,
                scope=args.scope,
                expires_at=expires_at,
                seat=args.seat,
                sprint_id=args.sprint_id,
                stage=args.stage,
                linked_msg_ids=_split_csv(args.linked_msg_ids),
                linked_sprints=_split_csv(args.linked_sprints),
                linked_decisions=_split_csv(args.linked_decisions),
                created_at=created_at,
                owner_user=args.owner_user,
                title=args.title,
            )
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        print(path)
        return 0

    if args.command == "record-wip-release":
        path = wip_claim_mod.release_wip_claim(
            repo_root=Path(args.repo_root) if args.repo_root else Path.cwd(),
            claim_id=args.claim_id,
            rationale=args.rationale,
        )
        print(path)
        return 0

    if args.command == "record-wip-extend":
        try:
            duration = _parse_duration(args.duration)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        path = wip_claim_mod.extend_wip_claim(
            repo_root=Path(args.repo_root) if args.repo_root else Path.cwd(),
            claim_id=args.claim_id,
            duration=duration,
        )
        print(path)
        return 0

    if args.command == "record-dispatch":
        from datetime import datetime as _dt
        recipients_list = _split_csv(args.recipients) or []
        if not recipients_list:
            print(
                "error: --recipients must be a non-empty comma-separated "
                "list of FQID strings",
                file=sys.stderr,
            )
            return 2

        def _parse_iso_arg(name: str, value: str | None):
            if value is None or value == "":
                return None
            try:
                dt = _dt.fromisoformat(value.replace("Z", "+00:00"))
            except (ValueError, TypeError) as exc:
                raise ValueError(
                    f"--{name} must be an ISO 8601 timestamp, got: "
                    f"{value!r} ({exc})"
                )
            return dt

        try:
            deadline = _parse_iso_arg("deadline", args.deadline)
            expires_at = _parse_iso_arg("expires-at", args.expires_at)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

        try:
            path = dispatch_mod.record_standing_dispatch(
                repo_root=Path(args.repo_root) if args.repo_root else Path.cwd(),
                slug=args.slug,
                purpose=args.purpose,
                recipients=recipients_list,
                expected_outcome=args.expected_outcome,
                scope=args.scope,
                deadline=deadline,
                expires_at=expires_at,
                linked_msg_ids=list(args.linked_msg_ids or []),
                linked_decisions=_split_csv(args.linked_decisions),
                linked_handoffs=_split_csv(args.linked_handoffs),
                linked_reviews=_split_csv(args.linked_reviews),
                supersedes=args.supersedes,
                satisfy_quorum=args.satisfy_quorum,
                sprint_id=args.sprint_id,
                stage=args.stage,
                created_by=args.created_by,
                owner_user=args.owner_user,
                title=args.title,
            )
        except (ValueError, validators.ValidationError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        print(path)
        return 0

    if args.command == "record-dispatch-satisfy":
        try:
            path = dispatch_mod.satisfy_dispatch(
                repo_root=Path(args.repo_root) if args.repo_root else Path.cwd(),
                dispatch_id=args.dispatch_id,
                by_seat=args.by_seat,
                rationale=args.rationale,
            )
        except FileNotFoundError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        print(path)
        return 0

    if args.command == "record-dispatch-supersede":
        try:
            path = dispatch_mod.supersede_dispatch(
                repo_root=Path(args.repo_root) if args.repo_root else Path.cwd(),
                new_id=args.new_id,
                old_id=args.old_id,
            )
        except FileNotFoundError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        print(path)
        return 0

    if args.command == "record-prd":
        try:
            path = prd_mod.record_prd(
                repo_root=Path(args.repo_root) if args.repo_root else Path.cwd(),
                slug=args.slug,
                title=args.title,
                scope=args.scope,
                author=args.author,
                owner_user=args.owner_user,
                pm_summary=args.pm_summary,
                linked_msg_ids=list(args.linked_msg_ids or []),
                linked_decisions=_split_csv(args.linked_decisions),
                cross_repo_prds=_split_csv(args.cross_repo_prds),
            )
        except (ValueError, validators.ValidationError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        print(path)
        return 0

    if args.command == "record-prd-ratify":
        try:
            path = prd_mod.ratify_prd(
                repo_root=Path(args.repo_root) if args.repo_root else Path.cwd(),
                prd_id=args.prd_id,
                by_seat=args.by_seat,
                rationale=args.rationale,
            )
        except (FileNotFoundError, ValueError,
                validators.ValidationError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        print(path)
        return 0

    if args.command == "record-prd-convert":
        try:
            path = prd_mod.convert_prd(
                repo_root=Path(args.repo_root) if args.repo_root else Path.cwd(),
                prd_id=args.prd_id,
                by_seat=args.by_seat,
                rationale=args.rationale,
            )
        except (FileNotFoundError, ValueError,
                validators.ValidationError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        print(path)
        return 0

    if args.command == "record-prd-technical-plan-ready":
        try:
            path = prd_mod.mark_technical_plan_ready(
                repo_root=Path(args.repo_root) if args.repo_root else Path.cwd(),
                prd_id=args.prd_id,
                technical_plan_url=args.technical_plan_url,
                by_seat=args.by_seat,
                rationale=args.rationale,
            )
        except (FileNotFoundError, ValueError,
                validators.ValidationError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        print(path)
        return 0

    if args.command == "record-prd-ship":
        try:
            path = prd_mod.ship_prd(
                repo_root=Path(args.repo_root) if args.repo_root else Path.cwd(),
                prd_id=args.prd_id,
                shipped_sha=args.shipped_sha,
                by_seat=args.by_seat,
                rationale=args.rationale,
            )
        except (FileNotFoundError, ValueError,
                validators.ValidationError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        print(path)
        return 0

    if args.command in ("consult", "consult-with-response"):
        repo = Path(args.repo_root) if args.repo_root else Path.cwd()
        try:
            persona_meta, persona_body, _ = consult_mod.resolve_persona(
                repo, args.persona,
            )
            target_fm, target_body, _target_path = consult_mod.resolve_target(
                repo, args.target,
            )
        except (consult_mod.PersonaNotFound,
                consult_mod.TargetNotFound,
                ValueError,
                validators.ValidationError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

        if args.command == "consult":
            # cohort R (wl:2026-06-05-06): per-backend model resolution.
            # - gemini: --model > persona.default_model > DEFAULT_GEMINI_MODEL
            # - agy:    --model > $WL_AGY_MODEL > None (omit --model flag;
            #           agy picks built-in tenant-adapted default per F4)
            # - codex:  placeholder; NotImplementedError raised in dispatch
            # ``review_model`` is the string written into the Review entity
            # frontmatter — set to "agy" when no specific model was named
            # (so traceability still shows which backend served the call).
            if args.backend == "agy":
                model = (
                    args.model
                    or os.environ.get(consult_mod.AGY_MODEL_ENV)
                    or None
                )
                review_model = model or "agy"
            elif args.backend == "codex":
                model = args.model or "codex"
                review_model = model
            else:  # gemini (default — preserves byte-identical regression)
                model = args.model or persona_meta.get(
                    "default_model", consult_mod.DEFAULT_GEMINI_MODEL,
                )
                review_model = model
            output_schema = persona_meta.get("output_schema")

            # PRD R2: auto-compute context_bundle from target's linked_*
            # forward fields (1-hop only, deterministic order, self-ref
            # loop guard). R9: --strict-context fails fast on miss.
            try:
                bundle_text, bundle_diag = consult_context.build_context_bundle(
                    repo, target_fm, target_id=args.target,
                    strict=args.strict_context,
                )
            except consult_context.MissingTargetStrict as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 13
            for d in bundle_diag:
                print(d, file=sys.stderr)

            # PRD R1+R3+R8+R13: default include_dirs = repo root, filtered
            # via .gitignore (git ls-files --exclude-standard) + .consultignore
            # (pathspec layer, positive excludes only per R10).
            #
            # Sentinel-based resolution:
            #   args.include_dirs is None  → v2.0 default (repo root + filter)
            #   args.include_dirs == ""    → R6 explicit-empty escape (no files)
            #   args.include_dirs == "..." → explicit CSV list (no filter)
            visible_files: list[str] = []
            stages_for_verbose: dict[str, list[str]] = {}
            filter_diag: list[str] = []
            if args.include_dirs is None:
                visible_files, stages_for_verbose, filter_diag = (
                    consult_context.discover_visible_files(repo)
                )
                include_dirs = [str(repo)]
            elif args.include_dirs == "":
                include_dirs = []
            else:
                include_dirs = _split_csv(args.include_dirs)

            for d in filter_diag:
                print(d, file=sys.stderr)

            # PRD R13: --verbose prints all three filter stages so
            # operators can debug .gitignore / .consultignore interactions.
            # Only meaningful on the default include_dirs path; explicit
            # --include-dirs bypasses the filter computation.
            if args.verbose and args.include_dirs is None:
                sys.stderr.write(
                    "=== consult --verbose: filter stages ===\n"
                )
                stage_labels = (
                    ("a (raw git ls-files)",        stages_for_verbose.get("a", [])),
                    ("b (post-.gitignore)",         stages_for_verbose.get("b", [])),
                    ("c (post-.consultignore)",     stages_for_verbose.get("c", [])),
                )
                for label, files in stage_labels:
                    sys.stderr.write(
                        f"stage {label}: {len(files)} files\n"
                    )
                    for f in files:
                        sys.stderr.write(f"  {f}\n")
                sys.stderr.write("=== /consult --verbose ===\n")

            assembled = consult_mod.assemble_prompt(
                persona_body=persona_body,
                target_id=args.target,
                target_fm=target_fm,
                target_body=target_body,
                context_bundle=bundle_text,
                output_schema=output_schema if isinstance(output_schema, dict) else None,
                persona_dimensions=consult_mod.extract_persona_dimensions(persona_meta),
            )

            # PRD R7 + R13: token-budget gate. Estimate prompt tokens +
            # files-payload tokens (byte // 4 approximation per R13);
            # warn / silence / fail per --confirm-large / --fail-on-large.
            prompt_tokens = consult_context.estimate_token_count(assembled)
            files_bytes = consult_context.estimate_files_payload(
                repo, visible_files,
            )
            files_tokens_est = files_bytes // 4
            total_est = prompt_tokens + files_tokens_est

            # wl:2026-06-05-03 PRIMARY auto-narrow heuristic
            # (charter §4.1). Operator-passed --include-dirs always
            # wins (args.include_dirs is None → no explicit scope).
            # SECONDARY auto-fallback retry reads this derived scope
            # too, so cache it for the except-block to reuse without
            # re-deriving.
            auto_narrow_derived: list[str] = []
            if args.include_dirs is None:
                auto_narrow_mult = (
                    consult_mod.auto_narrow_threshold_multiplier()
                )
                auto_narrow_threshold = (
                    auto_narrow_mult * args.token_budget
                )
                if total_est > auto_narrow_threshold:
                    derived_dirs = consult_mod._auto_narrow_include_dirs(
                        target_fm,
                    )
                    if derived_dirs:
                        narrowed = [
                            f for f in visible_files
                            if any(
                                f == d or f.startswith(d + "/")
                                for d in derived_dirs
                            )
                        ]
                        if narrowed:
                            auto_narrow_derived = derived_dirs
                            visible_files = narrowed
                            include_dirs = [
                                str(repo / d) for d in derived_dirs
                            ]
                            files_bytes = (
                                consult_context.estimate_files_payload(
                                    repo, visible_files,
                                )
                            )
                            files_tokens_est = files_bytes // 4
                            new_total = prompt_tokens + files_tokens_est
                            print(
                                f"[auto-narrow] consult: token-budget "
                                f"estimate {total_est} exceeds "
                                f"{auto_narrow_mult}x cap "
                                f"({auto_narrow_threshold}); derived "
                                f"include_dirs={derived_dirs} from "
                                f"target scope "
                                f"{target_fm.get('scope', '<none>')!r}"
                                f" / type "
                                f"{target_fm.get('type', '<none>')!r};"
                                f" new estimate={new_total} "
                                f"({len(visible_files)} files visible)",
                                file=sys.stderr,
                            )
                            total_est = new_total

            if total_est > args.token_budget:
                msg = (
                    f"token-budget estimate {total_est} > budget "
                    f"{args.token_budget} (prompt ~{prompt_tokens}t + "
                    f"files ~{files_tokens_est}t / {len(visible_files)} "
                    f"files visible). Consider narrower --include-dirs "
                    f"<path,...> or extend .consultignore."
                )
                if args.fail_on_large:
                    print(f"error: consult: {msg}", file=sys.stderr)
                    return 14
                if not args.confirm_large:
                    print(f"WARNING: consult: {msg}", file=sys.stderr)

            # wl:2026-06-05-03 SECONDARY auto-fallback: backend invoke is
            # wrapped in a retry-once loop. The retry fires ONLY when:
            #   - the exception is a timeout-class <Backend>Unavailable
            #     (substring "timed out after" in exc.reason)
            #   - --auto-fallback was passed (opt-in; default OFF)
            #   - the pre-flight auto-narrow did NOT already fire
            #     (auto_narrow_derived empty)
            #   - frontmatter yields a non-trivial derivation
            # Non-timeout failures + ResponseParseError + codex
            # NotImplementedError all flow through the existing
            # diagnostic + return paths unchanged.
            auto_fallback_attempted = False
            parsed = None
            for _invoke_attempt in range(2):
                try:
                    parsed = consult_mod.invoke_backend(
                        args.backend,
                        prompt=assembled,
                        model=model,
                        include_dirs=include_dirs,
                        timeout_s=args.timeout,
                        gemini_bin=args.gemini_bin,
                        agy_bin=args.agy_bin,
                        output_schema=(
                            output_schema
                            if isinstance(output_schema, dict)
                            else None
                        ),
                    )
                    break  # success — exit retry loop
                except (consult_mod.GeminiUnavailable,
                        consult_mod.AgyUnavailable) as exc:
                    is_gemini = isinstance(
                        exc, consult_mod.GeminiUnavailable,
                    )
                    is_timeout = "timed out after" in exc.reason

                    # Retry decision: timeout + opt-in + not-yet-narrowed
                    if (is_timeout and args.auto_fallback
                            and not auto_fallback_attempted
                            and not auto_narrow_derived):
                        derived = consult_mod._auto_narrow_include_dirs(
                            target_fm,
                        )
                        if derived:
                            narrowed = [
                                f for f in visible_files
                                if any(
                                    f == d or f.startswith(d + "/")
                                    for d in derived
                                )
                            ]
                            if narrowed:
                                include_dirs = [
                                    str(repo / d) for d in derived
                                ]
                                visible_files = narrowed
                                auto_narrow_derived = derived
                                auto_fallback_attempted = True
                                print(
                                    f"[auto-fallback] consult: "
                                    f"{args.backend} backend subprocess "
                                    f"timed out after {args.timeout}s; "
                                    f"this is likely token-budget "
                                    f"overflow. Retrying once with "
                                    f"frontmatter-derived narrow scope "
                                    f"include_dirs={derived} from target "
                                    f"scope "
                                    f"{target_fm.get('scope', '<none>')!r}"
                                    f" / type "
                                    f"{target_fm.get('type', '<none>')!r}"
                                    f".",
                                    file=sys.stderr,
                                )
                                continue  # retry with narrowed scope

                    # Not retrying — emit (enriched) diagnostic + return.
                    tmp_path = (
                        consult_mod.write_fallback_response_template(
                            persona_slug=args.persona,
                            persona_meta=persona_meta,
                            target_id=args.target,
                            assembled_prompt=exc.assembled_prompt,
                        )
                    )
                    diagnostic_prefix = ""
                    if is_timeout:
                        # SECONDARY diagnostic enrichment (charter §4.2):
                        # identify the timeout as likely token-budget
                        # overflow + surface tailored next-step guidance
                        # based on which path the operator is on.
                        hints = [
                            f"[consult] backend subprocess timed out "
                            f"after {args.timeout}s; this is likely "
                            f"token-budget overflow (pre-flight "
                            f"estimate={total_est}t vs budget="
                            f"{args.token_budget}t)."
                        ]
                        if auto_fallback_attempted:
                            hints.append(
                                f"[consult] --auto-fallback retried "
                                f"with derived narrow scope "
                                f"{auto_narrow_derived} and still "
                                f"timed out; raise --timeout further "
                                f"(currently {args.timeout}s) or pass "
                                f"an explicit narrower --include-dirs."
                            )
                        elif (args.include_dirs is not None
                              and args.include_dirs != ""):
                            hints.append(
                                f"[consult] explicit --include-dirs="
                                f"{args.include_dirs!r} was scoped too "
                                f"wide for the backend timeout; "
                                f"re-invoke with a narrower subset, or "
                                f"omit --include-dirs to enable the "
                                f"auto-narrow heuristic."
                            )
                        elif not args.auto_fallback:
                            hints.append(
                                f"[consult] pass --auto-fallback to "
                                f"retry once with frontmatter-derived "
                                f"narrow scope, or raise --timeout."
                            )
                        diagnostic_prefix = "\n".join(hints) + "\n"
                    backend_diag_label = (
                        "gemini-unavailable" if is_gemini
                        else "agy-unavailable"
                    )
                    print(
                        f"{diagnostic_prefix}"
                        f"{backend_diag_label}: {exc.reason}\n"
                        f"fallback-prompt-file: {tmp_path}\n"
                        f"(skill layer: prompt operator Y/n; on Y, "
                        f"write the local-CC response to a JSON file "
                        f"then invoke `consult-with-response "
                        f"{args.persona} {args.target} "
                        f"--response-from-file <path>`)",
                        file=sys.stderr,
                    )
                    return 11 if is_gemini else 15
                except consult_mod.GeminiResponseParseError as exc:
                    tmp_path = (
                        consult_mod.write_fallback_response_template(
                            persona_slug=args.persona,
                            persona_meta=persona_meta,
                            target_id=args.target,
                            assembled_prompt=assembled,
                        )
                    )
                    print(
                        f"gemini-response-parse-error: {exc}\n"
                        f"fallback-prompt-file: {tmp_path}\n"
                        f"(skill layer: prompt operator Y/n)",
                        file=sys.stderr,
                    )
                    return 12
                except consult_mod.AgyResponseParseError as exc:
                    tmp_path = (
                        consult_mod.write_fallback_response_template(
                            persona_slug=args.persona,
                            persona_meta=persona_meta,
                            target_id=args.target,
                            assembled_prompt=assembled,
                        )
                    )
                    print(
                        f"agy-response-parse-error: {exc}\n"
                        f"fallback-prompt-file: {tmp_path}\n"
                        f"(skill layer: prompt operator Y/n)",
                        file=sys.stderr,
                    )
                    return 16
                except NotImplementedError as exc:
                    # cohort R: codex backend stub (wl:2026-06-04-03)
                    print(
                        f"backend-not-implemented: {exc}",
                        file=sys.stderr,
                    )
                    return 17
            # parsed is now bound (the success path `break`-ed out of
            # the retry loop; every non-success path `return`-ed).
            assert parsed is not None  # type-narrowing for the caller
        else:  # consult-with-response
            try:
                parsed = json.loads(
                    Path(args.response_from_file).read_text(encoding="utf-8"),
                )
            except (json.JSONDecodeError, OSError) as exc:
                print(f"error: --response-from-file: {exc}", file=sys.stderr)
                return 2
            if not isinstance(parsed, dict):
                print(
                    "error: response file did not parse as a JSON object",
                    file=sys.stderr,
                )
                return 2
            review_model = args.model

        # Cohort GG fix #4: surface the backend identity to the
        # provenance marker. The primary path carries args.backend
        # (gemini/agy/codex); the consult-with-response fallback path
        # records "claude-code" since the local CC is the answering
        # backend (matches the FALLBACK_MODEL convention).
        if args.command == "consult":
            backend_for_provenance = args.backend
            agy_bin_for_provenance = args.agy_bin
        else:
            backend_for_provenance = "claude-code"
            agy_bin_for_provenance = "agy"

        try:
            path = consult_mod.record_consult_review(
                repo_root=repo,
                persona_slug=args.persona,
                persona_meta=persona_meta,
                target_id=args.target,
                target_fm=target_fm,
                parsed_response=parsed,
                model=review_model,
                title=args.title,
                scope=args.scope,
                author=args.author,
                owner_user=args.owner_user,
                linked_msg_ids=list(args.linked_msg_ids or []),
                linked_decisions=_split_csv(args.linked_decisions),
                supersedes=args.supersedes,
                backend=backend_for_provenance,
                agy_bin=agy_bin_for_provenance,
            )
        except (ValueError, validators.ValidationError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        print(path)
        return 0

    if args.command == "consult-supersede":
        repo = Path(args.repo_root) if args.repo_root else Path.cwd()
        try:
            path = consult_mod.supersede_review(
                repo_root=repo,
                old_id=args.old_id,
                new_id=args.new_id,
                rationale=args.rationale,
                by_seat=args.by_seat,
            )
        except (FileNotFoundError, ValueError,
                validators.ValidationError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        print(path)
        return 0

    if args.command == "re-index":
        repo = Path(args.repo_root) if args.repo_root else Path.cwd()
        if args.kind == "all":
            refreshed: list[str] = []
            skipped: list[str] = []
            for kind in _REINDEX_KINDS:
                if _do_reindex(kind, repo):
                    refreshed.append(kind)
                else:
                    skipped.append(kind)
            print(f"refreshed: {', '.join(refreshed) or '(none)'}")
            if skipped:
                print(f"skipped (no dir): {', '.join(skipped)}", file=sys.stderr)
        else:
            if not _do_reindex(args.kind, repo):
                print(
                    f"error: no directory at "
                    f"{repo / _REINDEX_KINDS[args.kind][0]}",
                    file=sys.stderr,
                )
                return 2
            print(f"refreshed: {args.kind}")
        return 0

    if args.command == "decisions-pending":
        repo = Path(args.repo_root) if args.repo_root else Path.cwd()
        entries = pending_views.list_pending_decisions(repo, args.seat)
        if args.json:
            sys.stdout.write(json.dumps(entries, indent=2, default=str) + "\n")
        else:
            sys.stdout.write(pending_views.format_text(
                entries, kind_label="Decisions", seat=args.seat,
            ))
        return 0

    if args.command == "dispatches-pending":
        repo = Path(args.repo_root) if args.repo_root else Path.cwd()
        entries = pending_views.list_pending_dispatches(repo, args.seat)
        if args.json:
            sys.stdout.write(json.dumps(entries, indent=2, default=str) + "\n")
        else:
            sys.stdout.write(pending_views.format_text(
                entries, kind_label="Standing-dispatches", seat=args.seat,
            ))
        return 0

    if args.command == "sprint-status":
        repos = args.repos if args.repos else [str(Path.cwd())]
        state = sprint_state_mod.collect_cross_repo(
            repos, args.sprint_id, commit_limit=args.commit_limit,
        )
        if args.json:
            sys.stdout.write(sprint_state_mod.to_json_str(state) + "\n")
        else:
            sys.stdout.write(
                sprint_state_mod.format_text(state, detail=args.detail)
            )
        return 0

    if args.command == "aging":
        import handoff_aging as _aging_mod
        repo = Path(args.repo_root) if args.repo_root else Path.cwd()
        try:
            summary = _aging_mod.run_aging_policy(
                repo,
                dry_run=args.dry_run,
                strategy_override=args.strategy,
            )
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        if args.json:
            sys.stdout.write(json.dumps(summary, indent=2) + "\n")
        else:
            lines = [
                f"handoff-aging: strategy={summary['strategy']}"
                f"{' (dry-run)' if summary['dry_run'] else ''}",
                f"  detected={summary['detected']} "
                f"archived={summary['archived']} "
                f"merged={summary['merged']} "
                f"deleted={summary['deleted']}",
            ]
            sys.stdout.write("\n".join(lines) + "\n")
        return 0

    if args.command == "validate":
        repo = Path(args.repo_root) if args.repo_root else Path.cwd()
        warnings = validate_mod.run_checks(
            repo,
            mtime_cutoff=args.mtime_cutoff,
            only_check=args.check,
            end_sprint_id=args.sprint,
        )
        if warnings:
            sys.stderr.write(validate_mod.format_warnings(warnings))
            if args.strict:
                # §4.7 carve-out: only non-suppressed records contribute
                # to non-zero exit. Records demoted via the
                # ``[[validator.ignore]]`` file (``suppressed_by`` set)
                # are filtered out of the strict-error set per D-WL-12.
                if validate_mod.strict_exit_warnings(warnings):
                    return 1
        return 0

    if args.command == "install-codex-mcp-block":
        target = Path(args.target).resolve()
        if not target.is_dir():
            sys.stderr.write(
                f"install-codex-mcp-block: --target {target} is not a directory\n"
            )
            return 2
        wl_bin = (
            Path(args.workshop_lite_bin).resolve()
            if args.workshop_lite_bin
            else target / "bin" / "wl-mcp"
        )
        cfg_path = target / ".codex" / "config.toml"
        new_text, action = _install_codex_mcp_block(
            cfg_path, wl_bin, approval_mode=args.approval_mode,
        )
        if args.dry_run:
            sys.stdout.write(
                f"install-codex-mcp-block [DRY-RUN]: would {action} "
                f"in {cfg_path}\n"
            )
            if action != "noop":
                sys.stdout.write("--- would write:\n")
                sys.stdout.write(new_text)
                if not new_text.endswith("\n"):
                    sys.stdout.write("\n")
                sys.stdout.write("--- end\n")
            return 0
        if action == "noop":
            sys.stdout.write(
                f"install-codex-mcp-block: {cfg_path} already canonical (no change)\n"
            )
            return 0
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        cfg_path.write_text(new_text, encoding="utf-8")
        sys.stdout.write(
            f"install-codex-mcp-block: {action} in {cfg_path}\n"
        )
        return 0

    if args.command == "state-digest":
        # WL.29 D1: state-digest CLI subcommand. Factors render_digest
        # from .claude/hooks/state_digest.py and applies the WL.29 D1
        # mode-specific framing per charter §2 D1 axes.
        repo = Path(args.repo_root) if args.repo_root else Path.cwd()
        text = state_digest_mod.render_digest(
            repo, current_seat=args.current_seat,
        )
        text = state_digest_mod.format_for_mode(text, args.output_mode)
        sys.stdout.write(text)
        return 0

    if args.command == "emit-pack-payload":
        # issue 2026-06-10-02: WL authors the adapter-neutral Layer-C pack
        # payload; the render seam consumes the YAML on stdout. HR-1: no
        # file write here.
        persona_dims = {
            k: v
            for k, v in (
                ("reasoning", args.persona_reasoning),
                ("register", args.persona_register),
                ("conflict", args.persona_conflict),
            )
            if v is not None
        }
        payload = workshop_lite_pack_mod.build_pack_payload(
            adapter=args.adapter,
            include_evidence_obligation=not args.no_evidence_obligation,
            include_memory_scope=not args.no_memory_scope,
            persona_dimensions=persona_dims or None,
            managed_block=args.managed_block,
        )
        sys.stdout.write(workshop_lite_pack_mod.to_yaml(payload))
        return 0

    if args.command == "install-codex-content":
        # WL.29 D2: composes 5 emission categories per charter §2 D2 +
        # chunk-0 PG-2.1/2.2/2.3/2.4 dispositions. Subsumes
        # install-codex-mcp-block per @plan Option B ruling.
        target = Path(args.target).resolve()
        if not target.is_dir():
            sys.stderr.write(
                f"install-codex-content: --target {target} is not a directory\n"
            )
            return 2
        wl_bin = (
            Path(args.workshop_lite_bin).resolve()
            if args.workshop_lite_bin
            else target / "bin" / "wl-mcp"
        )
        user_config_path = (
            Path(args.user_config_path).expanduser().resolve()
            if args.user_config_path
            else (Path.home() / ".codex" / "config.toml")
        )

        plan = codex_host_content_mod.plan_install(
            target,
            wl_bin=wl_bin,
            user_config_path=user_config_path,
            mcp_block_helper=_install_codex_mcp_block,
        )

        if args.dry_run:
            sys.stdout.write(
                f"install-codex-content [DRY-RUN]: {len(plan)} steps planned "
                f"for {target}\n"
            )
            for step in plan:
                sys.stdout.write(
                    f"  - {step['kind']:30s} {step['action']:20s} "
                    f"{step['path']}\n"
                )
            return 0

        for step in plan:
            codex_host_content_mod.apply_install_step(step)
            if step["action"] != "noop":
                sys.stdout.write(
                    f"install-codex-content: {step['kind']} "
                    f"{step['action']} in {step['path']}\n"
                )
        return 0

    if args.command == "install-workshop-lite-content":
        # WL.30 D1+D2: propagates the WL substrate content set to a
        # consumer repo per chunk-0 ratify msg-d91261e535ed bindings
        # (dynamic discovery + per-file-class drift policy).
        target = Path(args.target).resolve()
        if not target.is_dir():
            sys.stderr.write(
                f"install-workshop-lite-content: --target {target} "
                f"is not a directory\n"
            )
            return 2

        if args.source:
            source = Path(args.source).resolve()
        else:
            source = (
                workshop_lite_content_mod.resolve_workshop_lite_source_root()
            )
            if source is None:
                sys.stderr.write(
                    "install-workshop-lite-content: could not auto-detect "
                    "the workshop-lite source root (no ancestor with "
                    ".claude/scripts/dev-mgmt/ + bin/wl + docs/conventions/ "
                    "found within pyproject/.git anchor). Pass --source "
                    "explicitly.\n"
                )
                return 2
            # Verifier M13 amend: surface the auto-detected source path
            # to stderr so operators on a downstream-adopted consumer
            # (which itself has the 3 substrate-witnesses) get explicit
            # confirmation of which substrate they're propagating from.
            # Suppressed when --source is passed explicitly.
            sys.stderr.write(
                f"install-workshop-lite-content: auto-detected source "
                f"root at {source}; pass --source explicitly if this is "
                f"not the workshop-lite upstream you intended to "
                f"propagate from.\n"
            )

        if not source.is_dir():
            sys.stderr.write(
                f"install-workshop-lite-content: --source {source} "
                f"is not a directory\n"
            )
            return 2

        if target == source:
            sys.stderr.write(
                f"install-workshop-lite-content: --target == --source "
                f"({target}) — refusing self-install (would no-op or "
                f"corrupt source).\n"
            )
            return 2

        plan = workshop_lite_content_mod.plan_install(
            target,
            source=source,
            accept_drift=args.accept_drift,
        )

        if args.dry_run:
            non_noop = [s for s in plan if s["action"] != "noop"]
            sys.stdout.write(
                f"install-workshop-lite-content [DRY-RUN]: "
                f"{len(plan)} steps planned ({len(non_noop)} non-noop) "
                f"for target={target} source={source}\n"
            )
            for step in plan:
                if step["action"] == "noop":
                    continue
                sys.stdout.write(
                    f"  - {step['action']:18s} {step['kind']:60s} "
                    f"{step['target_path']}\n"
                )
            if workshop_lite_content_mod.plan_has_blocking_symlinks(plan):
                sym_steps = [
                    s for s in plan if s["action"] == "symlink-refuse"
                ]
                sys.stdout.write(
                    f"\nSYMLINK PATH-COMPONENT REFUSE on {len(sym_steps)} "
                    f"path(s). Refusing to write through symlinks in the "
                    f"target path (file-level OR parent-dir OR resolved-"
                    f"outside-target). `unlink` each path explicitly if "
                    f"you want a regular file there (--accept-drift does "
                    f"NOT bypass):\n"
                )
                for s in sym_steps:
                    reason = (
                        s.get("symlink_reason")
                        or s.get("symlink_target")
                        or "?"
                    )
                    sys.stdout.write(
                        f"    refuse: {s['target_path']} ({reason})\n"
                    )
            if workshop_lite_content_mod.plan_has_blocking_drift(plan):
                drift_files = [
                    str(s["target_path"]) for s in plan
                    if s["action"] == "drift-refuse"
                ]
                sys.stdout.write(
                    f"\nDRIFT DETECTED on {len(drift_files)} CLASS-A "
                    f"file(s). Pre-existing hand-edits would be "
                    f"overwritten. Pick per-file remediation:\n"
                    f"  (a) revert target file(s) to canonical → re-run "
                    f"WITHOUT --accept-drift\n"
                    f"  (b) cherry-pick consumer changes into workshop-lite "
                    f"upstream → re-run\n"
                    f"  (c) re-run WITH --accept-drift (destructive; "
                    f"acknowledges intent to overwrite)\n"
                )
                for f in drift_files:
                    sys.stdout.write(f"    drift: {f}\n")
            # Codex skill mirror (Agent Skills adoption Phase-1): planned
            # .codex/skills/<name>/SKILL.md emissions for the portable subset.
            wlc = workshop_lite_content_mod
            portable = wlc.portable_skill_dirs(source)
            codex_planned = [
                (sd, wlc.plan_codex_copy(
                    sd, target, accept_drift=args.accept_drift,
                ))
                for sd in portable
            ]
            codex_writes = [
                (sd, s) for sd, s in codex_planned if s["action"] != "noop"
            ]
            sys.stdout.write(
                f"\nCODEX SKILL MIRROR [DRY-RUN]: {len(portable)} portable "
                f"skill(s); {len(codex_writes)} .codex copy step(s) "
                f"(non-portable excluded: "
                f"{', '.join(sorted(wlc.NON_PORTABLE_SKILLS))}).\n"
            )
            for sd, s in codex_planned:
                if s["action"] == "noop":
                    continue
                sys.stdout.write(
                    f"  - {s['action']:18s} codex-skill:{sd.name:24s} "
                    f"{s['target_path']}\n"
                )
            return 0

        # Apply mode: refuse if blocking symlink boundary violation
        # (verifier M16 + M18). Symlinks always refuse — --accept-drift
        # does NOT bypass this check.
        if workshop_lite_content_mod.plan_has_blocking_symlinks(plan):
            sym_steps = [
                s for s in plan if s["action"] == "symlink-refuse"
            ]
            sys.stderr.write(
                f"install-workshop-lite-content: REFUSING to write "
                f"through {len(sym_steps)} symlinked path(s). "
                f"Symlinks anywhere in the target path (file-level OR "
                f"parent-dir OR resolved-outside-target) are not "
                f"followed — `unlink` each path explicitly if you "
                f"want a regular file there (--accept-drift does NOT "
                f"bypass):\n"
            )
            for s in sym_steps:
                reason = (
                    s.get("symlink_reason")
                    or s.get("symlink_target")
                    or "?"
                )
                sys.stderr.write(
                    f"  refuse: {s['target_path']} ({reason})\n"
                )
            return 4

        # Apply mode: refuse if blocking drift (unless --accept-drift
        # already converted them to overwrite-drift steps).
        if workshop_lite_content_mod.plan_has_blocking_drift(plan):
            drift_files = [
                str(s["target_path"]) for s in plan
                if s["action"] == "drift-refuse"
            ]
            sys.stderr.write(
                f"install-workshop-lite-content: REFUSING to overwrite "
                f"{len(drift_files)} hand-edited CLASS-A file(s). "
                f"Pick remediation:\n"
                f"  (a) revert target file(s) to canonical → re-run\n"
                f"  (b) cherry-pick consumer changes into workshop-lite "
                f"upstream → re-run\n"
                f"  (c) re-run WITH --accept-drift (destructive)\n"
            )
            for f in drift_files:
                sys.stderr.write(f"  drift: {f}\n")
            return 3

        # Codex skill mirror (Phase-1): plan the .codex copies FIRST so a
        # blocking drift/symlink refuses the WHOLE install before any write,
        # matching the CLASS-A pre-write discipline.
        wlc = workshop_lite_content_mod
        portable_dirs = wlc.portable_skill_dirs(source)
        codex_planned = [
            (sd, wlc.plan_codex_copy(
                sd, target, accept_drift=args.accept_drift,
            ))
            for sd in portable_dirs
        ]
        codex_blocking = [
            (sd, s) for sd, s in codex_planned
            if s["action"] in {"drift-refuse", "symlink-refuse"}
        ]
        if codex_blocking:
            sys.stderr.write(
                f"install-workshop-lite-content: REFUSING codex skill "
                f"mirror — {len(codex_blocking)} .codex/skills copy(ies) "
                f"would overwrite hand-edited content or write through a "
                f"symlink. Resolve per-file (revert / --accept-drift for "
                f"drift; unlink for symlink) and re-run:\n"
            )
            for sd, s in codex_blocking:
                reason = s.get("symlink_reason") or s["action"]
                sys.stderr.write(
                    f"  refuse: {s['target_path']} ({reason})\n"
                )
            return 3

        applied = 0
        for step in plan:
            if step["action"] in {"noop", "skip-malformed"}:
                continue
            workshop_lite_content_mod.apply_install_step(step)
            sys.stdout.write(
                f"install-workshop-lite-content: {step['action']} "
                f"{step['kind']} in {step['target_path']}\n"
            )
            applied += 1
        sys.stdout.write(
            f"install-workshop-lite-content: {applied} step(s) applied "
            f"({len(plan) - applied} noop).\n"
        )

        # Apply the codex skill mirror via the shared emit_codex_copy writer
        # (cto v3-3228 — the same Path-returning writer the Phase-4
        # /skill-port skill calls). Only non-noop planned steps are written;
        # noop steps (already byte-identical / consumer-owned present) skip.
        codex_written = 0
        codex_noop = 0
        for sd, s in codex_planned:
            if s["action"] == "noop":
                codex_noop += 1
                continue
            dest = wlc.emit_codex_copy(sd, target)
            codex_written += 1
            sys.stdout.write(
                f"install-workshop-lite-content: {s['action']} "
                f"codex-skill:{sd.name} in {dest}\n"
            )

        # Install-time byte-equality assertion (.claude vs .codex SKILL.md).
        ineqs = wlc.find_skill_body_inequalities(target)
        if ineqs:
            sys.stderr.write(
                f"install-workshop-lite-content: BYTE-EQUALITY ASSERTION "
                f"FAILED on {len(ineqs)} skill(s) — .codex body diverges "
                f"from .claude body:\n"
            )
            for m in ineqs:
                sys.stderr.write(
                    f"  mismatch: {m['skill']} ({m['reason']})\n"
                )
            return 5

        # skills-ref validate wiring (external tool; surface gap if absent).
        codex_skill_dirs = [
            target / ".codex" / "skills" / sd.name for sd in portable_dirs
        ]
        sref = wlc.run_skills_ref_validate(codex_skill_dirs)
        if not sref["available"]:
            sys.stderr.write(
                f"install-workshop-lite-content: skills-ref gap — "
                f"{sref['gap']}\n"
            )
        elif sref["failures"]:
            sys.stderr.write(
                f"install-workshop-lite-content: skills-ref validate FAILED "
                f"on {len(sref['failures'])} skill dir(s):\n"
            )
            for res in sref["results"]:
                if res["returncode"] != 0:
                    sys.stderr.write(
                        f"  invalid: {res['dir']} (rc={res['returncode']}) "
                        f"{res['output']}\n"
                    )
            return 6

        codex_total = len(
            list((target / ".codex" / "skills").glob("*/SKILL.md"))
        )
        sys.stdout.write(
            f"install-workshop-lite-content: codex skill mirror — "
            f"{codex_written} written, {codex_noop} noop; target "
            f".codex/skills now has {codex_total} skill(s). Byte-equality "
            f"asserted; skills-ref "
            f"{'OK' if sref['available'] else 'UNAVAILABLE (gap surfaced)'}."
            f"\n"
        )
        return 0

    if args.command == "record-workflow":
        path = entities.record_workflow(
            title=args.title,
            stages=json.loads(args.stages_json),
            author=args.author,
            status=args.status,
            library_layer=args.library_layer,
            is_default=args.is_default,
            supersedes=args.supersedes,
            linked_decisions=_split_csv(args.linked_decisions),
            owner_user=args.owner_user,
            body=args.body,
            repo_root=Path(args.repo_root) if args.repo_root else None,
        )
        print(path)
        return 0

    if args.command == "record-role-set":
        path = entities.record_role_set(
            title=args.title,
            roles=json.loads(args.roles_json),
            author=args.author,
            sod_predicates=json.loads(args.sod_predicates_json),
            per_stage_markers=json.loads(args.per_stage_markers_json),
            status=args.status,
            library_layer=args.library_layer,
            is_default=args.is_default,
            supersedes=args.supersedes,
            owner_user=args.owner_user,
            body=args.body,
            repo_root=Path(args.repo_root) if args.repo_root else None,
        )
        print(path)
        return 0

    if args.command == "raise-block-signal":
        path = entities.raise_block_signal(
            blocked_subject=args.blocked_subject,
            waits_on=args.waits_on,
            klass=args.klass,
            created_by=args.created_by,
            status=args.status,
            deadline=args.deadline,
            ttl=args.ttl,
            inferred_by=args.inferred_by,
            body=args.body,
            repo_root=Path(args.repo_root) if args.repo_root else None,
        )
        print(path)
        return 0

    if args.command == "write-resume-ledger":
        path = entities.write_resume_ledger(
            worker=args.worker,
            in_flight_state=args.in_flight_state,
            next_actions=json.loads(args.next_actions_json),
            author=args.author,
            canonical_pointer_ref=args.canonical_pointer_ref,
            supersedes=args.supersedes,
            owner_user=args.owner_user,
            body=args.body,
            repo_root=Path(args.repo_root) if args.repo_root else None,
        )
        print(path)
        return 0

    if args.command == "write-canonical-pointer":
        path = entities.write_canonical_pointer(
            names=args.names,
            points_to=args.points_to,
            updated_by=args.updated_by,
            owner_user=args.owner_user,
            body=args.body,
            repo_root=Path(args.repo_root) if args.repo_root else None,
        )
        print(path)
        return 0

    if args.command == "migrate-tasks":
        repo_root = Path(args.repo_root) if args.repo_root else None
        if args.sprint_id:
            sprints_dir = ledger_paths.compat_sprints_dir(repo_root)
            tasks_md = None
            for sub_dir in ("active", "archive"):
                cand = sprints_dir / sub_dir / f"sprint-{args.sprint_id}" / "tasks.md"
                if cand.exists():
                    tasks_md = cand
                    break
            if tasks_md is None:
                sys.stderr.write(
                    f"no tasks.md for sprint {args.sprint_id!r}\n"
                )
                return 1
            count = entities.migrate_tasks_md(tasks_md, sprint_id=args.sprint_id)
            print(f"{tasks_md}\t{count}")
        else:
            results = entities.migrate_all_tasks(repo_root)
            total = sum(results.values())
            for p, c in sorted(results.items()):
                print(f"{p}\t{c}")
            print(f"migrate-tasks: {total} line(s) migrated across {len(results)} file(s).")
        return 0

    return 2  # unreachable: argparse enforces required subcommand


if __name__ == "__main__":
    sys.exit(main())
