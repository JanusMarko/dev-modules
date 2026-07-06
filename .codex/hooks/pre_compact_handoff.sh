#!/usr/bin/env bash
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
    timeout 10s "$PY" "$REPO/.claude/hooks/precompact_body_scrape_hook.py" \
        --repo-root "$REPO" >/dev/null 2>&1
else
    "$PY" "$REPO/.claude/hooks/precompact_body_scrape_hook.py" \
        --repo-root "$REPO" >/dev/null 2>&1
fi

printf '{}\n'

exit 0
