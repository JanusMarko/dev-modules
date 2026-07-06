#!/usr/bin/env bash
# PostCompact hook for dev-mgmt sessions (WL.29 D3 PG-3.1).
#
# Fires after CC compaction completes. Re-emits the substrate state-
# digest so the freshly-compacted session has orientation context
# (mirrors `session-context.sh` §2 invocation pattern).
#
# Why this is NOT just re-firing session-context.sh wholesale:
#   1. session-context.sh §1 (parley resume + per-member instructions
#      chain) is heavy; the parley resume orientation digest already
#      ran at SessionStart, no value re-running on every compact.
#   2. session-context.sh §3 (sync-from-parley sidecar) has its own
#      SessionStart-aligned cadence; re-firing on compact would
#      over-sync the cursor.
#   3. The post-compact session NEEDS substrate orientation but not
#      the full re-parley.
# So post-compact.sh runs ONLY §2 (state_digest.py re-emit) and
# stays cheap.
#
# HR #1 (parley-agnostic at base): library code stays parley-free;
# the parley-whoami shell-out below is allowed at the SKILL/hook
# layer (D27 boundary).
#
# HR #5 + D33: always exits 0; never blocks.

set +e

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
PY="$REPO/.venv/bin/python3"
[ -x "$PY" ] || PY="python3"

# Mirror session-context.sh §2's --current-seat derivation so the
# re-emitted digest filters wip-claims + standing-dispatches per seat.
WIP_SEAT=""
if command -v parley >/dev/null 2>&1; then
    WHOAMI_JSON="$(parley whoami 2>/dev/null)"
    if [ -n "$WHOAMI_JSON" ]; then
        WIP_SEAT="$(printf '%s' "$WHOAMI_JSON" | "$PY" -c "import json,sys
try: d = json.loads(sys.stdin.read() or '{}')
except Exception: d = {}
sid = d.get('session', {}).get('sid', '') or ''
mid = d.get('member_id', '') or d.get('id', '') or ''
print(f'{sid}:{mid}' if sid and mid else mid)" 2>/dev/null)"
    fi
fi

if [ -n "$WIP_SEAT" ]; then
    "$PY" "$HERE/state_digest.py" --repo-root "$REPO" --current-seat "$WIP_SEAT" || true
else
    "$PY" "$HERE/state_digest.py" --repo-root "$REPO" || true
fi

exit 0
