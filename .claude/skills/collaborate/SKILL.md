---
name: collaborate
description: Joint refinement via the collaborator persona — thin alias for `/consult collaborator <target>`. Generative (not adversarial); proposes extensions / alternatives / sharpenings. Use when the user types `/collaborate <target>` or asks to brainstorm against an entity.
---

# /collaborate

When the user invokes `/collaborate <target>`, this is a **convenience
alias** for `/consult collaborator <target>`. Same flow, same Review
entity shape, same graceful degradation.

Hand off directly to the `/consult` skill flow with `persona-slug =
collaborator`. See `.claude/skills/consult/SKILL.md` for the full
procedure.

Pass-through invocation:

```bash
.venv/bin/python3 .claude/scripts/dev-mgmt/cli.py consult \
    collaborator \
    "<target-id>" \
    [--author "@<seat>"] \
    [other flags ...]
```

The collaborator persona runs in **generative mode** — the resulting
Review has `decision: N/A` + `insights` (not `findings`). v1 ships
this alias because collaborator is the second-highest-frequency
persona (charter §2.3).
