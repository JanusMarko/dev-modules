#!/usr/bin/env bash
# Parley-unread chain — generic parley-orientation hook (WL.29 D3 PG-3.2).
#
# Additive carveout of session-context.sh §1's parley chain. session-
# context.sh §1 stays in place AS-IS (this script does NOT replace it);
# the carveout makes the parley-coupling explicit + agent-class-portable
# so codex-host wrappers or future hook events can invoke the chain
# standalone without firing the full SessionStart sequence.
#
# Behavior (mirrors session-context.sh §1 faithfully):
#   - When parley is on PATH AND this session is a member of a parley
#     session: emit the `parley resume <sid>` orientation digest (unread
#     chat + recent decisions + newest handoff + git status) AND cat
#     the per-member instructions.md.
#   - When parley is on PATH but this session is NOT a member: emit
#     `parley unread` as a general state surface.
#   - When parley is absent: silent no-op.
#
# HR #1 (parley-agnostic at base) holds: this script IS the SKILL/hook
# layer where parley coupling is allowed (D27 boundary). Library code
# stays parley-free.
#
# HR #5 + D33: always exits 0; never blocks.

set +e

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
PY="$REPO/.venv/bin/python3"
[ -x "$PY" ] || PY="python3"

if ! command -v parley >/dev/null 2>&1; then
    exit 0
fi

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
    parley unread 2>&1 || true
fi

exit 0
