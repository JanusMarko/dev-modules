---
name: record-role-set
description: Record a role-set library entry (spec §2.3; DOC1 §6.4) — names roles + SoD rules, the companion to a workflow. Writes .workshop-lite/ledger/role-sets/<slug>.md and refreshes role-sets/INDEX.md. Use when the user types /record-role-set or asks to declare the roles/SoD constraints for a workflow.
---

# /record-role-set

A **role-set** names *roles and rules*, never a runtime. It is the companion to
a workflow: which role owns which stage, the SoD/identity constraints over those
roles, and per-stage parallelization + aggregation markers. Roles are first-class
at N=1 (sequential role-filling under a distinct role-identity per role);
`parallelizable` is a declaration of intent — the standalone floor runs sequential.

## 1. Gather inputs

Required:
- **title** — the role-set's human name (becomes the slug id).
- **roles** — non-empty list; each role is `{name, owns_stage, identity_predicate?}`.
- **author** — the calling member's `@id`.

Optional:
- **sod-predicates** — list of SoD/identity constraint strings (§12), e.g. `"builder != tester"`.
- **per-stage-markers** — object `stage → {parallelizable: bool, aggregation ∈ all-must-pass|merge|pick-one}`.
- **status** — `draft | active (default) | superseded | retired`.
- **library-layer** — `built-in | project | user (default)`.
- **is-default**, **supersedes**, **owner-user** (default `user/local`).

## 2. Write the role-set

```bash
.venv/bin/python3 .claude/scripts/dev-mgmt/cli.py record-role-set \
    --title "<title>" \
    --roles-json '[{"name":"builder","owns_stage":"build"}]' \
    --author "@<member>" \
    [--sod-predicates-json '["builder != tester"]'] \
    [--per-stage-markers-json '{"build":{"parallelizable":false,"aggregation":"all-must-pass"}}'] \
    [--status ...] [--library-layer ...] [--is-default] [--supersedes "<id>"] \
    [--owner-user "<owner>"]
```

The writer validates (each role requires `name` + `owns_stage`; aggregation ∈ the
closed set), writes the file, and re-renders the INDEX.
