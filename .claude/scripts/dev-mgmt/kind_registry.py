"""WL2 built-in kind catalog and declaration registry.

BC0.3 codifies the spec section 1.3/1.4 built-in set. The declarations here are
data, not inferred from writers or validators: missing flags fail closed.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from types import MappingProxyType
from typing import Mapping


PER_INSTANCE = "per-instance"
_FLAG_VALUES = {False, True, PER_INSTANCE}


class KindCatalogError(ValueError):
    """Raised when a kind catalog is incomplete or malformed."""


@dataclass(frozen=True)
class KindDeclaration:
    kind: str
    states: tuple[str, ...]
    transitions: tuple[tuple[str, str], ...]
    lifecycle_family: str
    body_schema_ref: str
    path: str
    requires_eval: bool | str
    produces_built_artifact: bool | str

    def to_dict(self) -> dict:
        return asdict(self)


def _edges(*states: str) -> tuple[tuple[str, str], ...]:
    return tuple(zip(states, states[1:]))


def _branch(start: str, *targets: str) -> tuple[tuple[str, str], ...]:
    return tuple((start, target) for target in targets)


_DECLARATIONS: dict[str, KindDeclaration] = {
    "task": KindDeclaration(
        kind="task",
        states=("created", "picked-up", "in-progress", "verified", "done", "cleaned-up"),
        transitions=_edges("created", "picked-up", "in-progress", "verified", "done", "cleaned-up"),
        lifecycle_family="work",
        body_schema_ref="spec:2.3 task-line",
        path=".workshop-lite/ledger/sprints/<active|archive>/sprint-<id>/tasks.md",
        requires_eval=PER_INSTANCE,
        produces_built_artifact=PER_INSTANCE,
    ),
    "decision": KindDeclaration(
        kind="decision",
        states=("accepted", "rejected", "superseded", "open"),
        transitions=(("open", "accepted"), ("open", "rejected"), ("open", "superseded"), ("accepted", "superseded")),
        lifecycle_family="status-only",
        body_schema_ref="spec:2.3 decision",
        path=".workshop-lite/ledger/decisions/<id>.md",
        requires_eval=False,
        produces_built_artifact=False,
    ),
    "review": KindDeclaration(
        kind="review",
        states=("completed", "in_progress"),
        transitions=(("in_progress", "completed"),),
        lifecycle_family="status-only",
        body_schema_ref="spec:2.3 review",
        path=".workshop-lite/ledger/reviews/<id>.md",
        requires_eval=False,
        produces_built_artifact=False,
    ),
    "issue": KindDeclaration(
        kind="issue",
        states=("open", "investigating", "deferred", "resolved", "wontfix", "superseded"),
        transitions=(("open", "investigating"), ("open", "deferred"), ("investigating", "resolved"), ("investigating", "wontfix"), ("investigating", "superseded")),
        lifecycle_family="status-only",
        body_schema_ref="spec:2.3 issue",
        path=".workshop-lite/ledger/issues/<id>.md",
        requires_eval=False,
        produces_built_artifact=False,
    ),
    "handoff": KindDeclaration(
        kind="handoff",
        states=("written",),
        transitions=(),
        lifecycle_family="status-only",
        body_schema_ref="spec:2.3 handoff",
        path=".workshop-lite/ledger/handoffs/<id>.md",
        requires_eval=False,
        produces_built_artifact=False,
    ),
    "sprint": KindDeclaration(
        kind="sprint",
        states=("active", "closed"),
        transitions=(("active", "closed"),),
        lifecycle_family="status-only",
        body_schema_ref="spec:2.3 sprint-plan",
        path=".workshop-lite/ledger/sprints/active|archive/sprint-<id>/plan.md",
        requires_eval=False,
        produces_built_artifact=False,
    ),
    "retrospective": KindDeclaration(
        kind="retrospective",
        states=("completed",),
        transitions=(),
        lifecycle_family="status-only",
        body_schema_ref="spec:2.3 retrospective",
        path=".workshop-lite/ledger/sprints/active|archive/sprint-<id>/retro.md",
        requires_eval=False,
        produces_built_artifact=False,
    ),
    "conversation": KindDeclaration(
        kind="conversation",
        states=(),
        transitions=(),
        lifecycle_family="stateless",
        body_schema_ref="spec:2.3 conversation",
        path=".workshop-lite/ledger/conversations/<id>.md",
        requires_eval=False,
        produces_built_artifact=False,
    ),
    "prd": KindDeclaration(
        kind="prd",
        states=("draft", "ratified", "converting", "technical_plan_ready", "shipped"),
        transitions=_edges("draft", "ratified", "converting", "technical_plan_ready", "shipped"),
        lifecycle_family="status-only",
        body_schema_ref="spec:2.3 prd",
        path=".workshop-lite/ledger/prds/<id>.md",
        requires_eval=False,
        produces_built_artifact=False,
    ),
    "standing_dispatch": KindDeclaration(
        kind="standing_dispatch",
        states=("standing", "satisfied", "superseded", "expired"),
        transitions=_branch("standing", "satisfied", "superseded", "expired"),
        lifecycle_family="status-only",
        body_schema_ref="spec:2.3 standing_dispatch",
        path=".workshop-lite/ledger/dispatches/<id>.md",
        requires_eval=False,
        produces_built_artifact=False,
    ),
    "wip_claim": KindDeclaration(
        kind="wip_claim",
        states=("claimed", "committed", "released", "abandoned"),
        transitions=_branch("claimed", "committed", "released", "abandoned"),
        lifecycle_family="status-only",
        body_schema_ref="spec:2.3 wip_claim",
        path=".workshop-lite/ledger/wip/<id>.md",
        requires_eval=False,
        produces_built_artifact=False,
    ),
    "gate": KindDeclaration(
        kind="gate",
        states=("open", "closed", "resolved"),
        transitions=_branch("open", "closed", "resolved"),
        lifecycle_family="status-only",
        body_schema_ref="spec:2.3 gate",
        path=".workshop-lite/ledger/gates/<id>.md",
        requires_eval=False,
        produces_built_artifact=False,
    ),
    "eval-corpus": KindDeclaration(
        kind="eval-corpus",
        states=("draft", "ratified", "superseded"),
        transitions=(("draft", "ratified"), ("ratified", "superseded")),
        lifecycle_family="status-only",
        body_schema_ref="spec:5.1",
        path=".workshop-lite/ledger/evals/<id>.md",
        requires_eval=False,
        produces_built_artifact=False,
    ),
    "eval-case": KindDeclaration(
        kind="eval-case",
        states=(),
        transitions=(),
        lifecycle_family="stateless",
        body_schema_ref="spec:5.2",
        path=".workshop-lite/ledger/evals/<corpus-id>/<case-id>.md",
        requires_eval=False,
        produces_built_artifact=False,
    ),
    "denial": KindDeclaration(
        kind="denial",
        states=("open", "resolve", "reroute", "cancel"),
        transitions=_branch("open", "resolve", "reroute", "cancel"),
        lifecycle_family="status-only",
        body_schema_ref="spec:9.1",
        path=".workshop-lite/ledger/denials/<id>.md",
        requires_eval=False,
        produces_built_artifact=False,
    ),
    "workflow": KindDeclaration(
        kind="workflow",
        states=("draft", "active", "superseded", "retired"),
        transitions=(("draft", "active"), ("active", "superseded"), ("active", "retired")),
        lifecycle_family="status-only",
        body_schema_ref="spec:2.3 workflow",
        path=".workshop-lite/ledger/workflows/<slug>.md",
        requires_eval=False,
        produces_built_artifact=False,
    ),
    "role-set": KindDeclaration(
        kind="role-set",
        states=("draft", "active", "superseded", "retired"),
        transitions=(("draft", "active"), ("active", "superseded"), ("active", "retired")),
        lifecycle_family="status-only",
        body_schema_ref="spec:2.3 role-set",
        path=".workshop-lite/ledger/role-sets/<slug>.md",
        requires_eval=False,
        produces_built_artifact=False,
    ),
    "block-signal": KindDeclaration(
        kind="block-signal",
        states=("raised", "resolved", "expired"),
        transitions=(("raised", "resolved"), ("raised", "expired")),
        lifecycle_family="status-only",
        body_schema_ref="spec:2.3 block-signal / spec:11.5",
        path=".workshop-lite/ledger/block-signals/<id>.md",
        requires_eval=False,
        produces_built_artifact=False,
    ),
    "resume-ledger": KindDeclaration(
        kind="resume-ledger",
        states=("written",),
        transitions=(),
        lifecycle_family="status-only",
        body_schema_ref="spec:2.3 resume-ledger",
        path=".workshop-lite/ledger/resume-ledgers/<id>.md",
        requires_eval=False,
        produces_built_artifact=False,
    ),
    "canonical-pointer": KindDeclaration(
        kind="canonical-pointer",
        states=("mutable-head",),
        transitions=(("mutable-head", "mutable-head"),),
        lifecycle_family="stateful-pointer",
        body_schema_ref="spec:2.3 canonical-pointer",
        path=".workshop-lite/ledger/pointers/<slug>.md",
        requires_eval=False,
        produces_built_artifact=False,
    ),
}

BUILTIN_KIND_CATALOG: Mapping[str, KindDeclaration] = MappingProxyType(_DECLARATIONS)
BUILTIN_KIND_SET = frozenset(_DECLARATIONS)


def get_kind_declaration(kind: str) -> KindDeclaration:
    try:
        return BUILTIN_KIND_CATALOG[kind]
    except KeyError as exc:
        raise KindCatalogError(f"unknown built-in kind: {kind!r}") from exc


def validate_kind_catalog(
    catalog: Mapping[str, KindDeclaration | Mapping[str, object]] = BUILTIN_KIND_CATALOG,
) -> None:
    actual = set(catalog)
    expected = set(BUILTIN_KIND_SET)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise KindCatalogError(
            f"built-in kind set mismatch; missing={missing}, extra={extra}"
        )
    for key in sorted(expected):
        raw = catalog[key]
        decl = raw.to_dict() if isinstance(raw, KindDeclaration) else dict(raw)
        if decl.get("kind") != key:
            raise KindCatalogError(f"{key}: kind field must match key")
        for field in ("states", "transitions", "lifecycle_family", "body_schema_ref", "path"):
            if field not in decl:
                raise KindCatalogError(f"{key}: missing required declaration field {field}")
        if decl["lifecycle_family"] != "stateless" and not decl["states"]:
            raise KindCatalogError(f"{key}: non-stateless kind must declare states")
        for flag in ("requires_eval", "produces_built_artifact"):
            if flag not in decl:
                raise KindCatalogError(f"{key}: missing required flag {flag}")
            if decl[flag] not in _FLAG_VALUES:
                raise KindCatalogError(f"{key}: invalid {flag} declaration {decl[flag]!r}")


def kind_declarations_as_dicts() -> dict[str, dict]:
    return {kind: decl.to_dict() for kind, decl in BUILTIN_KIND_CATALOG.items()}
