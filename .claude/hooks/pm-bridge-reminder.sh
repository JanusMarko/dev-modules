#!/bin/bash
# parley pm-bridge-reminder — UserPromptSubmit hook (par-p0-defect-55).
#
# Re-pins the PM-bridge role + the translation discipline + the
# escalation rules at every UserPromptSubmit. Without this hook the
# bridge tends to drift back into the bridge's native register
# (technical jargon, raw SHAs, parley Kind constants) on long turns.
#
# Activation gate (both must hold):
#   - $PARLEY_MEMBER_ID set (we are in a parley pane)
#   - `parley whoami --field role_kind` returns `product_manager`
#
# Either gate failing ⇒ no-op (silent exit 0). Operators with this
# hook installed in `.claude/settings.json` but no parley membership
# (or a non-PM-bridge membership) see no output.
#
# HR-#4 nuance: this script lives in the CONSUMER repo's
# `.claude/hooks/pm-bridge-reminder.sh` (per-project). The installer
# NEVER writes `~/.claude/settings.json` or `~/.codex/` (per HR-#4 /
# refined commitment #6). The hook is opt-in via `parley install
# --with-hooks`.

set -e

# Gate 1: no parley membership ⇒ silent no-op.
if [ -z "${PARLEY_MEMBER_ID:-}" ]; then
    exit 0
fi

# Gate 2: role_kind != product_manager ⇒ silent no-op.
# `parley whoami --field role_kind` returns the bare role_kind string
# (no JSON braces), or exits non-zero if the field is absent. Capture
# both stdout and stderr to keep noise out of the hook output.
ROLE_KIND="$(parley whoami --field role_kind 2>/dev/null || true)"
if [ "$ROLE_KIND" != "product_manager" ]; then
    exit 0
fi

# Gates passed: emit the reminder. `[PM-BRIDGE ROLE REMINDER]` is the
# canonical prefix the bridge member is trained to attend to (the
# `product_manager` role-template instructions name it explicitly).
# Emitting on stdout surfaces it as a system message ahead of the
# user prompt; the Claude Code UserPromptSubmit hook contract treats
# stdout as a pre-prompt system insertion.
cat <<'REMINDER'
[PM-BRIDGE ROLE REMINDER]
You are a PM-bridge (role_kind=product_manager). Your single discipline:
every inbound technical signal goes through `/translate --up` before
relaying to the PM; every PM intent goes through `/translate --down`
before posting into the technical session. Output of every PM-facing
message is wrapped in a ```pm-translation``` markdown block — the
opener / closer is the discipline marker; never paraphrase around it.

Anti-responsibilities (do NOT do these):
  - Do not read code, run a debugger, or critique an implementation.
  - Do not engage technical peers on technical merits — route the
    question to the appropriate technical lead / planner with a
    `/translate --down` wrapper.
  - Do not improvise around an unknown technical detail — surface it
    as an open question; the technical lead answers.

Escalation: when a technical phrase is the load-bearing signal and you
cannot plain-language it without inventing, surface it as an open
question instead of guessing.
REMINDER

exit 0
