---
name: devil
description: Adversarial review via the devil-advocate persona — thin alias for `/consult devil-advocate <target>`. Use when the user types `/devil <target>` or asks for a sharp adversarial read on an entity.
---

# /devil

When the user invokes `/devil <target>`, this is a **convenience alias**
for `/consult devil-advocate <target>`. Same flow, same Review entity
shape, same graceful degradation.

Hand off directly to the `/consult` skill flow with `persona-slug =
devil-advocate`. See `.claude/skills/consult/SKILL.md` for the full
procedure (input gathering, author derivation, gemini shell-out, Y/n
fallback, supersede).

Pass-through invocation:

```bash
.venv/bin/python3 .claude/scripts/dev-mgmt/cli.py consult \
    devil-advocate \
    "<target-id>" \
    [--author "@<seat>"] \
    [other flags ...]
```

All flags from `/consult` pass through verbatim. v1 ships this as a
flat-named alias (Hard Rule 4) because devil-advocate is the
highest-frequency persona.
