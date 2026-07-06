"""WL2 per-kind body (frontmatter) schemas — single source of truth.

BC1.1 codifies spec §2.3's per-kind body schemas as DATA, reconciled against
the live writers + validators (``entities.py`` / ``prd.py`` / ``dispatch.py`` /
``wip_claim.py`` / ``validators.py``), not only the template baseline
(``templates.py``). Every field maps to a Workshop entity column (Hard Rule 2).

This module is declarative: each :class:`BodySchema` names the kind's common +
required + optional frontmatter fields and whether the kind carries the
Phase-4 ``owner_user`` ownership field (BC1.3 — the 13/20 carry-set,
master design §3.2 / D-WL-11). The carry membership is enforced structurally
by :func:`validate_body_schema_registry`: a kind carries ``owner_user`` IFF it
is in :data:`OWNER_USER_CARRY_KINDS`, and that set is exactly the spec's 13.

Reconciliation (KA-4): for the §2.3 kinds backed by a flat-file validator, the
schema's ``required`` tuple equals the validator's ``_*_REQUIRED`` tuple —
asserted by :func:`reconcile_with_validators`.

The 3 non-§2.3 kinds (``eval-corpus`` · ``eval-case`` · ``denial``) are owned
by spec §5.1 / §5.2 / §9.1 (other cohorts); they appear here only so the
owner_user carry-set spans the full 20-kind catalog. They are marked
``schema_external=True`` and excluded from §2.3 reconciliation — BC1 does not
redefine another cohort's schema (cite, never re-define).
"""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping


class BodySchemaError(ValueError):
    """Raised when the body-schema registry is internally inconsistent."""


OWNER_USER = "owner_user"
OWNER_USER_DEFAULT = "user/local"


@dataclass(frozen=True)
class BodySchema:
    """Declared frontmatter shape for one record kind.

    ``required`` and ``optional`` are disjoint; their union is the kind's known
    field-set. ``type_value`` is the literal value of the ``type`` frontmatter
    field (often the kind name, but ``sprint`` → ``plan``). ``owner_user_carry``
    is derived from :data:`OWNER_USER_CARRY_KINDS` at construction and must
    agree with the presence of ``owner_user`` in the field-set.
    ``schema_external`` marks a kind whose body schema is owned by another spec
    section / cohort (eval-corpus / eval-case / denial → §5/§9).
    """

    kind: str
    type_value: str
    spec_section: str
    required: tuple[str, ...]
    optional: tuple[str, ...] = ()
    owner_user_carry: bool = False
    schema_external: bool = False

    @property
    def fields(self) -> frozenset[str]:
        return frozenset(self.required) | frozenset(self.optional)

    def is_required(self, name: str) -> bool:
        return name in self.required


# The 13-of-20 owner_user carry-set (spec §2.3; master design §3.2 / D-WL-11).
# Carries (13): the 9 v1 Phase-4 kinds + the 4 new authored kinds.
# NOT (7): task · conversation · gate · block-signal · eval-corpus · eval-case
# · denial. (13 + 7 = 20.)
OWNER_USER_CARRY_KINDS: frozenset[str] = frozenset({
    # 9 v1 Phase-4 kinds
    "decision",
    "sprint",
    "retrospective",
    "handoff",
    "issue",
    "review",
    "standing_dispatch",
    "prd",
    "wip_claim",
    # 4 new authored kinds (BC1.2)
    "workflow",
    "role-set",
    "resume-ledger",
    "canonical-pointer",
})

# Kinds NOT carrying owner_user (the explicit 7).
OWNER_USER_NON_CARRY_KINDS: frozenset[str] = frozenset({
    "task",
    "conversation",
    "gate",
    "block-signal",
    "eval-corpus",
    "eval-case",
    "denial",
})

def _schema(
    kind: str,
    *,
    type_value: str | None = None,
    spec_section: str,
    required: tuple[str, ...],
    optional: tuple[str, ...] = (),
    schema_external: bool = False,
) -> BodySchema:
    """Build a BodySchema, deriving owner_user_carry from the canonical set
    and adding owner_user to the optional field-set for carry kinds that do
    not already require it (so ``fields`` is carry-complete)."""
    carry = kind in OWNER_USER_CARRY_KINDS
    if carry and OWNER_USER not in required and OWNER_USER not in optional:
        optional = optional + (OWNER_USER,)
    return BodySchema(
        kind=kind,
        type_value=type_value if type_value is not None else kind,
        spec_section=spec_section,
        required=required,
        optional=optional,
        owner_user_carry=carry,
        schema_external=schema_external,
    )


_SCHEMAS: dict[str, BodySchema] = {
    # ----- v1 kinds (§2.3) -----
    "decision": _schema(
        "decision",
        spec_section="2.3",
        required=("id", "type", "title", "status", "scope", "options",
                  "created_at", "author"),
        optional=("sprint_id", "stage", "authored_with", "linked_decisions",
                  "linked_reviews", "linked_msg_ids", "supersedes",
                  "decision_shape"),
    ),
    "sprint": _schema(
        "sprint",
        type_value="plan",
        spec_section="2.3",
        required=("id", "type", "title", "sprint_id", "status", "version",
                  "created_at", "author"),
        optional=("plan_type", "previous_version_id", "linked_design_docs",
                  "closed_at"),
    ),
    "retrospective": _schema(
        "retrospective",
        spec_section="2.3",
        required=("id", "type", "title", "sprint_id", "status", "shipped_at",
                  "created_at", "author"),
        optional=("linked_decisions", "linked_reviews", "test_results"),
    ),
    "handoff": _schema(
        "handoff",
        spec_section="2.3",
        required=("id", "type", "title", "topic", "trigger", "status",
                  "created_at", "author"),
        optional=("sprint_id", "stage", "since_handoff_id", "since_msg_id",
                  "linked_decisions", "linked_issues", "linked_tasks",
                  "linked_msg_ids", "next_action"),
    ),
    "issue": _schema(
        "issue",
        spec_section="2.3",
        required=("id", "type", "title", "status", "severity", "scope",
                  "created_at", "reporter"),
        optional=("sprint_id", "stage", "class", "linked_decisions",
                  "linked_reviews", "linked_msg_ids"),
    ),
    "review": _schema(
        "review",
        spec_section="2.3",
        required=("id", "type", "review_type", "title", "status", "scope",
                  "created_at", "author"),
        optional=("sprint_id", "stage", "findings", "linked_decisions",
                  "linked_reviews", "linked_msg_ids", "accurate_trail"),
    ),
    "task": _schema(
        "task",
        spec_section="2.3",
        # task is an inline tasks.md line, not a standalone file; the parsed
        # shape is the schema. status is the R6 six-state value (BC1.5).
        required=("id", "type", "status", "description", "sprint_id"),
        optional=("assignee", "linked_issues", "linked_decisions"),
    ),
    "conversation": _schema(
        "conversation",
        spec_section="2.3",
        required=("id", "type", "title", "topic", "zone", "participants",
                  "verbatim_msg_range", "created_at"),
        optional=("sprint_id", "stage", "started_at", "ended_at",
                  "linked_design_docs", "linked_decisions", "linked_reviews",
                  "linked_issues", "linked_handoffs", "linked_msg_ids"),
    ),
    "prd": _schema(
        "prd",
        spec_section="2.3",
        # prd's lifecycle column is `state`, not `status` (the one deliberate
        # exception to the substrate-uniform `status` convention).
        required=("id", "type", "title", "state", "scope", "created_at",
                  "author", "owner_user"),
        optional=("linked_msg_ids", "linked_decisions", "cross_repo_prds",
                  "parley_external_ref", "ratified_at", "ratified_by",
                  "technical_plan_url", "shipped_sha"),
    ),
    "standing_dispatch": _schema(
        "standing_dispatch",
        spec_section="2.3",
        required=("id", "type", "title", "status", "purpose", "scope",
                  "recipients", "expected_outcome", "created_at", "created_by",
                  "owner_user"),
        optional=("sprint_id", "stage", "deadline", "expires_at",
                  "satisfy_quorum", "supersedes", "parley_external_ref",
                  "linked_msg_ids", "linked_decisions", "linked_handoffs",
                  "linked_reviews", "satisfied_at", "satisfied_by",
                  "satisfy_rationale", "superseded_at", "superseded_by"),
    ),
    "wip_claim": _schema(
        "wip_claim",
        spec_section="2.3",
        required=("id", "type", "title", "seat", "paths", "scope", "status",
                  "token_state", "expires_at", "created_at", "created_by",
                  "owner_user"),
        optional=("sprint_id", "stage", "linked_sprints", "linked_decisions",
                  "linked_msg_ids"),
    ),
    "gate": _schema(
        "gate",
        spec_section="2.3",
        required=("id", "type", "gate_id", "created", "gated_by", "status",
                  "how_to_close"),
        optional=("plan_ref", "ttl_until", "what_you_can_do",
                  "what_you_cannot_do", "linked_msg_ids"),
    ),
    # ----- 5 new kinds (§2.3; BC1.2) -----
    "workflow": _schema(
        "workflow",
        spec_section="2.3",
        required=("id", "type", "title", "status", "stages", "library_layer",
                  "is_default", "created_at", "author", "owner_user"),
        optional=("supersedes", "linked_decisions"),
    ),
    "role-set": _schema(
        "role-set",
        spec_section="2.3",
        required=("id", "type", "title", "status", "roles", "sod_predicates",
                  "per_stage_markers", "library_layer", "is_default",
                  "created_at", "author", "owner_user"),
        optional=("supersedes",),
    ),
    "block-signal": _schema(
        "block-signal",
        spec_section="2.3",
        required=("id", "type", "blocked_subject", "waits_on", "class",
                  "status", "created_at", "created_by"),
        optional=("deadline", "ttl", "inferred_by"),
    ),
    "resume-ledger": _schema(
        "resume-ledger",
        spec_section="2.3",
        required=("id", "type", "worker", "status", "in_flight_state",
                  "next_actions", "created_at", "author", "owner_user"),
        optional=("canonical_pointer_ref", "supersedes"),
    ),
    "canonical-pointer": _schema(
        "canonical-pointer",
        spec_section="2.3",
        required=("id", "type", "names", "points_to", "updated_at",
                  "updated_by", "owner_user"),
        optional=(),
    ),
    # ----- 3 non-§2.3 kinds (owned by §5/§9; here only for carry-set span) ---
    "eval-corpus": _schema(
        "eval-corpus",
        spec_section="5.1",
        required=("id", "type"),
        schema_external=True,
    ),
    "eval-case": _schema(
        "eval-case",
        spec_section="5.2",
        required=("id", "type"),
        schema_external=True,
    ),
    "denial": _schema(
        "denial",
        spec_section="9.1",
        required=("id", "type", "denied_subject", "denial_class", "from_state",
                  "reason_ref", "raised_by", "handler", "resolution", "created_at"),
    ),
}

BODY_SCHEMAS: Mapping[str, BodySchema] = MappingProxyType(_SCHEMAS)
BODY_SCHEMA_KINDS = frozenset(_SCHEMAS)

# §2.3 kinds reconciled against a flat-file validator's _*_REQUIRED tuple.
# Keyed kind → the validators module attribute name (KA-4 reconciliation).
_VALIDATOR_REQUIRED_ATTR: dict[str, str] = {
    "decision": "_DECISION_REQUIRED",
    "sprint": "_SPRINT_PLAN_REQUIRED",
    "retrospective": "_RETRO_REQUIRED",
    "handoff": "_HANDOFF_REQUIRED",
    "issue": "_ISSUE_REQUIRED",
    "review": "_REVIEW_REQUIRED",
    "conversation": "_CONVERSATION_REQUIRED",
    "prd": "_PRD_REQUIRED",
    "standing_dispatch": "_STANDING_DISPATCH_REQUIRED",
    "wip_claim": "_WIP_CLAIM_REQUIRED",
    "gate": "_GATE_REQUIRED",
}


def get_body_schema(kind: str) -> BodySchema:
    try:
        return BODY_SCHEMAS[kind]
    except KeyError as exc:
        raise BodySchemaError(f"unknown body-schema kind: {kind!r}") from exc


def owner_user_carry_kinds() -> frozenset[str]:
    """The exact set of kinds that carry the Phase-4 owner_user field (13)."""
    return OWNER_USER_CARRY_KINDS


def resolve_owner_user(kind: str, fm: Mapping[str, object]) -> str | None:
    """Read-time owner_user resolution (spec §2.3; BC1.3).

    For a carry kind: return the stamped ``owner_user`` if present + non-empty,
    else the read-time default ``user/local`` (so on-disk files written before
    the field existed parse with an owner). For a non-carry kind: return None
    (the kind has no owner). Raises for an unknown kind.
    """
    schema = get_body_schema(kind)
    if not schema.owner_user_carry:
        return None
    value = fm.get(OWNER_USER)
    if value in (None, ""):
        return OWNER_USER_DEFAULT
    return value  # type: ignore[return-value]


def validate_body_schema_registry(
    schemas: Mapping[str, BodySchema] = BODY_SCHEMAS,
) -> None:
    """Structural self-check of the body-schema registry.

    Raises :class:`BodySchemaError` on:
      - carry-set size ≠ 13 (KA-5 floor);
      - a kind whose ``owner_user_carry`` disagrees with membership in
        :data:`OWNER_USER_CARRY_KINDS`;
      - a carry kind missing ``owner_user`` from its field-set, or a non-carry
        kind carrying ``owner_user`` (the KA-5 mutation-kill axis);
      - required ∩ optional ≠ ∅;
      - a §2.3 kind with an empty required tuple.
    """
    if len(OWNER_USER_CARRY_KINDS) != 13:
        raise BodySchemaError(
            f"owner_user carry-set must be exactly 13, got "
            f"{len(OWNER_USER_CARRY_KINDS)}"
        )
    if OWNER_USER_CARRY_KINDS & OWNER_USER_NON_CARRY_KINDS:
        raise BodySchemaError("carry and non-carry sets overlap")
    union = OWNER_USER_CARRY_KINDS | OWNER_USER_NON_CARRY_KINDS
    if union != set(schemas):
        missing = sorted(set(schemas) - union)
        extra = sorted(union - set(schemas))
        raise BodySchemaError(
            f"carry∪non-carry must span all kinds; missing={missing}, "
            f"extra={extra}"
        )

    for kind, schema in schemas.items():
        carry_expected = kind in OWNER_USER_CARRY_KINDS
        if schema.owner_user_carry != carry_expected:
            raise BodySchemaError(
                f"{kind}: owner_user_carry={schema.owner_user_carry} but "
                f"canonical membership is {carry_expected}"
            )
        has_owner = OWNER_USER in schema.fields
        if carry_expected and not has_owner:
            raise BodySchemaError(
                f"{kind}: carry kind must declare owner_user in its field-set"
            )
        if not carry_expected and has_owner:
            raise BodySchemaError(
                f"{kind}: non-carry kind must NOT declare owner_user"
            )
        overlap = frozenset(schema.required) & frozenset(schema.optional)
        if overlap:
            raise BodySchemaError(
                f"{kind}: required ∩ optional must be empty, got "
                f"{sorted(overlap)}"
            )
        if not schema.schema_external and not schema.required:
            raise BodySchemaError(f"{kind}: §2.3 kind must declare required fields")


def reconcile_with_validators(validators_module) -> None:
    """Assert each backed kind's required tuple equals the validator's
    ``_*_REQUIRED`` (KA-4 reconciliation). Raises on any drift."""
    for kind, attr in _VALIDATOR_REQUIRED_ATTR.items():
        validator_required = tuple(getattr(validators_module, attr))
        schema_required = get_body_schema(kind).required
        if set(schema_required) != set(validator_required):
            raise BodySchemaError(
                f"{kind}: body-schema required {sorted(schema_required)} != "
                f"validator {attr} {sorted(validator_required)}"
            )
