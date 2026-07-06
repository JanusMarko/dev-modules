#!/usr/bin/env bash
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
    DIGEST=$(timeout 8s "$REPO/bin/wl-mcp" state-digest \
        --output-mode codex --repo-root "$REPO" 2>/dev/null)
else
    DIGEST=$(timeout 8s python3 \
        "$REPO/.claude/scripts/dev-mgmt/cli.py" state-digest \
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
sys.stdout.write("\n")
'

exit 0
