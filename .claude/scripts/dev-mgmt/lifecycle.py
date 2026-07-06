"""WL2 R6 six-state lifecycle machine (spec §11.1 / §11.4; BC2.1 + BC2.2).

The artifact work-lifecycle ``created → picked-up → in-progress → verified →
done → cleaned-up`` (``cleaned-up`` terminal) at field-level edge precision: each
edge's **firer**, **guard**, and **record written**. The transition engine
enforces the guards and, on a guard miss, returns an instance of the §9 canonical
denial envelope (``denial.py``) — reused, never redefined (BC2.4). A denial
leaves the subject in its ``from_state`` (§9.3 stays-put).

Anchors a builder must not miss (§11.1):
  * ``done``'s entry firer is the ``verified → done`` **acceptance**, NOT the
    closure signal.
  * a failing acceptance is a **gate-refused denial that leaves the task
    ``verified``** — rework is the separate *deliberate* ``verified → in-progress``
    edge, **never** an auto-regress.
  * abandonment is reachable **only before ``done``**.

Parley-agnostic at base (Hard Rule #1): pure library, no parley import / shell.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Mapping

import denial


class LifecycleError(ValueError):
    """Raised for a structurally-impossible transition request (no such edge)."""


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


# §11.1 state set; cleaned-up is the single terminal sink.
R6_STATES: tuple[str, ...] = (
    "created", "picked-up", "in-progress", "verified", "done", "cleaned-up",
)
TERMINAL_STATE = "cleaned-up"
_PRE_DONE_STATES = frozenset({"created", "picked-up", "in-progress", "verified"})

# §11.1 firers (who fires the edge). Labels, not concrete role-ids.
FIRER_FRAMEWORK = "framework"
FIRER_WORKER = "worker"
FIRER_ACCEPTING_ROLE = "accepting-role-identity"
FIRER_ACCEPTANCE_HANDLER = "acceptance-stage-handler"
FIRER_WL2 = "wl2"
FIRER_ABANDON_AUTHORITY = "abandon-authority"  # the task's lead


@dataclass(frozen=True)
class Edge:
    from_state: str
    to_state: str
    firer: str
    guard: str | None        # None = unguarded edge
    record: str              # the record written on a successful firing
    terminal: bool


# §11.1 canonical edge table — self-contained, field-level (DOC1 §6/§15 wins on
# any conflict). ``abandon`` is modelled as the special "any pre-done →
# cleaned-up" edge (resolved per-source by ``find_edge``).
_REWORK_EDGE = Edge(
    from_state="verified", to_state="in-progress", firer=FIRER_ACCEPTANCE_HANDLER,
    guard="rework-decision", record="task:in-progress", terminal=False,
)
_ABANDON_EDGE = Edge(
    from_state="<pre-done>", to_state="cleaned-up", firer=FIRER_ABANDON_AUTHORITY,
    guard="pre-done", record="closure-record:abandoned", terminal=True,
)

R6_EDGES: tuple[Edge, ...] = (
    Edge("created", "picked-up", FIRER_FRAMEWORK, "work-readiness",
         "task:picked-up", False),
    Edge("picked-up", "in-progress", FIRER_WORKER, None,
         "task:in-progress", False),
    Edge("in-progress", "verified", FIRER_WORKER, None,
         "task:verified", False),
    Edge("verified", "done", FIRER_ACCEPTING_ROLE, "acceptance-conjunction",
         "acceptance-verdict+task:done", False),
    _REWORK_EDGE,
    Edge("done", "cleaned-up", FIRER_WL2, "close-archive",
         "closure-record:completed-or-superseded", True),
    _ABANDON_EDGE,
)


@dataclass(frozen=True)
class TransitionResult:
    ok: bool
    from_state: str
    to_state: str | None     # None on a denial (subject stays in from_state)
    firer: str | None
    record: str | None       # the record to write on success
    denial: dict | None      # the §9 envelope on a guard miss


def find_edge(from_state: str, to_state: str) -> Edge | None:
    """Resolve the canonical edge ``from_state → to_state`` (§11.1).

    ``* → cleaned-up`` resolves to the ``done → cleaned-up`` closure edge from
    ``done``, else to the ``abandon`` edge (reachable only from a pre-done
    state). Returns ``None`` if no such edge exists.
    """
    if to_state == "cleaned-up":
        if from_state == "done":
            return next(e for e in R6_EDGES if e.from_state == "done"
                        and e.to_state == "cleaned-up")
        if from_state in _PRE_DONE_STATES:
            return _ABANDON_EDGE
        return None
    for edge in R6_EDGES:
        if edge.from_state == from_state and edge.to_state == to_state:
            return edge
    return None


def allowed_edges(from_state: str) -> list[Edge]:
    """Every edge fireable out of ``from_state`` (including abandon)."""
    out: list[Edge] = []
    for edge in R6_EDGES:
        if edge is _ABANDON_EDGE:
            continue
        if edge.from_state == from_state:
            out.append(edge)
    if from_state in _PRE_DONE_STATES:
        out.append(_ABANDON_EDGE)
    return out


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------

# §11.4 — the verified→done acceptance conjunction. review ∧ SoD always apply;
# eval iff requires_eval; cert iff produces_built_artifact (§6.5).
# most-restrictive-binds: every applicable conjunct must hold.


def acceptance_missing_conjuncts(
    *,
    review: bool,
    sod: bool,
    eval_pass: bool | None = None,
    cert_pass: bool | None = None,
    requires_eval: bool = False,
    produces_built_artifact: bool = False,
) -> list[str]:
    """Return the list of UNMET applicable conjuncts for ``verified → done``.

    review ∧ SoD always apply. eval applies iff ``requires_eval``; cert applies
    iff ``produces_built_artifact`` (§6.5). most-restrictive-binds — an empty
    return means the conjunction is satisfied. A self-scoped conjunct that
    applies but whose signal is ``None`` (absent) counts as UNMET (no silent
    pass, C6).
    """
    missing: list[str] = []
    if not review:
        missing.append("review")
    if not sod:
        missing.append("sod")
    if requires_eval and not bool(eval_pass):
        missing.append("eval")
    if produces_built_artifact and not bool(cert_pass):
        missing.append("cert")
    return missing


# §11.2 — a declared prerequisite (an ordering edge) is satisfied iff its task
# has reached a terminal-success state. ``cleaned-up`` is included (a prereq that
# completed-then-closed still satisfies); ``abandoned`` does not appear because
# an abandoned task never reaches done/cleaned-up via the success path.
_SATISFYING_PREREQ_STATES = frozenset({"done", "cleaned-up"})


def unmet_prerequisites(
    task: Mapping[str, object],
    prereq_states: Mapping[str, str] | None,
) -> list[str]:
    """Return the declared prerequisite links that are NOT satisfied (§11.2).

    Deterministic: a prerequisite id listed in ``task['prerequisites']`` is
    satisfied iff ``prereq_states[id]`` is a terminal-success state
    (done | cleaned-up). A prerequisite ABSENT from ``prereq_states`` (unknown
    state) counts as UNMET — no silent pass (C6).
    """
    declared = task.get("prerequisites") or []
    if not isinstance(declared, (list, tuple)):
        declared = [declared]
    states = prereq_states or {}
    return [
        str(pid) for pid in declared
        if states.get(str(pid)) not in _SATISFYING_PREREQ_STATES
    ]


def work_readiness(
    task: Mapping[str, object],
    *,
    prereq_states: Mapping[str, str] | None = None,
    work_order_ratified: bool | None = None,
) -> bool:
    """Deterministic ``created → picked-up`` guard predicate (§11.2; BC2.2).

    TRUE iff: (a) ``task.status == created``; (b) every declared prerequisite
    link is satisfied (deterministically resolved from ``prereq_states`` — the
    project's own "authorized to start" criterion folds in here as an ordinary
    prerequisite, no separate WL2 auth kind); (c) no abandon has fired
    (``task.abandoned`` falsy). **Under an orchestrator** the effective guard
    tightens to ``work-readiness ∧ work_order-ratified`` (bucket-3, composes by
    tightening): pass ``work_order_ratified`` (None = standalone, no orchestrator).
    """
    if task.get("status") != "created":
        return False
    if task.get("abandoned"):
        return False
    if unmet_prerequisites(task, prereq_states):
        return False
    if work_order_ratified is not None and not work_order_ratified:
        return False
    return True


# ---------------------------------------------------------------------------
# Transition engine
# ---------------------------------------------------------------------------


def _guard_miss_denial(
    *,
    task: Mapping[str, object],
    from_state: str,
    denial_class: str,
    reason_ref: str,
    handler: str | None,
) -> dict:
    """Build the §9 envelope for a guard miss (reuses denial.py — no redefine)."""
    return denial.build_denial(
        id=f"inflight:{task.get('id', '?')}",
        denied_subject=str(task.get("id", "?")),
        denial_class=denial_class,
        from_state=from_state,
        reason_ref=reason_ref,
        created_at=_now(),
        handler=handler,
    )


def attempt_transition(
    task: Mapping[str, object],
    to_state: str,
    *,
    # created→picked-up guard inputs
    prereq_states: Mapping[str, str] | None = None,
    work_order_ratified: bool | None = None,
    readiness_handler: str | None = None,
    # verified→done acceptance conjunction inputs
    review: bool = False,
    sod: bool = False,
    eval_pass: bool | None = None,
    cert_pass: bool | None = None,
    acceptance_handler: str | None = None,
    # verified→in-progress rework
    rework_decision: bool = False,
) -> TransitionResult:
    """Attempt an R6 transition, enforcing the edge's firer-record + guard.

    On a guard miss returns ``ok=False`` with a §9 denial envelope and
    ``to_state=None`` — the subject **stays in its ``from_state``** (§9.3). A
    structurally-impossible edge (no such transition in the model) raises
    ``LifecycleError`` (that is a programming error, not a denial).

    ``requires_eval`` / ``produces_built_artifact`` are read off the ``task`` for
    the acceptance conjunction (§6.5 self-scoping).
    """
    from_state = str(task.get("status"))
    edge = find_edge(from_state, to_state)
    if edge is None:
        raise LifecycleError(
            f"no R6 edge {from_state!r} → {to_state!r} (allowed: "
            f"{[e.to_state for e in allowed_edges(from_state)]})"
        )

    def ok() -> TransitionResult:
        return TransitionResult(True, from_state, to_state, edge.firer,
                                edge.record, None)

    # --- unguarded edges (picked-up→in-progress, in-progress→verified) ---
    if edge.guard is None:
        return ok()

    # --- created→picked-up : work-readiness (∧ work_order under orchestrator) ---
    if edge.guard == "work-readiness":
        if work_readiness(task, prereq_states=prereq_states,
                          work_order_ratified=work_order_ratified):
            return ok()
        reason = "work-readiness unmet: "
        unmet = unmet_prerequisites(task, prereq_states)
        if task.get("status") != "created":
            reason += "not in created"
        elif task.get("abandoned"):
            reason += "an abandon has fired"
        elif unmet:
            reason += "unsatisfied prerequisite(s): " + ", ".join(unmet)
        else:
            reason += "work_order not ratified (orchestrator)"
        return TransitionResult(
            False, from_state, None, None, None,
            _guard_miss_denial(task=task, from_state=from_state,
                               denial_class="guard-miss", reason_ref=reason,
                               handler=readiness_handler),
        )

    # --- verified→done : acceptance conjunction, most-restrictive-binds ---
    if edge.guard == "acceptance-conjunction":
        missing = acceptance_missing_conjuncts(
            review=review, sod=sod, eval_pass=eval_pass, cert_pass=cert_pass,
            requires_eval=bool(task.get("requires_eval")),
            produces_built_artifact=bool(task.get("produces_built_artifact")),
        )
        if not missing:
            return ok()
        return TransitionResult(
            False, from_state, None, None, None,
            denial.build_denial(
                id=f"inflight:{task.get('id', '?')}",
                denied_subject=str(task.get("id", "?")),
                denial_class="gate-refused",
                from_state=from_state,
                reason_ref="acceptance conjunction unmet: " + ", ".join(missing),
                created_at=_now(),
                handler=acceptance_handler,
            ),
        )

    # --- verified→in-progress : rework, deliberate only (never auto-regress) ---
    if edge.guard == "rework-decision":
        if rework_decision:
            return ok()
        raise LifecycleError(
            "verified → in-progress is rework: requires an explicit "
            "rework_decision (never an auto-regress, §11.1)"
        )

    # --- done→cleaned-up (close-archive) and abandon (pre-done) ---
    if edge.guard == "close-archive":
        return ok()
    if edge.guard == "pre-done":
        # find_edge already proved from_state is pre-done for the abandon edge.
        return ok()

    raise LifecycleError(f"unhandled guard {edge.guard!r}")  # defensive


# Introspection map (firer/guard/record/terminal) keyed by (from,to) for the
# cert leg + downstream consumers. Abandon keyed under ("<pre-done>","cleaned-up").
EDGE_MODEL: Mapping[tuple[str, str], Edge] = MappingProxyType(
    {(e.from_state, e.to_state): e for e in R6_EDGES}
)
