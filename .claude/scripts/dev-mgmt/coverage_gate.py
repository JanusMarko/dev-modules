"""WL2 coverage-gate query definitions (spec §4; BC3.1).

Pins the exact graph queries the design (DOC1 §9) deferred — ``Q1`` (no
under-coverage), ``Q2`` (no scope-creep), and the fulfillment rollup. All run
over the typed link graph (§4.1 vocabulary) as **neighborhood-bounded** set
operations — never a whole-history scan (§4.6). The graph is supplied as
explicit adjacency (a :class:`CoverageGraph`); a caller materializes it from the
BC0.4 derived-reverse link index (``cross_links.derived_reverse_links``) and
hands it here. This module is the pure query layer over that vocabulary.

The §4.1 vocabulary:
  * ``requirements(node)`` — the addressable requirement ids a ``spec``/epic/
    task carries *directly*, plus (transitively) those of everything it
    ``contains``.
  * ``authorizing_records`` — WL2's own build-plan / ``work_order`` nodes (the
    build-step carrying a requirement); ``covers(a, r)`` is the typed edge from
    authorizing record ``a`` to requirement ``r``.
  * ``derived_from(a, r)`` — the DOC1 §5.3 lineage edge from ``a`` back to the
    requirement it serves.
  * ``contains(parent, child)`` — the granularity containment edge
    (epic ▷ task ▷ sub-task).

Parley-agnostic at base (Hard Rule #1): pure library, no parley import / shell.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

# §4.3 — a covering authorizing record only counts toward ``fully_built`` when
# its own status is ``fulfilled``. The string is the spec vocabulary; callers
# map their record's status onto it.
STATUS_FULFILLED = "fulfilled"


@dataclass(frozen=True)
class CoverageGraph:
    """The §4.1 query vocabulary as explicit, neighborhood-bounded adjacency.

    All collections are local adjacency — the queries below are set operations
    over them, so every query is neighborhood-bounded by construction (§4.6).

    * ``direct_requirements`` — ``node_id → {requirement_id, …}`` carried
      *directly* by that node (a spec/epic/task may carry some itself).
    * ``contains`` — ``parent_id → {child_id, …}`` containment edges. The full
      requirement set of a node is its direct set ∪ the sets of everything it
      transitively contains.
    * ``covers`` — ``{(authorizing_record_id, requirement_id), …}`` covers edges.
    * ``derived_from`` — ``{(authorizing_record_id, requirement_id), …}`` lineage
      edges (DOC1 §5.3).
    * ``authorizing_records`` — the node ids that are build-plan/work_order
      authorizing records (the Q2 domain).
    * ``record_status`` — ``authorizing_record_id → status``; a record absent
      from the map is treated as *not* ``fulfilled`` (no silent pass, §4.3 / C6).
    """

    direct_requirements: Mapping[str, frozenset[str]] = field(default_factory=dict)
    contains: Mapping[str, frozenset[str]] = field(default_factory=dict)
    covers: frozenset[tuple[str, str]] = field(default_factory=frozenset)
    derived_from: frozenset[tuple[str, str]] = field(default_factory=frozenset)
    authorizing_records: frozenset[str] = field(default_factory=frozenset)
    record_status: Mapping[str, str] = field(default_factory=dict)


def requirements(graph: CoverageGraph, node: str) -> frozenset[str]:
    """``requirements(node)`` — direct ∪ transitively-contained (§4.1/§4.3).

    Recurses the containment tree. Cycle-safe (a malformed self/loop containment
    edge does not hang): each node is visited once.
    """
    seen_nodes: set[str] = set()
    out: set[str] = set()

    def _walk(n: str) -> None:
        if n in seen_nodes:
            return
        seen_nodes.add(n)
        out.update(graph.direct_requirements.get(n, frozenset()))
        for child in graph.contains.get(n, frozenset()):
            _walk(child)

    _walk(node)
    return frozenset(out)


def _covered_requirements(graph: CoverageGraph) -> frozenset[str]:
    """The set of requirement ids reached by at least one ``covers`` edge."""
    return frozenset(r for (_a, r) in graph.covers)


def q1_undercovered(graph: CoverageGraph, node: str) -> frozenset[str]:
    """Q1 — ``UNDERCOVERED = { r ∈ requirements(node) : ¬∃ a · covers(a, r) }``.

    The build-plan **cannot reach ``ready-to-execute``** while this is non-empty
    (§4.2). Returns the set of uncovered requirements (∅ ⇒ gate passes).
    """
    covered = _covered_requirements(graph)
    return frozenset(r for r in requirements(graph, node) if r not in covered)


def q2_rogue(graph: CoverageGraph, node: str) -> frozenset[str]:
    """Q2 — ``ROGUE = { a ∈ authorizing_records : ¬∃ r ∈ requirements(node) ·
    derived_from(a, r) }`` (§4.2).

    Any authorizing record tracing to no requirement of this node is
    **unrequested work**. Returns the rogue records (∅ ⇒ gate passes).
    """
    reqs = requirements(graph, node)
    derived_targets: dict[str, set[str]] = {}
    for (a, r) in graph.derived_from:
        derived_targets.setdefault(a, set()).add(r)
    return frozenset(
        a for a in graph.authorizing_records
        if not (derived_targets.get(a, set()) & reqs)
    )


def ready_to_execute(graph: CoverageGraph, node: str) -> bool:
    """A build-plan node reaches ``ready-to-execute`` IFF **both** gate queries
    are ∅ (§4.2): ``UNDERCOVERED = ∅ ∧ ROGUE = ∅``.

    ``ready-to-execute`` is a property of the build-plan, **not** a task
    lifecycle state (§4.2).
    """
    return not q1_undercovered(graph, node) and not q2_rogue(graph, node)


def fully_built(graph: CoverageGraph, node: str) -> bool:
    """§4.3 fulfillment rollup — recurses through the containment tree.

    ``fully_built(node) ⇔ ∀ r ∈ requirements(node) · ∃ a · covers(a, r) ∧
    status(a) = fulfilled``. A requirement covered only by a non-``fulfilled``
    (or status-unknown) record does **not** count — no silent pass (§4.3 / C6).
    Vacuously ``True`` for a node carrying no requirements.
    """
    fulfilled_covers: dict[str, set[str]] = {}
    for (a, r) in graph.covers:
        if graph.record_status.get(a) == STATUS_FULFILLED:
            fulfilled_covers.setdefault(r, set()).add(a)
    return all(
        r in fulfilled_covers for r in requirements(graph, node)
    )
