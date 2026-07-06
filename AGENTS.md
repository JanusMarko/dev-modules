<!-- BEGIN parley-managed -->
## Parley membership

When you are a member of a parley session, your per-member context lives at
`<repo>/.parley/<sid>/members/<window-id>/instructions.md` (sidecar-managed).
Run `parley whoami` to discover your session + member id + tier + policy.

The full participation reference is the project skill at
`<repo>/.codex/skills/parley/SKILL.md`. Codex auto-loads project skills
on session start.

**Nudge-and-pull delivery**: parley does NOT paste chat record bodies into
your pane. When new content arrives you receive a short NUDGE like
`[parley · 3 new for @<id>] run parley read --since msg-abc`. Run the
printed `parley read` command (a bash tool call) to fetch content; the
bash result is your window into the chat. Reply via `parley say`.
<!-- END parley-managed -->

<!-- workshop-lite-start -->

## Workshop-Lite substrate

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

<!-- workshop-lite-end -->
