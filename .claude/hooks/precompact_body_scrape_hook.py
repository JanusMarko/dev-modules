"""Hook-layer driver for the PreCompact body-scrape synthesizer.

Imported by `pre-compact.sh`; performs the §5.1–§5.6 scrape steps,
calls the parley-agnostic library `precompact_body_scrape.synthesize_handoff_body`,
then writes the handoff via the existing `entities.record_handoff` and
patches the new frontmatter fields onto the resulting artifact.

This is the SHELL/PARLEY boundary — all parley CLI invocations live
here (NOT in the library). Library Hard Rule 1 preserved.

Hook discipline (Hard Rule 5 + D33): NEVER block compaction. On any
failure path (timeout, scrape error, library exception, write fail,
fs error) the script falls back to writing the existing empty-stub
body via `entities.record_handoff` (no body arg) — same behavior as
pre-existing pre-compact.sh. Exits 0 unconditionally on the caller
side.

Output discipline: stderr gets a single observability line
`pre-compact-body-scrape p99_ms=<N> status=<...>` for log scraping.
Nothing on stdout (compaction output channel is reserved).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Wire sys.path to find the dev-mgmt library + sibling state_digest.
_HERE = Path(__file__).resolve().parent
_LIB = _HERE.parent / "scripts" / "dev-mgmt"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import frontmatter as _fm  # noqa: E402
import entities  # noqa: E402
import index as _index  # noqa: E402
from state_digest import find_active_sprint  # noqa: E402
import precompact_body_scrape as pbs  # noqa: E402


# ---------------------------------------------------------------------------
# Config (sub-spec §7 + Hard Rule 3)
# ---------------------------------------------------------------------------


def _body_scrape_config(repo: Path) -> dict:
    """Read `[handoffs.body_scrape]` from the consolidated config.

    Defaults per sub-spec §7: enabled=False (opt-in), timeout_seconds=5.0,
    synthesizer='heuristic-v1'.
    """
    cfg = _index._load_workshop_lite_config(repo)
    out = {"enabled": False, "timeout_seconds": 5.0, "synthesizer": "heuristic-v1"}
    if not isinstance(cfg, dict):
        return out
    handoffs = cfg.get("handoffs")
    if not isinstance(handoffs, dict):
        return out
    section = handoffs.get("body_scrape")
    if not isinstance(section, dict):
        return out
    en = section.get("enabled")
    if isinstance(en, bool):
        out["enabled"] = en
    ts = section.get("timeout_seconds")
    if isinstance(ts, (int, float)) and ts > 0:
        out["timeout_seconds"] = float(ts)
    syn = section.get("synthesizer")
    if isinstance(syn, str) and syn:
        out["synthesizer"] = syn
    return out


# ---------------------------------------------------------------------------
# Cursor resolution (§5.1)
# ---------------------------------------------------------------------------


def _resolve_cursor(repo: Path) -> tuple[str | None, str]:
    """Return (since_msg_id, since_iso_ts) per §5.1.

    Primary: prior handoff's `since_msg_id`.
    Fallback: now() - 4h.
    """
    fallback_ts = (datetime.now(timezone.utc) - timedelta(hours=4)).isoformat()
    handoffs_dir = repo / "docs" / "handoffs"
    if not handoffs_dir.exists():
        return None, fallback_ts
    files = [
        p for p in handoffs_dir.glob("*.md")
        if p.name != "INDEX.md" and not p.name.startswith("INDEX-")
    ]
    if not files:
        return None, fallback_ts
    files.sort(key=lambda p: p.stem, reverse=True)
    for f in files:
        try:
            fm, _ = _fm.parse(f)
        except Exception:
            continue
        if not isinstance(fm, dict):
            continue
        msg_id = fm.get("since_msg_id")
        created = fm.get("created_at")
        if msg_id:
            return str(msg_id), str(created or fallback_ts)
    return None, fallback_ts


def _advance_cursor(parley_events: list[pbs.ParleyRow]) -> str:
    """Return the highest-msg-id observed in this window per §5.1
    chained-cursor convention. Sort by iso_ts DESC and take the first
    non-empty msg_id; fall back to a `now-ts:<iso>` sentinel when the
    parley_events list is empty or yields no usable msg_id.
    """
    if parley_events:
        rows = [p for p in parley_events if p.msg_id]
        if rows:
            rows.sort(key=lambda r: r.iso_ts or "", reverse=True)
            return rows[0].msg_id
    return "now-ts:" + datetime.now(timezone.utc).isoformat()


def _resolve_prior_handoff_id(repo: Path) -> str | None:
    """Return the id (filename stem) of the most-recent existing handoff,
    sorted by stem (consistent with _resolve_cursor's filename-encoded
    timestamp ordering). Returns None if no handoffs exist.

    Used by the flag-OFF cursor-chain populator (D6 contract — issue
    workshop-lite:2026-06-03-08): the NEW handoff being written needs
    `since_handoff_id` = prior handoff's id so the next-seat reconstruction
    walk has a stable starting point.
    """
    handoffs_dir = repo / "docs" / "handoffs"
    if not handoffs_dir.exists():
        return None
    files = [
        p for p in handoffs_dir.glob("*.md")
        if p.name != "INDEX.md" and not p.name.startswith("INDEX-")
    ]
    if not files:
        return None
    files.sort(key=lambda p: p.stem, reverse=True)
    return files[0].stem


def _flag_off_advance_cursor(prior_msg_id: str | None) -> str:
    """Flag-OFF cursor advancement for the new handoff's `since_msg_id`.

    Tries `parley get --since <prior> --limit 1 --json` to get the current
    chat-end msg-id (fastest cursor advance). Falls back to `now-ts:<iso>`
    sentinel when parley is absent, the call fails, or yields no msg-id.

    Per HR 1: this lives in the hook layer (parley-coupling allowed); the
    library helpers stay parley-agnostic. Tight 1.5s subprocess timeout
    so the hook stays well under the never-block discipline (HR 5).

    Issue workshop-lite:2026-06-03-08: pairs with _resolve_prior_handoff_id
    to populate the cursor-chain (D6 contract) in the flag-OFF default path.
    """
    if shutil.which("parley") is None:
        return "now-ts:" + datetime.now(timezone.utc).isoformat()
    args = ["parley", "get", "--limit", "1", "--json"]
    if prior_msg_id and not prior_msg_id.startswith("now-ts:"):
        args += ["--since", prior_msg_id]
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=1.5)
        if r.returncode != 0 or not r.stdout.strip():
            return "now-ts:" + datetime.now(timezone.utc).isoformat()
        try:
            data = json.loads(r.stdout)
        except Exception:
            return "now-ts:" + datetime.now(timezone.utc).isoformat()
        if isinstance(data, list) and data:
            item = data[-1] if isinstance(data[-1], dict) else None
            if item:
                advanced = item.get("msg_id") or item.get("id")
                if advanced:
                    return str(advanced)
    except Exception:
        pass
    return "now-ts:" + datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Git scrape (§5.2)
# ---------------------------------------------------------------------------


def _git_scrape(repo: Path, since_iso_ts: str, deadline: float) -> tuple[list[pbs.GitRow], str]:
    """Run git log + git status -s. Return (commits, status_short)."""
    if time.monotonic() > deadline:
        return [], ""
    commits: list[pbs.GitRow] = []
    try:
        r = subprocess.run(
            ["git", "log", f"--since={since_iso_ts}", "--format=%H|%an|%s|%cI"],
            cwd=str(repo), capture_output=True, text=True, timeout=2.0,
        )
        if r.returncode == 0:
            for line in r.stdout.splitlines():
                parts = line.split("|", 3)
                if len(parts) >= 3:
                    sha, author, subject = parts[0], parts[1], parts[2]
                    ts = parts[3] if len(parts) > 3 else ""
                    commits.append(pbs.GitRow(sha=sha, author=author, subject=subject, iso_ts=ts))
    except Exception:
        pass
    status_short = ""
    try:
        r = subprocess.run(
            ["git", "status", "-s"],
            cwd=str(repo), capture_output=True, text=True, timeout=2.0,
        )
        if r.returncode == 0:
            status_short = r.stdout.strip()
    except Exception:
        pass
    return commits, status_short


# ---------------------------------------------------------------------------
# Parley scrape (§5.3) — kinds-only filter; graceful skip if absent
# ---------------------------------------------------------------------------


# governance_input intentionally OMITTED per master §4.3 HIGH #3 amendment.
_PARLEY_KINDS = ("decision", "blocker_raised", "blocker_resolved", "epic_shipped")


def _parley_scrape(since_msg_id: str | None, deadline: float) -> list[pbs.ParleyRow]:
    if time.monotonic() > deadline:
        return []
    if shutil.which("parley") is None:
        return []
    args = ["parley", "get", "--limit", "100", "--kind", ",".join(_PARLEY_KINDS), "--json"]
    if since_msg_id:
        args += ["--since", since_msg_id]
    rows: list[pbs.ParleyRow] = []
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=2.0)
        if r.returncode != 0 or not r.stdout.strip():
            return []
        try:
            data = json.loads(r.stdout)
        except Exception:
            return []
        if not isinstance(data, list):
            return []
        for item in data:
            if not isinstance(item, dict):
                continue
            kind = str(item.get("kind") or "")
            # Defense-in-depth: re-filter even if `parley get --kind` honored.
            if kind not in _PARLEY_KINDS:
                continue
            body = str(item.get("body") or "")
            first_line = body.splitlines()[0] if body else ""
            rows.append(pbs.ParleyRow(
                msg_id=str(item.get("msg_id") or item.get("id") or ""),
                kind=kind,
                sender=str(item.get("from") or item.get("sender") or ""),
                body_first_line=first_line[:200],
                iso_ts=str(item.get("ts") or item.get("created_at") or ""),
            ))
    except Exception:
        return []
    return rows


# ---------------------------------------------------------------------------
# Entity walk (§5.4)
# ---------------------------------------------------------------------------


_INDEX_DIRS = ("decisions", "issues", "reviews", "dispatches", "wip", "epics")


def _entity_walk(repo: Path, since_iso_ts: str, deadline: float) -> dict[str, list[pbs.EntityRow]]:
    out: dict[str, list[pbs.EntityRow]] = {}
    for sub in _INDEX_DIRS:
        if time.monotonic() > deadline:
            break
        sub_dir = repo / "docs" / sub
        if not sub_dir.exists():
            continue
        rows: list[pbs.EntityRow] = []
        for entity_file in sub_dir.glob("*.md"):
            if entity_file.name == "INDEX.md":
                continue
            try:
                fm, _ = _fm.parse(entity_file)
            except Exception:
                continue
            if not isinstance(fm, dict):
                continue
            created = str(fm.get("created_at") or "")
            if since_iso_ts and created and created < since_iso_ts:
                continue
            rows.append(pbs.EntityRow(
                entity_type=sub,
                id=str(fm.get("id") or entity_file.stem),
                title=str(fm.get("title") or ""),
                status=str(fm.get("status") or ""),
                scope=str(fm.get("scope") or ""),
                severity=str(fm.get("severity") or ""),
                created_at=created,
            ))
        if rows:
            # Map dispatches → 'dispatches' (matches §5.7.3 sub-section).
            # wip → 'wip-claims' (matches the ScrapeResult contract).
            key = {"wip": "wip-claims"}.get(sub, sub)
            out[key] = rows
    return out


# ---------------------------------------------------------------------------
# Flag-OFF deterministic STUB body augmentation (wl:2026-06-03-07)
# ---------------------------------------------------------------------------
#
# Per HR #7 §1: this augmentation is non-judgment. Every operation is a
# deterministic function of the scrape inputs — no LLM, no classifier, no
# rule-ordering, no threshold heuristics, no selection-among-equals. The
# issue body's design-acceptance argument (`docs/issues/2026-06-03-07-*.md`
# §"Why this is non-judgment") justifies the no-eval-corpus gate.

_AUG_GIT_COMMIT_CAP = 10
_AUG_PARLEY_EVENT_CAP = 10
_AUG_ENTITY_ROWS_PER_TYPE_CAP = 10
_AUG_FLAG_OFF_DEADLINE_S = 3.0


def _git_branch(repo: Path) -> str:
    """Return current branch name via `git branch --show-current` (deterministic).

    Empty string on detached HEAD or git failure. Tight 1s subprocess timeout
    per HR #5 never-block discipline.
    """
    try:
        r = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=str(repo), capture_output=True, text=True, timeout=1.0,
        )
        if r.returncode == 0:
            return r.stdout.strip()
    except Exception:
        pass
    return ""


def _compose_stub_augmented_body(
    *,
    title: str,
    branch: str,
    git_rows: list[pbs.GitRow],
    git_status_short: str,
    parley_rows: list[pbs.ParleyRow],
    entity_walk: dict[str, list[pbs.EntityRow]],
) -> str:
    """Compose the flag-OFF STUB-augmented handoff body deterministically.

    Mechanical str.join over caller-supplied scrape inputs:
      - §1 Current state: branch + `git status -s` literal + capped git log dump
      - §2 Since last handoff: capped parley-events dump + per-type entity-walk
      - §3 What's next: preserved STUB "TBD" (judgment surface per HR #7)
      - §4 Notes: preserved STUB

    Caps (`_AUG_GIT_COMMIT_CAP` / `_AUG_PARLEY_EVENT_CAP` /
    `_AUG_ENTITY_ROWS_PER_TYPE_CAP`) are pre-fixed code constants, not
    runtime judgment. Order within each section is the order the
    underlying scrape primitive produced (no re-sort; deterministic).

    Pure function: same inputs → byte-identical output (cert axis #2).
    """
    lines: list[str] = [f"# {title}", ""]

    # §1 — Current state
    lines += ["## Current state", ""]
    if branch:
        lines.append(f"- Branch: `{branch}`")
    if git_status_short:
        lines += ["", "Working-tree (`git status -s`):", "", "```"]
        for status_line in git_status_short.splitlines():
            lines.append(status_line)
        lines.append("```")
    else:
        lines.append("- Working-tree: clean")
    lines.append("")
    capped_commits = git_rows[:_AUG_GIT_COMMIT_CAP]
    if capped_commits:
        lines += [
            f"Recent commits ({len(capped_commits)} of {len(git_rows)}"
            f"{'+ ' if len(git_rows) > _AUG_GIT_COMMIT_CAP else ''} in window):",
            "",
        ]
        for c in capped_commits:
            short_sha = c.sha[:8] if c.sha else ""
            author = f" (@{c.author})" if c.author else ""
            lines.append(f"- `{short_sha}` {c.subject}{author}")
    else:
        lines.append("(no commits in window)")
    lines.append("")

    # §2 — Since last handoff
    lines += ["## Since last handoff", ""]
    section_rendered_any = False

    capped_parley = parley_rows[:_AUG_PARLEY_EVENT_CAP]
    if capped_parley:
        section_rendered_any = True
        lines += [
            f"Parley events ({len(capped_parley)} of {len(parley_rows)}"
            f"{'+ ' if len(parley_rows) > _AUG_PARLEY_EVENT_CAP else ''}; "
            f"kinds: decision / blocker_raised / blocker_resolved / epic_shipped):",
            "",
        ]
        for p in capped_parley:
            sender = f" — {p.sender}" if p.sender else ""
            first_line = p.body_first_line or ""
            lines.append(f"- [{p.kind}] `{p.msg_id}`{sender}: {first_line}")
        lines.append("")

    for entity_type in ("decisions", "issues", "reviews", "dispatches", "wip-claims", "epics"):
        rows = entity_walk.get(entity_type) or []
        if not rows:
            continue
        section_rendered_any = True
        capped = rows[:_AUG_ENTITY_ROWS_PER_TYPE_CAP]
        header_label = entity_type.capitalize() if entity_type != "wip-claims" else "WIP-claims"
        lines += [
            f"Recent {header_label} ({len(capped)} of {len(rows)}"
            f"{'+ ' if len(rows) > _AUG_ENTITY_ROWS_PER_TYPE_CAP else ''}):",
            "",
        ]
        for r in capped:
            status_part = f" ({r.status})" if r.status else ""
            severity_part = f" [{r.severity}]" if r.severity else ""
            lines.append(f"- `{r.id}` — {r.title}{status_part}{severity_part}")
        lines.append("")

    if not section_rendered_any:
        lines.append("(no parley events or recent entities in window)")
        lines.append("")

    # §3 — What's next (preserved STUB; judgment surface gated by HR #7 + corpus)
    lines += [
        "## What's next",
        "",
        "TBD",
        "",
    ]

    # §4 — Notes (preserved STUB)
    lines += [
        "## Notes",
        "",
        "(auto-generated stub-augmented body; deterministic scrape only. "
        "`## What's next` is the judgment surface — replace with hand-authored "
        "content or enable [handoffs.body_scrape] for synthesizer output.)",
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Active sprint state (§5.5)
# ---------------------------------------------------------------------------


def _active_sprint_state(repo: Path) -> pbs.SprintState | None:
    found = find_active_sprint(repo)
    if not found:
        return None
    sprint_id, stage = found
    if not sprint_id:
        return None
    tasks_path = (
        repo / "docs" / "sprints" / "active" / f"sprint-{sprint_id}" / "tasks.md"
    )
    tasks: list[pbs.TaskRow] = []
    if tasks_path.exists():
        for line in tasks_path.read_text(encoding="utf-8").splitlines():
            ls = line.strip()
            if not ls.startswith("- ["):
                continue
            # Detect the 4-state marker.
            if ls.startswith("- [ ]"):
                status = "pending"
            elif ls.startswith("- [x]") or ls.startswith("- [X]"):
                status = "completed"
            elif ls.startswith("- [~]"):
                status = "in_progress"
            elif ls.startswith("- [!]"):
                status = "blocked"
            else:
                status = "pending"
            desc = ls.split("]", 1)[1].strip() if "]" in ls else ls
            # assignee parse: trailing "— @<seat>" or "@<seat>" anywhere.
            assignee = ""
            if "@" in desc:
                for tok in desc.split():
                    if tok.startswith("@") and len(tok) > 1:
                        assignee = tok[1:].rstrip(",.;)")
                        break
            tasks.append(pbs.TaskRow(description=desc, status=status, assignee=assignee))
    return pbs.SprintState(sprint_id=sprint_id, stage=stage or "execute", tasks=tasks)


# ---------------------------------------------------------------------------
# Cross-arc xrequests (§5.6)
# ---------------------------------------------------------------------------


def _xrequests(deadline: float) -> list[pbs.XreqRow]:
    if time.monotonic() > deadline:
        return []
    if shutil.which("parley") is None:
        return []
    try:
        r = subprocess.run(
            ["parley", "xrequest", "list", "--state", "open,accepted", "--json"],
            capture_output=True, text=True, timeout=2.0,
        )
        if r.returncode != 0 or not r.stdout.strip():
            return []
        try:
            data = json.loads(r.stdout)
        except Exception:
            return []
        if not isinstance(data, list):
            return []
        rows: list[pbs.XreqRow] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            rows.append(pbs.XreqRow(
                xreq_id=str(item.get("xreq_id") or item.get("id") or ""),
                domain_tag=str(item.get("domain_tag") or ""),
                state=str(item.get("state") or ""),
                expects_response=bool(item.get("expects_response", False)),
                ttl_remaining=str(item.get("ttl_remaining") or ""),
                from_seat=str(item.get("from") or ""),
                direction=str(item.get("direction") or ""),
            ))
        return rows
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Top-level orchestration
# ---------------------------------------------------------------------------


def _current_seat() -> str | None:
    """Detect the current seat via `parley whoami` if available.

    Returns None when parley is absent (degrades per Q-PCS-1).
    """
    if shutil.which("parley") is None:
        return None
    try:
        r = subprocess.run(
            ["parley", "whoami", "--json"],
            capture_output=True, text=True, timeout=1.0,
        )
        if r.returncode != 0 or not r.stdout.strip():
            return None
        try:
            data = json.loads(r.stdout)
        except Exception:
            return None
        if isinstance(data, dict):
            seat = data.get("seat") or data.get("member_id") or data.get("window_id")
            if seat:
                return str(seat)
    except Exception:
        return None
    return None


def _patch_frontmatter(target: Path, additions: dict) -> None:
    """Merge `additions` into the on-disk handoff frontmatter."""
    try:
        fm, body = _fm.parse(target)
    except Exception:
        return
    if not isinstance(fm, dict):
        return
    fm.update(additions)
    try:
        _fm.write(target, fm, body)
    except Exception:
        return


def _stderr(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", required=True)
    args = parser.parse_args()
    repo = Path(args.repo_root).resolve()

    cfg = _body_scrape_config(repo)
    started = time.monotonic()

    active = _active_sprint_state(repo)
    sprint_id = active.sprint_id if active else None
    stage = active.stage if active else None

    # Compose the canonical handoff-cli args (must mirror the legacy invocation
    # in pre-compact.sh so the FALLBACK path is bitwise-identical to today's
    # behavior).
    base_args = [
        "handoff",
        "--title", "Pre-compact snapshot",
        "--topic", "pre-compact-snapshot",
        "--trigger", "pre_compact",
        "--author", "@cc-hook",
        "--repo-root", str(repo),
    ]
    if sprint_id:
        base_args += ["--sprint-id", sprint_id, "--stage", stage or "execute"]

    if not cfg["enabled"]:
        # Flag OFF (default) — populate cursor-chain (wl:2026-06-03-08 D6
        # contract; LIGHTWEIGHT §6:514-566) AND attempt deterministic STUB
        # body augmentation (wl:2026-06-03-07): scrape git + parley + entity
        # walk under a 3s budget + compose mechanically (no synthesizer call,
        # no judgment, HR #7 §1 inapplicable per issue body's enumeration).
        #
        # On any scrape exception or deadline pass: fall through to the
        # legacy cursor-chain-only path (preserves HR #5 never-block + the
        # wl:2026-06-03-08 D6 contract bitwise-identical to pre-augmentation).
        prior_handoff_id = _resolve_prior_handoff_id(repo)
        prior_msg_id, prior_iso_ts = _resolve_cursor(repo)
        advanced_msg_id = _flag_off_advance_cursor(prior_msg_id)
        extra_args: list[str] = []
        if prior_handoff_id:
            extra_args += ["--since-handoff-id", prior_handoff_id]
        if advanced_msg_id:
            extra_args += ["--since-msg-id", advanced_msg_id]

        aug_deadline = started + _AUG_FLAG_OFF_DEADLINE_S
        aug_tmp = repo / ".claude" / "_pcbs_aug_body.tmp.md"
        aug_status = "skipped"
        try:
            branch = _git_branch(repo)
            git_rows, git_status_short = _git_scrape(repo, prior_iso_ts, aug_deadline)
            parley_rows = _parley_scrape(prior_msg_id, aug_deadline)
            entity_walk = _entity_walk(repo, prior_iso_ts, aug_deadline)
            if time.monotonic() > aug_deadline:
                aug_status = "timeout-fallback"
            else:
                body = _compose_stub_augmented_body(
                    title="Pre-compact snapshot",
                    branch=branch,
                    git_rows=git_rows,
                    git_status_short=git_status_short,
                    parley_rows=parley_rows,
                    entity_walk=entity_walk,
                )
                aug_tmp.parent.mkdir(parents=True, exist_ok=True)
                aug_tmp.write_text(body, encoding="utf-8")
                extra_args += ["--body-from-file", str(aug_tmp)]
                aug_status = "completed"
        except Exception:
            aug_status = "error-fallback"

        try:
            _invoke_handoff_cli(repo, base_args + extra_args)
            if aug_status == "completed":
                target = _most_recent_handoff(repo)
                if target is not None:
                    _patch_frontmatter(target, {
                        "body_augmentation": "deterministic-stub-v1",
                        "body_augmentation_status": "completed",
                    })
            elif aug_status in {"timeout-fallback", "error-fallback"}:
                target = _most_recent_handoff(repo)
                if target is not None:
                    _patch_frontmatter(target, {
                        "body_augmentation": "deterministic-stub-v1",
                        "body_augmentation_status": aug_status,
                    })
        finally:
            try:
                aug_tmp.unlink()
            except Exception:
                pass

        _stderr(
            f"pre-compact-body-scrape p99_ms={int((time.monotonic()-started)*1000)} "
            f"status=disabled cursor_chain=populated augmented={aug_status}"
        )
        return 0

    timeout_s = float(cfg["timeout_seconds"])
    deadline = started + timeout_s

    # Scrape (§5.1-5.6). Each step honors the deadline; on any
    # exception we capture-and-fallback (no compaction block).
    try:
        cursor_msg_id, cursor_iso_ts = _resolve_cursor(repo)
        git_rows, git_status_short = _git_scrape(repo, cursor_iso_ts, deadline)
        parley_rows = _parley_scrape(cursor_msg_id, deadline)
        entity_walk = _entity_walk(repo, cursor_iso_ts, deadline)
        xrequests = _xrequests(deadline)
        scrape = pbs.ScrapeResult(
            cursor_msg_id=cursor_msg_id,
            cursor_iso_ts=cursor_iso_ts,
            git_commits=git_rows,
            git_status_short=git_status_short,
            parley_events=parley_rows,
            entity_walk=entity_walk,
            active_sprint=active,
            xrequests=xrequests,
            git_since=cursor_iso_ts,
            parley_since=cursor_msg_id or "",
            entity_walk_since=cursor_iso_ts,
        )
    except Exception as exc:
        _invoke_handoff_cli(repo, base_args)
        # Find the just-written handoff and patch error-fallback frontmatter.
        target = _most_recent_handoff(repo)
        if target is not None:
            _patch_frontmatter(target, {
                "body_synthesizer": cfg["synthesizer"],
                "body_synthesizer_status": "error-fallback",
                "body_scrape_p99_ms": int((time.monotonic() - started) * 1000),
            })
        _stderr(f"pre-compact-body-scrape p99_ms={int((time.monotonic()-started)*1000)} status=error-fallback err={type(exc).__name__}")
        return 0

    # Deadline check: if scrape already burned the budget, fallback.
    remaining = max(0.001, deadline - time.monotonic())
    if remaining <= 0:
        _invoke_handoff_cli(repo, base_args)
        target = _most_recent_handoff(repo)
        if target is not None:
            _patch_frontmatter(target, {
                "body_synthesizer": cfg["synthesizer"],
                "body_synthesizer_status": "timeout-fallback",
                "body_scrape_p99_ms": int((time.monotonic() - started) * 1000),
            })
        _stderr(f"pre-compact-body-scrape p99_ms={int((time.monotonic()-started)*1000)} status=timeout-fallback")
        return 0

    seat = _current_seat()
    try:
        body, fm_add = pbs.synthesize_handoff_body(
            scrape=scrape,
            current_seat=seat,
            timeout_s=remaining,
            title="Pre-compact snapshot",
        )
    except Exception as exc:
        _invoke_handoff_cli(repo, base_args)
        target = _most_recent_handoff(repo)
        if target is not None:
            _patch_frontmatter(target, {
                "body_synthesizer": cfg["synthesizer"],
                "body_synthesizer_status": "error-fallback",
                "body_scrape_p99_ms": int((time.monotonic() - started) * 1000),
            })
        _stderr(f"pre-compact-body-scrape p99_ms={int((time.monotonic()-started)*1000)} status=error-fallback err={type(exc).__name__}")
        return 0

    # Write the body via a temp file passed to the CLI's --body-from-file.
    tmp = repo / ".claude" / "_pcbs_body.tmp.md"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    try:
        tmp.write_text(body, encoding="utf-8")
        invoked = _invoke_handoff_cli(repo, base_args + ["--body-from-file", str(tmp)])
        target = _most_recent_handoff(repo)
        if target is not None:
            # Stamp scrape window with cursor info if the synth didn't override.
            # Sub-spec §5.1 chained-cursor: the new handoff's since_msg_id
            # must advance to the cursor AT THIS compact moment so the NEXT
            # PreCompact picks up where THIS one left off. Use the highest
            # msg-id from this window's parley_events (sorted by iso_ts DESC);
            # fall back to a `now-ts` sentinel when no parley events landed.
            advanced_cursor = _advance_cursor(scrape.parley_events)
            fm_add.setdefault("since_msg_id", advanced_cursor)
            _patch_frontmatter(target, fm_add)
        status = fm_add.get("body_synthesizer_status", "completed")
        _stderr(f"pre-compact-body-scrape p99_ms={int((time.monotonic()-started)*1000)} status={status}")
    finally:
        try:
            tmp.unlink()
        except Exception:
            pass

    return 0


def _invoke_handoff_cli(repo: Path, args: list[str]) -> int:
    """Invoke the dev-mgmt CLI's handoff subcommand."""
    cli = repo / ".claude" / "scripts" / "dev-mgmt" / "cli.py"
    py = repo / ".venv" / "bin" / "python3"
    py_exe = str(py) if py.exists() else sys.executable
    try:
        r = subprocess.run(
            [py_exe, str(cli), *args],
            cwd=str(repo), capture_output=True, text=True, timeout=10.0,
        )
        return r.returncode
    except Exception:
        return 1


def _most_recent_handoff(repo: Path) -> Path | None:
    handoffs = repo / "docs" / "handoffs"
    if not handoffs.exists():
        return None
    files = [
        p for p in handoffs.glob("*.md")
        if p.name != "INDEX.md" and not p.name.startswith("INDEX-")
    ]
    if not files:
        return None
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0]


if __name__ == "__main__":
    sys.exit(main())
