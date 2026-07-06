"""Codex-host substrate-emission helpers (WL.29 D2).

Backs the ``wl install-codex-content`` CLI verb. Composes 5 emission
categories into a target consumer repo so codex agents can be
first-class workshop-lite citizens:

1. **Trust entry** in user-global ``~/.codex/config.toml``:
   ``[projects."<absolute-path>"] trust_level = "trusted"`` — per
   @codex-expert msg-ee984e05aeec, per-repo configs are silently
   dropped without the trust entry.

2. **MCP server block** in repo-local ``<target>/.codex/config.toml``:
   ``[mcp_servers.workshop_lite] command = "<wl-mcp>"
   default_tools_approval_mode = "approve"`` — delegated to the
   existing ``_install_codex_mcp_block`` helper in cli.py (LANDed
   bdfeac1).

3. **AGENTS.md** substrate-orientation section in
   ``<target>/AGENTS.md`` — STATIC markdown wrapped in
   ``<!-- workshop-lite-start --> ... <!-- workshop-lite-end -->``
   markers (HR #3 workshop-lite-* prefix). Operator-facing
   description of available verbs + doc pointers.

4. **3 codex-host hook scripts** in ``<target>/.codex/hooks/``:
   - ``state_digest_emit.sh`` — SessionStart hook; shells out to
     ``wl state-digest --output-mode codex`` and wraps stdout as
     a SessionStart hook output JSON envelope per
     ``codex-rs/hooks/src/schema.rs:328-346`` (sha 58573da43):
     ``{"hookSpecificOutput": {"hookEventName": "SessionStart",
     "additionalContext": "<digest>"}}``.
   - ``pre_compact_handoff.sh`` — PreCompact hook; mirrors
     ``.claude/hooks/pre-compact.sh`` (writes handoff entity).
   - ``validate_state.sh`` — Stop hook; mirrors
     ``.claude/hooks/validate-state.sh`` (runs ``wl validate``).

5. **Hook registrations** in repo-local
   ``<target>/.codex/config.toml``: ``[[hooks.<Event>]]`` blocks
   using **PascalCase + nested-array-of-tables** per the codex
   hook config soft-trap (harness-analysis Area 3 /
   ``codex-rs/config/src/hook_config.rs:32-50``). Single-table
   ``[hooks.session_start]`` is silently invalid against codex
   0.130's deserializer.

Each emission path is idempotent (state machine: file absent /
section absent / section present / canonical) and supports
``--dry-run`` (no writes; prints proposed changes).

HR #1 (parley-agnostic at base) holds: this module never imports
or shells out to parley.
"""
from __future__ import annotations

from pathlib import Path


# ---------------------------------------------------------------------------
# AGENTS.md marker section
# ---------------------------------------------------------------------------

AGENTS_MD_MARKER_START = "<!-- workshop-lite-start -->"
AGENTS_MD_MARKER_END = "<!-- workshop-lite-end -->"

AGENTS_MD_SECTION_BODY = """## Workshop-Lite substrate

This repository is managed by Workshop-Lite, a lightweight,
markdown-based dev-management substrate. Decisions, issues, reviews,
sprints, and handoffs are tracked as durable markdown entities under
`docs/`.

### Available verbs (codex MCP)

When the workshop-lite MCP server is registered in
`.codex/config.toml` (`[mcp_servers.workshop_lite]`), the following
verbs are available via codex's MCP tool surface:

- `record-decision` — log a decision entity
- `record-issue` — log an issue
- `record-review` — log a review (adversarial / collaborative / synthesis / research)
- `handoff` — write a session-boundary handoff
- `start-sprint` / `end-sprint` — sprint lifecycle
- `add-task` — append a task to the active sprint
- `capture-conversation` — snapshot a chat range

### SessionStart orientation

A codex SessionStart hook (`.codex/hooks/state_digest_emit.sh`)
emits the current substrate state — active sprint, recent
decisions, latest handoff, open issues — into your context at
session start. Failures degrade silently.

### Reference

- Comprehensive design: `docs/design/LIGHTWEIGHT-DEV-MGMT-SYSTEM.md`
- Conventions index: `docs/conventions/INDEX.md`
"""


def render_agents_md_section() -> str:
    """Return the canonical workshop-lite AGENTS.md section bracketed by
    HR #3 ``workshop-lite-*`` markers.
    """
    return (
        f"{AGENTS_MD_MARKER_START}\n\n"
        f"{AGENTS_MD_SECTION_BODY.rstrip()}\n\n"
        f"{AGENTS_MD_MARKER_END}\n"
    )


def _install_agents_md(agents_md_path: Path) -> tuple[str, str]:
    """Compute desired ``AGENTS.md`` text + action.

    State machine (mirrors ``_install_codex_mcp_block``):

    - file absent → action=``create-file``, text = marker section only
    - file present, markers absent → action=``append-section``, text =
      existing content + blank line + marker section
    - file present, markers present, content matches canonical → action=
      ``noop``, text = existing
    - file present, markers present, content differs → action=
      ``refresh-section``, text = existing with marker section replaced

    Drift-detect: content OUTSIDE the marker block is preserved as-is on
    refresh (not touched). Per HR #3 + the standing D3 PG-4 PRE-WRITE
    drift-detection pattern from ``parley adopt-workshop-lite``.
    """
    canonical_section = render_agents_md_section()

    if not agents_md_path.exists():
        return canonical_section, "create-file"

    existing = agents_md_path.read_text(encoding="utf-8")
    start_idx = existing.find(AGENTS_MD_MARKER_START)
    end_idx = existing.find(AGENTS_MD_MARKER_END)

    if start_idx == -1 or end_idx == -1 or end_idx < start_idx:
        # Markers absent (or malformed) — append the section.
        sep = "" if existing.endswith("\n") else "\n"
        return existing + sep + "\n" + canonical_section, "append-section"

    # Markers present — extract the existing section + compare against
    # canonical.
    section_end = end_idx + len(AGENTS_MD_MARKER_END)
    # Include the trailing newline immediately after the end marker if
    # present (for stable noop comparison).
    if section_end < len(existing) and existing[section_end] == "\n":
        section_end += 1
    existing_section = existing[start_idx:section_end]

    if existing_section == canonical_section:
        return existing, "noop"

    # Refresh: replace the section in place, preserve everything else.
    new_text = (
        existing[:start_idx] + canonical_section + existing[section_end:]
    )
    return new_text, "refresh-section"


# ---------------------------------------------------------------------------
# Trust entry in user-global ~/.codex/config.toml
# ---------------------------------------------------------------------------


def _trust_entry_block(target_abs: str) -> str:
    return (
        f'[projects."{target_abs}"]\n'
        f'trust_level = "trusted"\n'
    )


def _install_trust_entry(
    user_config_path: Path, target_abs: str,
) -> tuple[str, str]:
    """Compute desired user-global ``~/.codex/config.toml`` text + action
    for the canonical ``[projects."<abs>"] trust_level = "trusted"`` entry.

    State machine:

    - file absent → action=``create-file``, text = entry only
    - file present, entry absent → action=``append-entry``, text =
      existing + blank line + canonical entry
    - file present, header present, ``trust_level`` line absent → action=
      ``insert-trust-line``, text = existing with line inserted
    - file present, header present, canonical → action=``noop``

    String-anchored detection — never reads/parses TOML, mirrors the
    ``_install_codex_mcp_block`` pattern (no TOML parse dependency).
    """
    header = f'[projects."{target_abs}"]'
    trust_key = "trust_level"
    canonical = _trust_entry_block(target_abs)

    if not user_config_path.exists():
        return canonical, "create-file"

    existing = user_config_path.read_text(encoding="utf-8")
    lines = existing.split("\n")

    header_idx: int | None = None
    for i, ln in enumerate(lines):
        if ln.strip() == header:
            header_idx = i
            break

    if header_idx is None:
        if not existing:
            return canonical, "append-entry"
        return existing.rstrip("\n") + "\n\n" + canonical, "append-entry"

    # Header exists — scan forward to find block extent + check trust line.
    block_end = len(lines)
    for j in range(header_idx + 1, len(lines)):
        s = lines[j].strip()
        if s.startswith("[") and s.endswith("]"):
            block_end = j
            break

    block_body = lines[header_idx + 1:block_end]
    has_trust = any(
        ln.strip().startswith(trust_key + " ") or
        ln.strip().startswith(trust_key + "=")
        for ln in block_body
    )
    if has_trust:
        return existing, "noop"

    insert_at = header_idx + 1
    new_lines = (
        lines[:insert_at]
        + [f'{trust_key} = "trusted"']
        + lines[insert_at:]
    )
    return "\n".join(new_lines), "insert-trust-line"


# ---------------------------------------------------------------------------
# Codex-host hook script templates
#
# These are emitted to <target>/.codex/hooks/ at install time. Each
# script honors HR #5 (never-block) via `set +e` + `timeout` wrapping,
# HR #1 (parley-agnostic at base) — no parley shellout, and is
# self-contained (resolves its own REPO root from $0 location).
# ---------------------------------------------------------------------------

CODEX_HOOK_STATE_DIGEST_EMIT_SH = """#!/usr/bin/env bash
# Workshop-Lite codex-host SessionStart hook.
# Installed by `wl install-codex-content` (WL.29 D2).
#
# Shells out to `wl state-digest --output-mode codex` and wraps the
# captured stdout as a SessionStart hook output JSON envelope per
# codex-rs/hooks/src/schema.rs:328-346 (sha 58573da43):
#   {"hookSpecificOutput": {"hookEventName": "SessionStart",
#    "additionalContext": "<digest>"}}
#
# HR #5: never blocks. Failures emit a minimal valid envelope so the
# codex session continues with no orientation rather than wedging.

set +e

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"

# Drain codex's hook-input JSON on stdin to avoid SIGPIPE.
cat >/dev/null 2>&1 || true

# Resolve the wl entry-point. Prefer the wl-mcp shim if present;
# fall back to direct cli.py invocation.
if [ -x "$REPO/bin/wl-mcp" ]; then
    DIGEST=$(timeout 8s "$REPO/bin/wl-mcp" state-digest \\
        --output-mode codex --repo-root "$REPO" 2>/dev/null)
else
    DIGEST=$(timeout 8s python3 \\
        "$REPO/.claude/scripts/dev-mgmt/cli.py" state-digest \\
        --output-mode codex --repo-root "$REPO" 2>/dev/null)
fi

[ -z "$DIGEST" ] && DIGEST="(workshop-lite state-digest unavailable)"

# Emit the codex SessionStart hook output envelope.
printf '%s' "$DIGEST" | python3 -c '
import json, sys
text = sys.stdin.read()
out = {
    "hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": text,
    },
}
sys.stdout.write(json.dumps(out))
sys.stdout.write("\\n")
'

exit 0
"""


CODEX_HOOK_PRE_COMPACT_HANDOFF_SH = """#!/usr/bin/env bash
# Workshop-Lite codex-host PreCompact hook.
# Installed by `wl install-codex-content` (WL.29 D2).
#
# Mirrors `.claude/hooks/pre-compact.sh` — writes a handoff entity
# before compaction via precompact_body_scrape_hook.py.
#
# Hook output: codex PreCompactCommandOutputWire is universal-only
# (no additionalContext channel per codex-rs/hooks/src/schema.rs:138-142).
# Emit minimal valid envelope `{}`.
#
# HR #5: never blocks.

set +e

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
PY="$REPO/.venv/bin/python3"
[ -x "$PY" ] || PY="python3"

cat >/dev/null 2>&1 || true

if command -v timeout >/dev/null 2>&1; then
    timeout 10s "$PY" "$REPO/.claude/hooks/precompact_body_scrape_hook.py" \\
        --repo-root "$REPO" >/dev/null 2>&1
else
    "$PY" "$REPO/.claude/hooks/precompact_body_scrape_hook.py" \\
        --repo-root "$REPO" >/dev/null 2>&1
fi

printf '{}\\n'

exit 0
"""


CODEX_HOOK_VALIDATE_STATE_SH = """#!/usr/bin/env bash
# Workshop-Lite codex-host Stop hook.
# Installed by `wl install-codex-content` (WL.29 D2).
#
# Mirrors `.claude/hooks/validate-state.sh` — runs `wl validate`
# (advisory; never blocks via HR #5 / D33).
#
# Hook output: codex StopCommandOutputWire has decision/reason
# optional fields (defaults applied). Emit minimal valid envelope `{}`
# so the turn completes normally.
#
# HR #5: never blocks.

set +e

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
PY="$REPO/.venv/bin/python3"
[ -x "$PY" ] || PY="python3"
CLI="$REPO/.claude/scripts/dev-mgmt/cli.py"

cat >/dev/null 2>&1 || true

"$PY" "$CLI" validate --mtime-cutoff 300 --repo-root "$REPO" \\
    >/dev/null 2>&1 || true

printf '{}\\n'

exit 0
"""


CODEX_HOOK_SCRIPTS: dict[str, str] = {
    "state_digest_emit.sh": CODEX_HOOK_STATE_DIGEST_EMIT_SH,
    "pre_compact_handoff.sh": CODEX_HOOK_PRE_COMPACT_HANDOFF_SH,
    "validate_state.sh": CODEX_HOOK_VALIDATE_STATE_SH,
}


# ---------------------------------------------------------------------------
# Hook registrations in repo-local <target>/.codex/config.toml
#
# CRITICAL: codex 0.130's HookEventsToml deserializer expects PascalCase
# event names with nested array-of-tables, NOT single-table snake_case.
# `[hooks.session_start]` single-table = silently invalid (no error;
# the hook is dropped on the floor). Per harness-analysis Area 3
# substrate soft-trap.
# ---------------------------------------------------------------------------

CODEX_HOOK_EVENTS: list[tuple[str, str]] = [
    # (PascalCase event name, script filename)
    ("SessionStart", "state_digest_emit.sh"),
    ("PreCompact", "pre_compact_handoff.sh"),
    ("Stop", "validate_state.sh"),
]


def _render_hooks_block(target_abs: str) -> str:
    """Render the canonical ``[[hooks.<Event>]]`` block set.

    Each event gets a matcher + nested ``[[hooks.<Event>.hooks]]``
    array-of-tables with type=command + absolute script path.
    """
    parts: list[str] = [
        "# Workshop-lite codex-host hook registrations.",
        "# Installed by `wl install-codex-content` (WL.29 D2).",
        "# PascalCase + nested-array-of-tables per codex hook config",
        "# soft-trap (codex-rs/config/src/hook_config.rs:32-50, sha 58573da43).",
    ]
    for event, script in CODEX_HOOK_EVENTS:
        script_path = f"{target_abs}/.codex/hooks/{script}"
        parts.append("")
        parts.append(f"[[hooks.{event}]]")
        parts.append('matcher = ""')
        parts.append("")
        parts.append(f"[[hooks.{event}.hooks]]")
        parts.append('type = "command"')
        parts.append(f'command = "{script_path}"')
    return "\n".join(parts) + "\n"


def _hooks_block_present(existing: str) -> bool:
    """Return True iff the canonical hook registrations marker line is
    present in the existing config text.

    String-anchored detection — looks for the comment-line marker so we
    don't depend on TOML parse.
    """
    return (
        "# Installed by `wl install-codex-content` (WL.29 D2)." in existing
    )


def _compute_hooks_block_update(
    existing_text: str | None, target_abs: str,
) -> tuple[str, str]:
    """String-based core: compute hooks-block update against in-memory text.

    Used by ``plan_install`` to chain after the MCP-block plan (both
    steps target the same ``.codex/config.toml`` file; step N+1 must
    see step N's projected output, not the pre-write disk state).

    State machine:

    - ``existing_text is None`` (file absent) → action=``create-file``,
      text = hooks block only
    - existing has marker → action=``noop`` (idempotent re-install)
    - existing without marker → action=``append-block``, text = existing
      + blank line + hooks block
    """
    canonical = _render_hooks_block(target_abs)

    if existing_text is None:
        return canonical, "create-file"
    if _hooks_block_present(existing_text):
        return existing_text, "noop"
    if not existing_text:
        return canonical, "append-block"
    return (
        existing_text.rstrip("\n") + "\n\n" + canonical, "append-block",
    )


def _install_codex_hooks_block(
    cfg_path: Path, target_abs: str,
) -> tuple[str, str]:
    """Disk-based wrapper around ``_compute_hooks_block_update``. Reads
    ``cfg_path`` (or treats absent as ``None``) and dispatches.

    Drift detection is NOT applied to this block because the registered
    command path is bound to ``target_abs`` (move-invariant: stale paths
    after a repo move are a separate concern). Future refresh via a
    ``--refresh-hooks`` flag (out of scope for v1).
    """
    existing = (
        cfg_path.read_text(encoding="utf-8") if cfg_path.exists() else None
    )
    return _compute_hooks_block_update(existing, target_abs)


# ---------------------------------------------------------------------------
# Plan / apply orchestrator
# ---------------------------------------------------------------------------


def plan_install(
    target: Path,
    *,
    wl_bin: Path,
    user_config_path: Path,
    mcp_block_helper,  # callable: (cfg_path, wl_bin) -> (text, action)
) -> list[dict]:
    """Plan all install-codex-content steps. Returns a list of step dicts
    in execution order; each dict has keys:

      - ``kind``: one of ``trust-entry`` / ``mcp-block`` / ``hooks-block`` /
        ``agents-md`` / ``hook-script:<filename>``
      - ``path``: target file path (Path)
      - ``action``: state-machine action label
        (``create-file``/``append``/``noop``/``refresh-section``/…)
      - ``new_text``: text that would be written (None for noop)

    Caller decides whether to actually write (dry-run vs apply) based on
    the returned plan.

    ``mcp_block_helper`` is injected so this module avoids importing
    cli.py (which would create a circular import). Caller passes
    ``cli._install_codex_mcp_block``.
    """
    target_abs = str(target.resolve())
    plan: list[dict] = []

    # Step 1: user-global trust entry
    trust_text, trust_action = _install_trust_entry(
        user_config_path, target_abs,
    )
    plan.append({
        "kind": "trust-entry",
        "path": user_config_path,
        "action": trust_action,
        "new_text": None if trust_action == "noop" else trust_text,
    })

    # Step 2: repo-local MCP server block
    repo_codex_cfg = target / ".codex" / "config.toml"
    mcp_text, mcp_action = mcp_block_helper(repo_codex_cfg, wl_bin)
    plan.append({
        "kind": "mcp-block",
        "path": repo_codex_cfg,
        "action": mcp_action,
        "new_text": None if mcp_action == "noop" else mcp_text,
    })

    # Step 3: 3 codex-host hook script emissions
    hooks_dir = target / ".codex" / "hooks"
    for filename, body in CODEX_HOOK_SCRIPTS.items():
        script_path = hooks_dir / filename
        if script_path.exists():
            existing_body = script_path.read_text(encoding="utf-8")
            if existing_body == body:
                action = "noop"
                new_text = None
            else:
                action = "refresh-script"
                new_text = body
        else:
            action = "create-file"
            new_text = body
        plan.append({
            "kind": f"hook-script:{filename}",
            "path": script_path,
            "action": action,
            "new_text": new_text,
        })

    # Step 4: hook registrations block in repo-local .codex/config.toml.
    # Must chain after step 2's mcp-block plan because both target the
    # same file — step 4 sees step 2's projected output as the
    # "existing" text so a sequential apply (step 2 write, then step 4
    # write) produces a combined file containing both blocks.
    hooks_text, hooks_action = _compute_hooks_block_update(
        mcp_text, target_abs,
    )
    plan.append({
        "kind": "hooks-block",
        "path": repo_codex_cfg,
        "action": hooks_action,
        "new_text": None if hooks_action == "noop" else hooks_text,
    })

    # Step 5: AGENTS.md substrate-orientation section
    agents_md_path = target / "AGENTS.md"
    agents_text, agents_action = _install_agents_md(agents_md_path)
    plan.append({
        "kind": "agents-md",
        "path": agents_md_path,
        "action": agents_action,
        "new_text": None if agents_action == "noop" else agents_text,
    })

    return plan


def apply_install_step(step: dict) -> None:
    """Apply a single planned step to disk.

    Creates parent directories as needed; chmods hook scripts to 0o755.
    No-op when ``action == "noop"``.
    """
    if step["action"] == "noop":
        return
    path: Path = step["path"]
    new_text: str = step["new_text"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(new_text, encoding="utf-8")
    if step["kind"].startswith("hook-script:"):
        path.chmod(0o755)
