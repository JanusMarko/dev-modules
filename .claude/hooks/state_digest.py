"""SessionStart state-digest helper (D31 + Q3).

Called by ``session-context.sh`` and also imported by ``pre-compact.sh``
for active-sprint detection. Reads ``docs/sprints/INDEX.md`` (Q3:
INDEX is source-of-truth, not ``ls`` of ``active/``) plus the most
recent decisions/handoffs/open-issues, and writes a brief markdown
digest to stdout (per D45 / Issue 2026-05-14-07: CC SessionStart
surfaces hook stdout into the new session's orientation context,
not stderr — Sprint 6 gate-7 empirical finding).

Parley-agnostic per CLAUDE.md Hard Rule 5 — this module never imports
or shells out to parley.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_LIB = _HERE.parent / "scripts" / "dev-mgmt"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

import frontmatter  # noqa: E402

try:
    import wip_claim as _wip_claim_mod  # noqa: E402
    import wip_claim_checks as _wip_claim_checks_mod  # noqa: E402
except Exception:  # pragma: no cover — defensive (Hard Rule 5)
    _wip_claim_mod = None
    _wip_claim_checks_mod = None

try:
    import dispatch as _dispatch_mod  # noqa: E402
except Exception:  # pragma: no cover — defensive (Hard Rule 5)
    _dispatch_mod = None


def _parse_index_rows(index_path: Path) -> list[dict[str, str]]:
    """Parse a markdown table INDEX.md into a list of header-keyed dicts."""
    if not index_path.exists():
        return []
    rows: list[dict[str, str]] = []
    headers: list[str] | None = None
    in_table = False
    for line in index_path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s.startswith("|"):
            in_table = False
            continue
        cells = [c.strip() for c in s.split("|")[1:-1]]
        if not cells:
            continue
        if not in_table:
            headers = cells
            in_table = True
            continue
        if set("".join(cells).strip()) <= set("-: "):
            continue  # separator row
        if headers is None or len(cells) != len(headers):
            continue
        rows.append(dict(zip(headers, cells)))
    return rows


def find_active_sprint(repo: Path) -> tuple[str, str] | None:
    """Return ``(sprint_id, stage)`` for the row whose Status='active'.

    Returns ``None`` if no row matches or the INDEX is missing.
    """
    rows = _parse_index_rows(repo / "docs" / "sprints" / "INDEX.md")
    for row in rows:
        if row.get("Status") == "active":
            return row.get("ID", ""), row.get("Stage", "")
    return None


def pending_tasks_count(repo: Path, sprint_id: str) -> int:
    """Count ``- [ ]`` lines in the active sprint's tasks.md."""
    if not sprint_id:
        return 0
    tasks = repo / "docs" / "sprints" / "active" / f"sprint-{sprint_id}" / "tasks.md"
    if not tasks.exists():
        return 0
    return sum(
        1 for line in tasks.read_text(encoding="utf-8").splitlines()
        if line.startswith("- [ ]")
    )


def recent_decisions(repo: Path, n: int = 3) -> list[str]:
    d = repo / "docs" / "decisions"
    if not d.exists():
        return []
    files = [p for p in d.glob("*.md") if p.name != "INDEX.md"]
    files.sort(key=lambda p: p.stem, reverse=True)
    return [p.stem for p in files[:n]]


def _first_n_lines(text: str, n: int = 25) -> str:
    lines = text.splitlines()
    if len(lines) <= n:
        return text
    return "\n".join(lines[:n])


def latest_handoff(repo: Path) -> dict[str, str] | None:
    """Return most recent handoff metadata + body excerpt + format.

    Skips files whose names look like legacy INDEX renames (INDEX-*.md);
    those are tracked separately and aren't entity files.
    """
    h = repo / "docs" / "handoffs"
    if not h.exists():
        return None
    files = [
        p for p in h.glob("*.md")
        if p.name != "INDEX.md" and not p.name.startswith("INDEX-")
    ]
    if not files:
        return None
    # Sort by mtime descending (matches maxai's existing pattern; robust against
    # filename schemes that don't sort lexicographically by date).
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    latest = files[0]
    try:
        fm, body = frontmatter.parse(latest)
        return {
            "slug": latest.stem,
            "format": "dev-mgmt",
            "topic": str(fm.get("topic") or "?"),
            "next_action": str(fm.get("next_action") or "?"),
            "excerpt": _first_n_lines(body, 25),
        }
    except Exception:
        # Legacy handoff (no frontmatter); show first 25 lines of the whole file.
        text = latest.read_text(encoding="utf-8")
        return {
            "slug": latest.stem,
            "format": "legacy",
            "topic": "?",
            "next_action": "?",
            "excerpt": _first_n_lines(text, 25),
        }


def latest_open_issue(repo: Path) -> dict[str, str] | None:
    i = repo / "docs" / "issues"
    if not i.exists():
        return None
    candidates: list[tuple[str, str]] = []
    for p in i.glob("*.md"):
        if p.name == "INDEX.md":
            continue
        try:
            fm, _ = frontmatter.parse(p)
        except Exception:
            continue
        if fm.get("status") == "open":
            candidates.append((p.stem, str(fm.get("severity") or "?")))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return {"slug": candidates[0][0], "severity": candidates[0][1]}


def _days_since(iso_ts: str | None) -> int | None:
    if not iso_ts:
        return None
    try:
        dt = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
    except ValueError:
        return None
    delta = datetime.now(timezone.utc) - dt
    return max(0, delta.days)


def _active_sprint_created_at(repo: Path, sprint_id: str) -> str | None:
    plan = repo / "docs" / "sprints" / "active" / f"sprint-{sprint_id}" / "plan.md"
    if not plan.exists():
        return None
    try:
        fm, _ = frontmatter.parse(plan)
    except Exception:
        return None
    val = fm.get("created_at")
    return str(val) if val else None


def _format_expires_delta(expires_iso: str, now: datetime) -> str:
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


def _load_dispatch_visual_budget(repo: Path) -> int:
    """Per sub-spec §7.1: pagination visual budget, default 10.

    Read from ``.claude/workshop-lite-config.toml`` ``[dispatches]
    visual_budget`` key. Failures degrade silently to the default
    (Hard Rule 5).
    """
    cfg_path = repo / ".claude" / "workshop-lite-config.toml"
    if not cfg_path.exists():
        return 10
    try:
        import tomllib
        cfg = tomllib.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception:
        return 10
    section = cfg.get("dispatches") if isinstance(cfg, dict) else None
    if isinstance(section, dict):
        val = section.get("visual_budget")
        if isinstance(val, int) and val > 0:
            return val
    return 10


def _annotate_dispatch_with_delivery_state(
    fm: dict, delivery_state: dict[tuple[str, str], str] | None,
    current_seat: str,
) -> str:
    """Return a short " (primitive #1 state: <s>)" suffix for a dispatch
    line, when delivery state is available for the current seat.

    Per sub-spec §10.1: composition is opportunistic. When parley is
    available and delivery_state was queried, annotate; otherwise
    degrade to entity-only display.

    Multi-msg union: when a dispatch links multiple msg-ids, surface
    the "most-progressed" state (acted_on > delivered > pending) for
    the current_seat across all msg-ids. The state enum per primitive
    #1 sub-spec §2.1: ``pending → delivered → acted_on | aborted``.
    """
    if not delivery_state or not current_seat:
        return ""
    msg_ids = [
        m for m in (fm.get("linked_msg_ids") or [])
        if isinstance(m, str) and m
    ]
    if not msg_ids:
        return ""
    _STATE_ORDER = {"aborted": 0, "pending": 1, "delivered": 2, "acted_on": 3}
    best_state: str | None = None
    best_rank = -1
    for mid in msg_ids:
        s = delivery_state.get((mid, current_seat))
        if not s:
            continue
        rank = _STATE_ORDER.get(s, -1)
        if rank > best_rank:
            best_rank = rank
            best_state = s
    if best_state is None:
        return ""
    return f" (primitive #1 state: {best_state})"


def render_standing_dispatch_section(
    repo: Path,
    *,
    current_seat: str | None,
    delivery_state: dict[tuple[str, str], str] | None = None,
) -> str:
    """Render the standing-dispatch section for the SessionStart digest.

    Per sub-spec §7: surface standing dispatches naming the current
    seat as recipient, in ``created_at ASC`` deterministic order. ALL
    matches shown — NO truncation, NO prioritization, NO relevance-
    scoring. Per sub-spec §7.1: pagination (not elision) past visual
    budget (default 10): first N rendered, footer cites overflow count.

    Anti-judgment-creep (sub-spec §3.2 + §7.1 + master MED #7
    amendment + Hard Rule 7): the surfacing rule is structurally
    deterministic — no graded behavioral disposition.

    D33 / Hard Rule 5: never blocks; failures degrade to a short stderr
    log and an empty rendered section. Parley-agnostic-at-base preserved:
    when ``current_seat`` is None (parley absent), the section is
    suppressed; when ``delivery_state`` is None (composition with
    primitive #1 unavailable), entity-only display.
    """
    if _dispatch_mod is None:
        return ""
    if current_seat is None:
        # Sub-spec §7 query: "which standing-dispatches name me as
        # recipient" — no current-seat = no seat-scoped surfacing.
        return ""
    try:
        for_seat = _dispatch_mod.load_dispatches_for_seat(repo, current_seat)
    except Exception as exc:  # pragma: no cover
        sys.stderr.write(
            f"[state_digest] standing-dispatch discovery failed: {exc}\n"
        )
        return ""
    if not for_seat:
        return ""

    visual_budget = _load_dispatch_visual_budget(repo)
    total = len(for_seat)
    visible = for_seat[:visual_budget]
    overflow = total - len(visible)

    out: list[str] = []
    out.append(f"## Standing dispatches (seat: {current_seat})")
    out.append("")
    for fm in visible:
        slug = fm.get("_slug") or fm.get("id") or "?"
        purpose = fm.get("purpose") or "?"
        deadline = fm.get("deadline") or "none"
        delivery_suffix = _annotate_dispatch_with_delivery_state(
            fm, delivery_state, current_seat,
        )
        out.append(
            f"- {slug} ({purpose}; deadline {deadline}){delivery_suffix}"
        )
        expected = (fm.get("expected_outcome") or "").strip()
        if expected:
            out.append(f"  expected: {expected}")
    if overflow > 0:
        # Sub-spec §7.1: pagination cursor (no elision; deterministic
        # age-ordered).
        out.append(
            f"... ({overflow} more standing dispatches; "
            f"run `wl dispatches pending --seat me` to view)"
        )
    out.append("")
    return "\n".join(out)


def render_wip_claim_section(
    repo: Path, *, current_seat: str | None,
) -> str:
    """Render the active wip-claims section for the SessionStart digest.

    Per sub-spec §7: surface active claims for the CURRENT seat first,
    then visible path-collisions where the colliding-seat is NOT the
    current seat (early warning).

    D33 / Hard Rule 5: never blocks; failures degrade to a short stderr
    log and an empty rendered section.
    """
    if _wip_claim_mod is None:
        return ""
    try:
        all_active = _wip_claim_mod.load_active_claims(repo)
    except Exception as exc:  # pragma: no cover
        sys.stderr.write(
            f"[state_digest] wip-claim discovery failed: {exc}\n"
        )
        return ""
    if not all_active and current_seat is None:
        return ""

    now = datetime.now(timezone.utc)
    out: list[str] = []

    # Section 1: claims owned by current_seat.
    if current_seat is not None:
        mine = [c for c in all_active if c.get("seat") == current_seat]
        out.append(f"## Active wip-claims (seat: {current_seat})")
        if mine:
            for fm in mine:
                slug = fm.get("_slug") or fm.get("id") or "?"
                expires = fm.get("expires_at") or "?"
                delta = _format_expires_delta(expires, now)
                out.append(f"- {slug} (expires {delta})")
                paths = fm.get("paths") or []
                if paths:
                    truncated = paths[:3]
                    suffix = (
                        f" (+ {len(paths) - 3} more)"
                        if len(paths) > 3 else ""
                    )
                    out.append(
                        f"  paths: {', '.join(truncated)}{suffix}"
                    )
        else:
            out.append("- (none for this seat)")
        out.append("")
    else:
        # No current seat known — surface all active.
        out.append("## Active wip-claims (all seats — no current-seat known)")
        for fm in all_active:
            slug = fm.get("_slug") or fm.get("id") or "?"
            seat = fm.get("seat") or "?"
            expires = fm.get("expires_at") or "?"
            delta = _format_expires_delta(expires, now)
            out.append(f"- {slug} — {seat} (expires {delta})")
        if not all_active:
            out.append("- (none)")
        out.append("")

    # Section 2: visible path-collisions where colliding-seat != current_seat.
    if _wip_claim_checks_mod is not None and current_seat is not None:
        try:
            warnings = _wip_claim_checks_mod.run_wip_claim_checks(repo)
        except Exception as exc:  # pragma: no cover
            sys.stderr.write(
                f"[state_digest] wip-claim checks failed: {exc}\n"
            )
            warnings = []
        collisions = [
            w for w in warnings
            if w.category == "wip_claim_path_collision"
        ]
        if collisions:
            out.append("## WIP-claim collisions (early warning)")
            for w in collisions:
                # Filter to ones touching the current seat's paths if possible.
                out.append(f"- {w.message}")
            out.append("")

    return "\n".join(out)


_CODEX_FRAMING_PREFIX = (
    "## Workshop-Lite substrate orientation (codex-host emission)\n\n"
)


def format_for_mode(digest_text: str, output_mode: str) -> str:
    """Apply WL.29 D1 mode-specific framing to a base ``render_digest`` output.

    Modes (per cohort WL.29 charter §2 D1 cert axes):

    - ``claude_code`` / default — pass-through; preserves existing
      hook-path behavior (regression-delta = 0 vs LANDed-main).
    - ``codex`` — prepends a one-line codex-host framing prefix so the
      content is identifiable as codex-emission. Body is the same;
      mechanical-transform only (HR #7 disposition (b)).
    - ``plain`` — strips markdown decorators (header prefixes ``## ``,
      code-fence ``` ``` ``` lines, backticks around inline code) for
      lowest-common-denominator text-only consumers.

    Unknown modes pass through unchanged (treat as ``claude_code``).
    """
    if output_mode == "codex":
        return _CODEX_FRAMING_PREFIX + digest_text
    if output_mode == "plain":
        return _strip_markdown_decorators(digest_text)
    # claude_code or unrecognized: pass through.
    return digest_text


def _strip_markdown_decorators(text: str) -> str:
    """Strip the common markdown decorators for plain-text mode.

    Removes code-fence lines (``` ``` ```), leading header prefixes
    (``# ``, ``## ``, ``### ``), and backticks around inline code.
    Preserves bullet markers (``- ``) and indentation since they read
    cleanly as plain text.
    """
    out: list[str] = []
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("```"):
            # Drop the code-fence line entirely.
            continue
        prefix_len = len(line) - len(stripped)
        rest = stripped
        for header_marker in ("### ", "## ", "# "):
            if rest.startswith(header_marker):
                rest = rest[len(header_marker):]
                break
        rest = rest.replace("`", "")
        out.append(line[:prefix_len] + rest)
    result = "\n".join(out)
    if text.endswith("\n") and not result.endswith("\n"):
        result += "\n"
    return result


def render_digest(
    repo: Path,
    *,
    current_seat: str | None = None,
    delivery_state: dict[tuple[str, str], str] | None = None,
) -> str:
    """Compose the full digest text (does NOT write — caller handles I/O).

    ``current_seat`` (optional) is the SessionStart hook's resolved
    seat FQID — handed in from ``parley whoami`` by the shell wrapper.
    None (parley absent) suppresses the per-seat WIP-claim section and
    falls back to a list-all rendering.

    ``delivery_state`` (optional, Phase 2 sub-spec §7 + §10): mapping
    ``(msg_id, recipient_fqid) -> state_string`` from parley primitive
    #1. The skill / hook wrapper queries parley and hands the data in;
    this module stays parley-agnostic at base (Hard Rule 1). When None,
    standing-dispatch annotation degrades to entity-only display.
    """
    lines: list[str] = []

    # Phase 2 of re-arch arc: standing-dispatches surface AT THE TOP of
    # the orientation digest per sub-spec §7 (load-bearing dispatches
    # must remain front-of-mind across seat replacements). Empty
    # section degrades silently.
    try:
        dispatch_section = render_standing_dispatch_section(
            repo,
            current_seat=current_seat,
            delivery_state=delivery_state,
        )
    except Exception as exc:  # pragma: no cover
        sys.stderr.write(
            f"[state_digest] standing-dispatch render failed: {exc}\n"
        )
        dispatch_section = ""
    if dispatch_section.strip():
        lines.append(dispatch_section.rstrip())
        lines.append("")

    lines.append("## dev-mgmt session orientation")
    sprint = find_active_sprint(repo)
    if sprint:
        sid, stage = sprint
        n = pending_tasks_count(repo, sid)
        suffix = ""
        created = _active_sprint_created_at(repo, sid)
        days = _days_since(created) if created else None
        if days is not None:
            suffix = f"; {days}d since start"
        lines.append(f"- Active sprint: **{sid}** (stage={stage}; pending tasks={n}{suffix})")
    else:
        lines.append("- No active sprint")

    decisions = recent_decisions(repo)
    if decisions:
        lines.append("- Recent decisions:")
        for slug in decisions:
            lines.append(f"  - {slug}")

    handoff = latest_handoff(repo)
    if handoff:
        lines.append(f"- Latest handoff: {handoff['slug']} (format={handoff['format']})")
        if handoff["format"] == "dev-mgmt":
            lines.append(f"  - topic: {handoff['topic']}")
            lines.append(f"  - next_action: {handoff['next_action']}")
        lines.append(f"  - excerpt (first 25 lines):")
        lines.append("    ```")
        for excerpt_line in handoff["excerpt"].splitlines():
            lines.append(f"    {excerpt_line}")
        lines.append("    ```")
        lines.append(
            "  - (per memory feedback_handoff_at_session_start.md if present, "
            "read the full handoff file and ask the user whether to follow its "
            "instructions before starting other work.)"
        )

    issue = latest_open_issue(repo)
    if issue:
        lines.append(
            f"- Open issue (most recent): {issue['slug']} "
            f"(severity={issue['severity']})"
        )

    lines.append(
        "- Orientation docs: CLAUDE.md, DEV-MGMT-SESSION-ORIENTATION.md, "
        "docs/design/LIGHTWEIGHT-DEV-MGMT-SYSTEM.md"
    )
    digest_text = "\n".join(lines) + "\n"

    # Phase 1 of re-arch arc: append the WIP-claim section per sub-spec §7.
    # Failures degrade silently (D33 / Hard Rule 5).
    try:
        wip_section = render_wip_claim_section(repo, current_seat=current_seat)
    except Exception as exc:  # pragma: no cover
        sys.stderr.write(
            f"[state_digest] wip-claim section render failed: {exc}\n"
        )
        wip_section = ""
    if wip_section.strip():
        digest_text += "\n" + wip_section
        if not digest_text.endswith("\n"):
            digest_text += "\n"
    return digest_text


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo-root", default=None)
    ap.add_argument(
        "--current-seat",
        default=None,
        help="FQID of the calling seat (e.g. 'wl-rearch:wl-plan'); the "
             "session-context.sh wrapper derives this from `parley whoami`"
             " and hands it in so the WIP-claim section can filter to "
             "this seat's claims (sub-spec §7).",
    )
    args = ap.parse_args()
    repo = Path(args.repo_root) if args.repo_root else Path.cwd()
    # Silent only if NO dev-mgmt convention dir exists. Partial adoption
    # (e.g. legacy handoffs without sprints) should still surface the digest.
    docs = repo / "docs"
    convention_dirs = (
        "sprints", "decisions", "issues",
        "reviews", "handoffs", "conversations", "wip",
    )
    if not any((docs / d).exists() for d in convention_dirs):
        return 0
    sys.stdout.write(render_digest(repo, current_seat=args.current_seat))
    return 0


if __name__ == "__main__":
    sys.exit(main())
