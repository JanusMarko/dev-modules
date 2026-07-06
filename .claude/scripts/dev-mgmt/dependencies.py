"""WL2 ordering-dependency vocabulary (spec §4.5a; BC3.2).

The four typed **ordering edges** that sequence build-steps on WL2's own
build-plan (build-step → build-step), plus the optional **lag/lead** qualifier.
Two invariants this module exists to enforce (the §4.5 / KA-12 kill-axes):

  1. **Unlabelled defaults to FS, NEVER to a non-FS type** (§4.5a: "the default
     when an edge declares no type" is finish-to-start). An untyped edge silently
     becoming SS/FF/SF is the mutant that must die.
  2. **A lag/lead qualifier is honoured, never silently dropped** — a present
     ``{kind, amount, unit}`` qualifier round-trips; absent ⇒ zero lag (§4.5a).

Ordering edges are NOT block-signals (those are §11.5 runtime blocks) and NOT
lineage/containment (those are §4.1 typed links) — this is family (a) of the
DOC1 §5 three-family vocabulary. "One graph, not five subsystems": these are
typed edges on the same graph, this module just types + qualifies them.

Parley-agnostic at base (Hard Rule #1): pure library, no parley import / shell.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

# §4.5a — the four ordering edge types. FS is the default for an unlabelled edge.
FINISH_TO_START = "FS"
START_TO_START = "SS"
FINISH_TO_FINISH = "FF"
START_TO_FINISH = "SF"

ORDERING_EDGE_TYPES: frozenset[str] = frozenset(
    {FINISH_TO_START, START_TO_START, FINISH_TO_FINISH, START_TO_FINISH}
)
DEFAULT_EDGE_TYPE = FINISH_TO_START  # §4.5a — unlabelled ⇒ FS, never non-FS.

# §4.5a lag/lead qualifier value domains.
LAG = "lag"
LEAD = "lead"
_QUALIFIER_KINDS: frozenset[str] = frozenset({LAG, LEAD})
LAG_LEAD_UNITS: frozenset[str] = frozenset({"min", "hour", "day", "step"})


class DependencyError(ValueError):
    """Raised for a structurally-invalid ordering edge or lag/lead qualifier."""


@dataclass(frozen=True)
class LagLead:
    """A §4.5a lag/lead qualifier — ``{kind: lag|lead, amount, unit}``.

    ``lag 1 day`` = "B starts no earlier than 1 day after A finishes." Absent on
    an edge ⇒ zero lag. ``amount`` may be negative only conceptually via the
    ``lead`` kind; we model the two as distinct ``kind`` values per the spec
    (lead = a negative lag) and keep ``amount`` non-negative.
    """

    kind: str
    amount: float
    unit: str

    def __post_init__(self) -> None:
        if self.kind not in _QUALIFIER_KINDS:
            raise DependencyError(
                f"lag/lead kind must be one of {sorted(_QUALIFIER_KINDS)}, "
                f"got {self.kind!r}"
            )
        if self.unit not in LAG_LEAD_UNITS:
            raise DependencyError(
                f"lag/lead unit must be one of {sorted(LAG_LEAD_UNITS)}, "
                f"got {self.unit!r}"
            )
        if not isinstance(self.amount, (int, float)) or isinstance(self.amount, bool):
            raise DependencyError(f"lag/lead amount must be a number, got {self.amount!r}")
        if self.amount < 0:
            raise DependencyError(
                "lag/lead amount must be non-negative (use kind=lead for a lead)"
            )


def parse_lag_lead(raw: Mapping[str, object] | None) -> LagLead | None:
    """Parse a lag/lead qualifier mapping. ``None``/absent ⇒ zero lag (no
    qualifier). A present-but-malformed qualifier RAISES — it is never silently
    dropped (KA-12: a dropped qualifier is the mutant that must die).
    """
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise DependencyError(f"lag/lead qualifier must be a mapping, got {type(raw).__name__}")
    missing = {"kind", "amount", "unit"} - set(raw)
    if missing:
        raise DependencyError(
            f"lag/lead qualifier missing required key(s): {sorted(missing)}"
        )
    return LagLead(kind=str(raw["kind"]), amount=raw["amount"], unit=str(raw["unit"]))  # type: ignore[arg-type]


def resolve_edge_type(label: str | None) -> str:
    """Resolve an ordering edge's type from its declared label (§4.5a).

    An **absent / empty** label resolves to the FS default — **never** to a
    non-FS type (the KA-12 invariant). A present label must be one of the four
    canonical types; an unknown label RAISES (a typo is not silently coerced to
    FS, which would mask an authoring error — fails closed loudly).
    """
    if label is None or (isinstance(label, str) and not label.strip()):
        return DEFAULT_EDGE_TYPE
    norm = str(label).strip().upper()
    if norm not in ORDERING_EDGE_TYPES:
        raise DependencyError(
            f"unknown ordering edge type {label!r}; "
            f"must be one of {sorted(ORDERING_EDGE_TYPES)} (or absent ⇒ FS)"
        )
    return norm


@dataclass(frozen=True)
class OrderingEdge:
    """A typed ordering edge ``predecessor → successor`` with optional lag/lead.

    Build via :func:`make_ordering_edge` so an unlabelled edge is normalized to
    FS and any lag/lead qualifier is parsed (and preserved, never dropped).
    """

    predecessor: str
    successor: str
    edge_type: str
    lag_lead: LagLead | None = None


def make_ordering_edge(
    predecessor: str,
    successor: str,
    *,
    edge_type: str | None = None,
    lag_lead: Mapping[str, object] | None = None,
) -> OrderingEdge:
    """Construct a normalized :class:`OrderingEdge` (§4.5a).

    ``edge_type`` absent ⇒ FS (never non-FS); ``lag_lead`` parsed + preserved
    (a present qualifier is honoured, never silently dropped).
    """
    return OrderingEdge(
        predecessor=predecessor,
        successor=successor,
        edge_type=resolve_edge_type(edge_type),
        lag_lead=parse_lag_lead(lag_lead),
    )
