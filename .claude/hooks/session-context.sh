#!/usr/bin/env bash
# SessionStart hook for dev-mgmt sessions (D31 + Q3 + Q7 + Sprint 9 D62).
#
# - When parley is on PATH AND this CC session is a parley member,
#   chains `parley resume <sid>` (orientation digest: unread chat +
#   recent decisions + newest handoff + git status) AND cats the
#   per-member `instructions.md` (per-role context). Together these
#   give a fresh/replaced agent the full re-orientation packet.
# - When parley is on PATH but this session is NOT a member, falls
#   back to `parley unread` for any general state.
# - When parley is absent, silently skips both (Hard Rule 5
#   parley-agnostic-base; Q7).
# - Always runs state_digest.py for dev-mgmt entity state (D31 / Q3).
#
# D33: always exits 0; failures log to stderr but never propagate.

set +e

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
PY="$REPO/.venv/bin/python3"
[ -x "$PY" ] || PY="python3"

# 1. Parley chain (D62: resume + per-member instructions when member; unread fallback when not; silent when parley absent).
if command -v parley >/dev/null 2>&1; then
    WHOAMI_JSON="$(parley whoami 2>/dev/null)"
    SID=""
    WID=""
    if [ -n "$WHOAMI_JSON" ]; then
        SID="$(printf '%s' "$WHOAMI_JSON" | "$PY" -c "import json,sys
try: d = json.loads(sys.stdin.read() or '{}')
except Exception: d = {}
print(d.get('session', {}).get('sid', '') or '')" 2>/dev/null)"
        WID="$(printf '%s' "$WHOAMI_JSON" | "$PY" -c "import json,sys
try: d = json.loads(sys.stdin.read() or '{}')
except Exception: d = {}
print(d.get('tmux_window_id', '') or '')" 2>/dev/null)"
    fi

    if [ -n "$SID" ]; then
        # Member context: orientation digest + per-member instructions.
        parley resume "$SID" 2>&1 || true
        if [ -n "$WID" ]; then
            INSTR="$REPO/.parley/$SID/members/$WID/instructions.md"
            if [ -f "$INSTR" ]; then
                echo ""
                echo "## Per-member instructions ($SID / $WID)"
                cat "$INSTR"
            fi
        fi
    else
        # Parley installed but not a member of any session here: surface any unread state.
        parley unread 2>&1 || true
    fi

    # 1a. Hard Rule #8 forward-motion-default reminder for scrum-master seats.
    # Phase 5 of wl-rearch arc — codifies the doctrine at the SessionStart
    # surface so a fresh-context scrum-master seat sees it without needing to
    # re-read the doc. Silent for non-scrum-master role_kinds + parley-absent.
    # Hard Rule 5: never blocks; failures fall through.
    #
    # Sprint wl.15 — gated on `planning.autonomy_level` user preference
    # (modular, opt-in per Kris's "not a hardcoded global" doctrine on
    # user-prefs). Reminder fires only when the effective user-scoped
    # autonomy_level == "forward-motion"; default "prompt" → silent.
    # Pref-read is the canonical consumer pattern from preferences/
    # SKILL.md — one path, parley-aware ScopeResolver injected at the
    # SKILL/hook layer (Hard Rule 1 / D27).
    if [ -n "$WHOAMI_JSON" ]; then
        if printf '%s' "$WHOAMI_JSON" | grep -q '"role_kind"[[:space:]]*:[[:space:]]*"scrum_master"' 2>/dev/null; then
            AUTONOMY="$("$PY" -c "
import sys
sys.path.insert(0, '$REPO/.claude/scripts/dev-mgmt')
sys.path.insert(0, '$REPO/.claude/skills/preferences')
from preferences import get_preference
try:
    from adapters import ParleyHumanScopeResolver
    resolver = ParleyHumanScopeResolver()
except Exception:
    resolver = None
print(get_preference('planning', 'autonomy_level', default='prompt', resolver=resolver, repo_root='$REPO'))
" 2>/dev/null)"
            if [ "$AUTONOMY" = "forward-motion" ]; then
                echo ""
                echo "[workshop-lite] reminder: forward-motion default per Hard Rule #8 (autonomy-delegated → dispatch, not ask). See docs/design/AUTONOMY-FORWARD-MOTION-DOCTRINE.md. (Gated on planning.autonomy_level=forward-motion user pref.)"
            fi
        fi
    fi
fi

# 2. State-digest. The python helper writes to stdout (D45 / Issue 2026-05-14-07).
#
# Phase 1 of re-arch arc (sub-spec §7): pass --current-seat when parley
# whoami yields an FQID so the digest can surface this seat's active
# wip-claims + early-warning path-collisions. Failure to derive the
# seat falls through to no-flag invocation (the digest then renders a
# list-all section instead of the per-seat section).
WIP_SEAT=""
if command -v parley >/dev/null 2>&1 && [ -n "$WHOAMI_JSON" ]; then
    WIP_SEAT="$(printf '%s' "$WHOAMI_JSON" | "$PY" -c "import json,sys
try: d = json.loads(sys.stdin.read() or '{}')
except Exception: d = {}
sid = d.get('session', {}).get('sid', '') or ''
mid = d.get('member_id', '') or d.get('id', '') or ''
print(f'{sid}:{mid}' if sid and mid else mid)" 2>/dev/null)"
fi

if [ -n "$WIP_SEAT" ]; then
    "$PY" "$HERE/state_digest.py" --repo-root "$REPO" --current-seat "$WIP_SEAT" || true
else
    "$PY" "$HERE/state_digest.py" --repo-root "$REPO" || true
fi

# 3. Sync-from-parley sidecar (Phase 2 Cycle 2 of the workshop-lite
# re-arch arc, sub-spec
# `docs/design/2026-05-29-wl-sync-from-parley-spec.md` §6.1). Opt-in
# via `.claude/workshop-lite-config.toml` `[sync_from_parley]
# enabled=true`. Default OFF + parley-absent both yield silent no-ops
# (Hard Rule 5: never block; the daemon's failure is silent to the
# seat — visible only in the log file).
#
# The Python driver is parley-coupled by design (it shells out to
# `parley get`); the library it calls (`sync_from_parley.py`) is
# parley-agnostic per Hard Rule 1.
if command -v timeout >/dev/null 2>&1; then
    timeout 10s "$PY" "$HERE/sync_from_parley_hook.py" --repo-root "$REPO" >/dev/null 2>&1 || true
else
    "$PY" "$HERE/sync_from_parley_hook.py" --repo-root "$REPO" >/dev/null 2>&1 || true
fi

exit 0
