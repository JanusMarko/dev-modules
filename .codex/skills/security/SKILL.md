---
name: security
description: Security review via the security-auditor persona — thin alias for `/consult security-auditor <target>`. Surfaces vulnerabilities, data exposure, auth gaps, dependency risk. Use when the user types `/security <target>` or asks for a security review of an entity.
---

# /security

When the user invokes `/security <target>`, this is a **convenience
alias** for `/consult security-auditor <target>`. Same flow, same
Review entity shape, same graceful degradation.

Hand off directly to the `/consult` skill flow with `persona-slug =
security-auditor`. See `.claude/skills/consult/SKILL.md` for the full
procedure.

Pass-through invocation:

```bash
.venv/bin/python3 .claude/scripts/dev-mgmt/cli.py consult \
    security-auditor \
    "<target-id>" \
    [--author "@<seat>"] \
    [other flags ...]
```

The security-auditor persona runs in **evaluative mode** — the
resulting Review has `decision: PROCEED | AMEND | RETHINK` +
`findings`. v1 ships this alias as `security` (NOT `security-review`
or `security-audit`) to avoid collision with the CC-shipped
`/security-review` general PR review skill.
