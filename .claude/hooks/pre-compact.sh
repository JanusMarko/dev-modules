#!/usr/bin/env bash
# PreCompact hook for dev-mgmt sessions (D32 + D6.A + D33 + Q5 + Q6).
#
# Phase 1 Cycle 4 (wl-rearch §4.3): delegates to
# `precompact_body_scrape_hook.py`. That driver reads the consolidated
# `[handoffs.body_scrape]` config; when enabled=true it scrapes
# git/parley/INDEX and writes a populated handoff body via the pure
# `precompact_body_scrape` library. When enabled=false (the default)
# it falls back to the legacy empty-stub invocation — bitwise-identical
# behavior to pre-Cycle-4.
#
# - Active-sprint detection uses INDEX (Q3 via state_digest.find_active_sprint);
#   when no active sprint exists, the handoff is still written with sprint_id=null
#   per D6.A / Q5 (the artifact captures the moment of compact regardless).
# - Stage hardcoded to `execute` per Q6 (95% accurate — compacts almost always
#   hit mid-work between /start-sprint and /end-sprint).
#
# D33 + Hard Rule 5: always exits 0; NEVER blocks compaction.
# §8.5 timeout budget: enforced internally by the Python driver (5s wall-clock
# default, configurable via [handoffs.body_scrape].timeout_seconds).

set +e

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
PY="$REPO/.venv/bin/python3"
[ -x "$PY" ] || PY="python3"

# Hard outer wall-clock cap (Hard Rule 5 belt-and-suspenders): the
# Python driver enforces the configured timeout internally; we wrap
# it in a 10s shell-level `timeout` so a wedged subprocess can never
# hold compaction.
if command -v timeout >/dev/null 2>&1; then
    timeout 10s "$PY" "$HERE/precompact_body_scrape_hook.py" --repo-root "$REPO" >/dev/null
else
    "$PY" "$HERE/precompact_body_scrape_hook.py" --repo-root "$REPO" >/dev/null
fi

exit 0
