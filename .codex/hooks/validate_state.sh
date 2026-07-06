#!/usr/bin/env bash
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

"$PY" "$CLI" validate --mtime-cutoff 300 --repo-root "$REPO" \
    >/dev/null 2>&1 || true

printf '{}\n'

exit 0
