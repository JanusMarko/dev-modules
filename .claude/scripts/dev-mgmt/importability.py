"""WL2 → heavyweight-Workshop importability field-map (spec §13; BC6.1).

Every field of all 20 built-in kinds maps **1:1** to either a first-class
Workshop entity COLUMN (§13.1 rule 1 — the common families) or the
``metadata_`` JSONB overflow (§13.1 rule 2 — kind-specific fields with no
typed column) — **NO orphan field**. This is the §10 importability non-goal's
guaranteed property: a future import to a heavyweight-Workshop API becomes a
frontmatter-parse + INSERT (master design Residual #5; Hard Rule #2).

Kill-axis (build-plan App B):
  * **KA-26** (§13) — a kind field that maps to neither a Workshop column nor
    the ``metadata_`` JSONB (an *orphan*) yet importability passes → die. The
    classifier :func:`classify_field` is **total** over the enumerated field
    set; :func:`orphan_fields` surfaces any field whose destination is
    ``UNMAPPED``, and :func:`importability_holds` / :func:`importability_report`
    **fail closed** on a non-empty orphan set (or on any catalog kind missing a
    schema, §13.2(c)).

This is a **structural / deterministic** check (RE=no): every field is
classified by name against the §13.1 rule-1 table (a fixed vocabulary) or the
``linked_*`` link-graph family, else routed to the JSONB overflow — a lookup,
never a graded judgment.

Parley-agnostic at base (Hard Rule #1): pure library, no parley import / shell.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

import body_schemas
import kind_registry


# ---------------------------------------------------------------------------
# §13.1 rule 1 — common families → first-class Workshop entity columns.
# The fixed common-family vocabulary (spec §13.1 table). Field name → column.
# ---------------------------------------------------------------------------
COMMON_FAMILY_COLUMNS: Mapping[str, str] = MappingProxyType({
    "id": "id",                       # the date-counter-slug id (or natural key)
    "type": "entity_kind",            # the 20-kind discriminator
    "title": "title",
    "status": "status",               # substrate-uniform status
    "state": "status",                # prd's forward-only lifecycle column → status
    "created_at": "created_at",       # ISO-8601
    "author": "author_id",            # role/seat id
    "reporter": "author_id",
    "created_by": "author_id",
    "owner_user": "owner_user",       # Phase-4 ownership thread
    "scope": "scope",
    "sprint_id": "sprint_id",
    "stage": "stage",
    "parley_external_ref": "external_ref",   # workshop-lite-<kind>://<id> grammar
})

# §13.1 rule 1 — the typed link-graph edge family. Any ``linked_*`` field maps
# to the derived-reverse typed link-graph edges (§4 / DOC1), not a scalar column.
LINK_GRAPH_PREFIX = "linked_"
LINK_GRAPH_COLUMN = "link_graph_edge"

# The JSONB overflow channel (§13.1 rule 2 — the established overflow, see the
# dispatch.py module note). Every kind-specific field with no typed column lands
# here; nothing is dropped.
METADATA_JSONB = "metadata_"


# ---------------------------------------------------------------------------
# §5.1 / §5.2 — the 2 external-schema kinds (body_schemas marks these
# schema_external=True with only {id,type}; their full field set is owned by §5).
# Enumerated here field-level so the importability map is exhaustive (§13.2(a)).
# ---------------------------------------------------------------------------
EVAL_CORPUS_FIELDS: frozenset[str] = frozenset({
    "id", "type", "created_at", "author",
    "target_component", "independent_supplier", "discriminant", "pass_bar",
    "scoring_mode", "judge", "judge_consistency_protocol",
    "red_without_proof", "holdout", "refresh_cadence", "human_ratification",
    "linked_cases", "linked_decisions", "linked_reviews", "linked_msg_ids",
})
EVAL_CASE_FIELDS: frozenset[str] = frozenset({
    "id", "type", "created_at", "author",
    "corpus_ref", "category", "observable_inputs", "scoring_key", "in_holdout",
})
_EXTERNAL_KIND_FIELDS: Mapping[str, frozenset[str]] = MappingProxyType({
    "eval-corpus": EVAL_CORPUS_FIELDS,
    "eval-case": EVAL_CASE_FIELDS,
})


# ---------------------------------------------------------------------------
# Destination model
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Destination:
    """Where a WL2 field lands in the heavyweight-Workshop schema.

    ``channel`` ∈ {``"column"``, ``"jsonb"``, ``"unmapped"``}. ``"unmapped"`` is
    the **orphan sentinel** (§13 / KA-26): a field the classifier could not route
    to either a named column or the JSONB overflow. It is unreachable for the
    shipped classifier (the JSONB fallback is total) and exists so the no-orphan
    check can *detect* a mutation that drops the fallback — fail-closed, not a
    silent pass.
    """

    channel: str
    column: str | None = None

    @property
    def is_orphan(self) -> bool:
        return self.channel == "unmapped"


def classify_field(field: str) -> Destination:
    """Route one field to its Workshop destination (§13.1 rules 1 & 2).

    Rule 1: a common-family field → its named column; a ``linked_*`` field → the
    typed link-graph edges. Rule 2: any other (kind-specific) field → the
    ``metadata_`` JSONB overflow. **Total** — every field name yields a
    destination; ``unmapped`` is never returned by this shipped classifier.
    """
    if field in COMMON_FAMILY_COLUMNS:
        return Destination("column", COMMON_FAMILY_COLUMNS[field])
    if field.startswith(LINK_GRAPH_PREFIX):
        return Destination("column", LINK_GRAPH_COLUMN)
    # Rule 2 — kind-specific overflow. Nothing is dropped.
    return Destination("jsonb", METADATA_JSONB)


# ---------------------------------------------------------------------------
# Field enumeration over the 20-kind catalog
# ---------------------------------------------------------------------------
def kind_field_sets() -> dict[str, frozenset[str]]:
    """The full field set (required ∪ optional) for every built-in kind.

    The 18 schema-internal kinds draw from :data:`body_schemas.BODY_SCHEMAS`;
    the 2 ``schema_external`` kinds (``eval-corpus`` / ``eval-case``) draw their
    §5 field sets from :data:`_EXTERNAL_KIND_FIELDS`.
    """
    out: dict[str, frozenset[str]] = {}
    for kind, schema in body_schemas.BODY_SCHEMAS.items():
        if kind in _EXTERNAL_KIND_FIELDS:
            out[kind] = _EXTERNAL_KIND_FIELDS[kind]
        else:
            out[kind] = frozenset(schema.required) | frozenset(schema.optional)
    return out


def field_map() -> dict[str, dict[str, Destination]]:
    """The full importability field-map: ``kind → field → Destination`` over
    all 20 built-in kinds."""
    return {
        kind: {field: classify_field(field) for field in sorted(fields)}
        for kind, fields in kind_field_sets().items()
    }


# ---------------------------------------------------------------------------
# §13.2 acceptance — schema-coverage check (the no-orphan gate, fail-closed)
# ---------------------------------------------------------------------------
def orphan_fields(
    fmap: Mapping[str, Mapping[str, Destination]] | None = None,
) -> tuple[tuple[str, str], ...]:
    """The ``(kind, field)`` pairs whose destination is an orphan (§13 / KA-26).

    Empty ⇔ every field resolves to a named column or the JSONB overflow.
    """
    fmap = field_map() if fmap is None else fmap
    return tuple(
        (kind, field)
        for kind, fields in sorted(fmap.items())
        for field, dest in sorted(fields.items())
        if dest.is_orphan
    )


def missing_kinds(
    catalog: frozenset[str] = kind_registry.BUILTIN_KIND_SET,
) -> frozenset[str]:
    """Catalog kinds with no enumerated field schema (§13.2(c))."""
    return frozenset(catalog) - frozenset(kind_field_sets())


def importability_holds() -> bool:
    """``True`` iff §13.2 holds: no kind missing a schema AND no orphan field."""
    return not missing_kinds() and not orphan_fields()


@dataclass(frozen=True)
class ImportabilityReport:
    """The §13.2 acceptance verdict, fail-closed."""

    passed: bool
    n_kinds: int
    n_fields: int
    orphans: tuple[tuple[str, str], ...]
    missing_kinds: tuple[str, ...]
    reason: str


def importability_report() -> ImportabilityReport:
    """Run the §13.2 schema-coverage check across the 20-kind catalog.

    Fails closed: a non-empty orphan set OR any catalog kind missing a schema
    ⇒ ``passed = False``.
    """
    fmap = field_map()
    orphans = orphan_fields(fmap)
    missing = tuple(sorted(missing_kinds()))
    n_fields = sum(len(fields) for fields in fmap.values())
    passed = not orphans and not missing
    if passed:
        reason = (
            f"importability holds — {len(fmap)} kinds, {n_fields} fields, "
            "every field → a Workshop column or metadata_ JSONB (no orphan)"
        )
    elif missing:
        reason = f"{len(missing)} catalog kind(s) missing a schema: {missing}"
    else:
        reason = f"{len(orphans)} orphan field(s) (no Workshop destination)"
    return ImportabilityReport(
        passed=passed,
        n_kinds=len(fmap),
        n_fields=n_fields,
        orphans=orphans,
        missing_kinds=missing,
        reason=reason,
    )
