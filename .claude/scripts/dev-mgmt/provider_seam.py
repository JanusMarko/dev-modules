"""WL2 ↔ parley capability-provider seam (BC5, SETTLED half).

This is WL2's side of the provider/registry seam, built to the FIELD-LEVEL
SPEC v1 (``docs/design/wl-2-0/2026-06-24-wl2-FIELD-LEVEL-SPEC-v1.md``):

- **BC5.1** — the N1 agent-facing interface-conformance suite (spec §3.1 /
  App D.1, parley N1 @979f8e6): the closed-7 Op set, the request header, the
  idempotency rule, and ``unknown ⇒ unknown_verb`` typed-return. PLUS the
  provide-when-absent precedence (parley N2 §6.6): WL2 supplies a value only
  when the platform value is ABSENT, never overriding a present one.

All contract values transcribed in this module are TRANSCRIBED FROM THE SPEC
(App D), never re-defined here. Per Hard Rule #1 this module is
**parley-agnostic at base**: it imports / shells out to nothing parley — it
asserts WL2's own conformance to the transcribed contract.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Iterable, Mapping, Protocol, runtime_checkable

import lifecycle


# ---------------------------------------------------------------------------
# BC5.1 — the N1 closed-7 Op set (spec §3.1 / App D.1; parley §1.5.1, @979f8e6)
# ---------------------------------------------------------------------------

# The closed-7: the six data/coordination verbs "closed at six" + ``describe``
# as the 7th (introspection). Transcribed from App D.1 — NOT re-defined here.
READ_OPS: tuple[str, ...] = ("get", "list", "query", "subscribe")
WRITE_OPS: tuple[str, ...] = ("emit", "transition")
INTROSPECT_OPS: tuple[str, ...] = ("describe",)
CLOSED_7_OPS: frozenset[str] = frozenset((*READ_OPS, *WRITE_OPS, *INTROSPECT_OPS))


def idempotency_required(op: str) -> bool:
    """``idempotency_key`` is REQUIRED for the write verbs (``emit`` /
    ``transition``) and IGNORED for the reads (App D.1)."""
    return op in WRITE_OPS


class N1Status(str, Enum):
    """The typed-return statuses (spec §3.1 typed-return conformance + §9.4).

    A denial/refusal is a typed N1 return, never a silent failure or an
    out-of-band exception (C6 "no silent failure").
    """

    OK = "ok"
    UNKNOWN_VERB = "unknown_verb"
    INVALID_HEADER = "invalid_header"
    IDEMPOTENCY_KEY_REQUIRED = "idempotency_key_required"
    TRANSITION_GUARD_FAILED = "transition_guard_failed"


# The four required request-header fields (App D.1: ``{op, kind, request_id,
# idempotency_key}``).
HEADER_FIELDS: tuple[str, ...] = ("op", "kind", "request_id", "idempotency_key")


@dataclass(frozen=True)
class N1Request:
    """An N1 request header + payload (App D.1).

    ``idempotency_key`` is optional in the dataclass (reads ignore it) but is
    REQUIRED at dispatch for the write verbs — enforced by :class:`N1Dispatcher`,
    not by construction, so the missing-key case surfaces as a typed return
    rather than a constructor error.
    """

    op: str
    kind: str
    request_id: str
    idempotency_key: str | None = None
    payload: object = None


@dataclass(frozen=True)
class N1Return:
    """A typed N1 return (spec §3.1). ``status`` is the typed disposition; a
    non-OK status is the typed refusal — never a raised exception."""

    status: N1Status
    op: str | None = None
    kind: str | None = None
    request_id: str | None = None
    payload: object = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.status is N1Status.OK


@runtime_checkable
class CapabilityProvider(Protocol):
    """A capability provider (WL2 is one). The conformance suite (§3.1) probes
    a provider through this single entrypoint + its declared op set."""

    def supported_ops(self) -> frozenset[str]:
        """The op set the provider implements — must equal CLOSED_7_OPS."""
        ...

    def handle(self, request: N1Request) -> N1Return:
        """Route one N1 request to a typed return."""
        ...


# A per-op handler: takes the request, returns the OK payload-bearing return.
OpHandler = Callable[[N1Request], N1Return]


class N1Dispatcher:
    """Reference N1 front-door that enforces the §3.1 contract for any provider.

    A provider registers a handler per op; the dispatcher enforces — uniformly,
    so no provider re-implements the contract:

    1. **closed-7 only** — an op outside CLOSED_7_OPS ⇒ ``unknown_verb`` typed
       return (never raised; KA-8).
    2. **header well-formedness** — all four header fields present (``op`` /
       ``kind`` / ``request_id`` non-empty) ⇒ else ``invalid_header``.
    3. **idempotency** — ``emit`` / ``transition`` require a non-empty
       ``idempotency_key`` ⇒ else ``idempotency_key_required`` (KA-8); reads
       ignore the key.

    Only after all three hold does it dispatch to the registered handler.
    """

    def __init__(self, handlers: Mapping[str, OpHandler]):
        unknown = set(handlers) - CLOSED_7_OPS
        if unknown:
            raise ValueError(
                f"handlers register ops outside the closed-7: {sorted(unknown)}"
            )
        self._handlers: dict[str, OpHandler] = dict(handlers)

    def supported_ops(self) -> frozenset[str]:
        return frozenset(self._handlers)

    def handle(self, request: N1Request) -> N1Return:
        base = dict(
            op=request.op, kind=request.kind, request_id=request.request_id
        )
        # 1. closed-7 gate — unknown verb is a typed return, not an exception.
        if request.op not in CLOSED_7_OPS:
            return N1Return(
                status=N1Status.UNKNOWN_VERB,
                **base,
                error=f"op {request.op!r} is not one of the closed-7",
            )
        # 2. header well-formedness.
        if not (request.op and request.kind and request.request_id):
            return N1Return(
                status=N1Status.INVALID_HEADER,
                **base,
                error="op/kind/request_id are all required",
            )
        # 3. idempotency rule (writes only).
        if idempotency_required(request.op) and not request.idempotency_key:
            return N1Return(
                status=N1Status.IDEMPOTENCY_KEY_REQUIRED,
                **base,
                error=f"{request.op!r} requires a non-empty idempotency_key",
            )
        handler = self._handlers.get(request.op)
        if handler is None:
            # A closed-7 op with no registered handler is an incomplete
            # provider — surfaced as unknown_verb (the verb is known to the
            # contract but unimplemented by THIS provider).
            return N1Return(
                status=N1Status.UNKNOWN_VERB,
                **base,
                error=f"op {request.op!r} not implemented by this provider",
            )
        return handler(request)


def conformance_violations(provider: CapabilityProvider) -> list[str]:
    """The §3.1 interface-conformance suite, as a list of violations.

    A conformant provider yields ``[]``. Asserts (App D.1):
    - implements EXACTLY the closed-7 ops;
    - returns ``unknown_verb`` (typed, not raised) on an op outside the closed-7;
    - requires ``idempotency_key`` on ``emit`` / ``transition``;
    - ignores ``idempotency_key`` on the reads.
    """
    out: list[str] = []
    ops = provider.supported_ops()
    if ops != CLOSED_7_OPS:
        out.append(
            f"op set {sorted(ops)} != closed-7 {sorted(CLOSED_7_OPS)}"
        )
    # unknown verb ⇒ typed unknown_verb (never raised).
    try:
        r = provider.handle(
            N1Request(op="frobnicate", kind="task", request_id="r1")
        )
        if r.status is not N1Status.UNKNOWN_VERB:
            out.append(f"unknown op did not return unknown_verb (got {r.status})")
    except Exception as exc:  # noqa: BLE001 — conformance: must NOT raise
        out.append(f"unknown op raised instead of typed-return: {exc!r}")
    # writes require idempotency_key.
    for op in WRITE_OPS:
        r = provider.handle(N1Request(op=op, kind="task", request_id="r2"))
        if r.status is not N1Status.IDEMPOTENCY_KEY_REQUIRED:
            out.append(f"{op} without idempotency_key was not refused (got {r.status})")
    # reads ignore idempotency_key (presence must not change disposition).
    for op in READ_OPS:
        with_key = provider.handle(
            N1Request(op=op, kind="task", request_id="r3", idempotency_key="k")
        )
        without = provider.handle(N1Request(op=op, kind="task", request_id="r3"))
        if with_key.status is not without.status:
            out.append(f"{op} disposition changed with/without idempotency_key")
    return out


def assert_conformant(provider: CapabilityProvider) -> None:
    """Raise if ``provider`` fails the §3.1 conformance suite."""
    violations = conformance_violations(provider)
    if violations:
        raise AssertionError(
            "provider is not N1-conformant:\n  " + "\n  ".join(violations)
        )


# ---------------------------------------------------------------------------
# BC5.1 — provide-when-absent precedence (parley N2 §6.6; mirrors DOC2 §4 bucket-3)
# ---------------------------------------------------------------------------


class _Absent:
    """Singleton sentinel: the platform supplied NO value for this slot.

    Distinct from a present ``None``/falsy value — a present value (even falsy)
    is platform content and is authoritative. Only ABSENT yields to WL2's fill.
    """

    _instance: "_Absent | None" = None

    def __new__(cls) -> "_Absent":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return "ABSENT"

    def __bool__(self) -> bool:
        return False


ABSENT = _Absent()


def provide_when_absent(platform_value: object, wl2_value: object) -> object:
    """Platform-precedence merge (parley §6.6).

    The platform's value is authoritative and supersedes WL2's; WL2 supplies
    only when the platform value is :data:`ABSENT`. A PRESENT platform value —
    **including a falsy one such as ``None``, ``0``, ``""``** — is never
    overridden (the KA-9 invariant).
    """
    if platform_value is ABSENT:
        return wl2_value
    return platform_value


def merge_provided(
    platform: Mapping[str, object], wl2: Mapping[str, object]
) -> dict[str, object]:
    """Map form of :func:`provide_when_absent`: WL2 fills only the keys ABSENT
    from ``platform`` (i.e. not present). A present key — even with a falsy /
    ``None`` value — keeps the platform value (never overridden, KA-9)."""
    merged = dict(platform)
    for key, value in wl2.items():
        if key not in platform:
            merged[key] = value
    return merged


# ---------------------------------------------------------------------------
# BC5.2 — Kind-Registry registration wire (spec §7; parley N2 §6.1 @b932c6a +
# descriptor N1 §1.4.1/2 @979f8e6)
# ---------------------------------------------------------------------------


class SourceLayer(str, Enum):
    """Registration ``source_layer`` (§7.1). WL2 always registers its own kinds
    as ``framework_overlay`` (distinct from ``framework_owned``, the ledger
    *ownership mode* §1.1 — not conflated)."""

    PARLEY_BASE = "parley_base"
    FRAMEWORK_OVERLAY = "framework_overlay"


# WL2 registers its kinds at the overlay layer (§7.1).
WL2_SOURCE_LAYER = SourceLayer.FRAMEWORK_OVERLAY


class RegistrationState(str, Enum):
    """``kind_registration.registration_state`` (§7.1)."""

    DRAFT = "draft"
    ACTIVE = "active"
    RETIRED = "retired"
    WITHDRAWN = "withdrawn"


# The registry-state edges (§7.1 / §7.2). draft→active is the GATED edge.
REGISTRATION_EDGES: frozenset[tuple[RegistrationState, RegistrationState]] = frozenset(
    {
        (RegistrationState.DRAFT, RegistrationState.ACTIVE),
        (RegistrationState.DRAFT, RegistrationState.WITHDRAWN),
        (RegistrationState.ACTIVE, RegistrationState.RETIRED),
        (RegistrationState.ACTIVE, RegistrationState.WITHDRAWN),
    }
)


@dataclass(frozen=True)
class KindRegistration:
    """The §7.1 ``kind_registration`` payload (parley N2 §6.1 @b932c6a).

    The record body is N2-owned; ``descriptor_ref`` points at the separate N1
    ``KindDescriptor`` payload (§1.4.1/2 @979f8e6) — two distinct parley
    surfaces. ``completeness_checked_at`` is stamped by parley's gate on pass;
    WL2 never writes it itself (§7.3 composition).
    """

    kind: str
    descriptor_ref: str
    registration_state: RegistrationState
    registered_by: str
    source_layer: SourceLayer = WL2_SOURCE_LAYER
    supersedes: str | None = None
    completeness_checked_at: str | None = None


# ---------------------------------------------------------------------------
# BC5.2 — WL2 CP4 state-completeness predicate (§7.3, WL-owned)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StateCompleteness:
    """One state's CP4 declaration (§7.3): a non-terminal state declares (a) its
    normal exit, (b) its reachable failure/abort exit, and (c) its firer (or
    ``inferred_by``). A terminal state declares none of these."""

    state: str
    normal_exit: str | None = None
    failure_exit: str | None = None
    firer: str | None = None
    inferred_by: str | None = None
    terminal: bool = False


def cp4_violations(states: Iterable[StateCompleteness]) -> list[str]:
    """The CP4 state-completeness predicate as a violation list (§7.3).

    Machine-checkable over WL2's own kind declarations: every NON-terminal state
    must declare a normal exit, a reachable failure/abort exit, and a firer (or
    ``inferred_by``). A complete machine yields ``[]``. Fail-closed: a missing
    component is a violation, not a silent pass (C6).
    """
    out: list[str] = []
    seen = False
    for s in states:
        seen = True
        if s.terminal:
            continue
        if not s.normal_exit:
            out.append(f"{s.state}: missing normal exit")
        if not s.failure_exit:
            out.append(f"{s.state}: missing reachable failure/abort exit")
        if not (s.firer or s.inferred_by):
            out.append(f"{s.state}: missing firer/inferred_by")
    if not seen:
        out.append("no states declared")
    return out


def cp4_from_edges(
    *,
    states: Iterable[str],
    edges: Iterable[tuple[str, str]],
    firers: Mapping[tuple[str, str], str] | None = None,
    failure_targets: Iterable[str] = (),
) -> list[StateCompleteness]:
    """Derive per-state :class:`StateCompleteness` from a transition table so
    CP4 can run over a real WL2 kind's ``{states, transitions}`` declaration.

    A state is terminal iff it has no outgoing edge. For a non-terminal state,
    its normal exit is the first edge to a non-failure target, its failure exit
    the first edge to a ``failure_targets`` member (or, absent the hint, any
    additional out-edge). ``firers`` supplies the per-edge firer when known.
    """
    firers = dict(firers or {})
    failure = set(failure_targets)
    out_edges: dict[str, list[str]] = {s: [] for s in states}
    for src, dst in edges:
        out_edges.setdefault(src, []).append(dst)
    decls: list[StateCompleteness] = []
    for state, targets in out_edges.items():
        if not targets:
            decls.append(StateCompleteness(state=state, terminal=True))
            continue
        normal = next((t for t in targets if t not in failure), targets[0])
        fail = next((t for t in targets if t in failure), None)
        if fail is None and len(targets) > 1:
            fail = next(t for t in targets if t != normal)
        firer = firers.get((state, normal)) or (
            firers.get((state, fail)) if fail else None
        )
        decls.append(
            StateCompleteness(
                state=state,
                normal_exit=normal,
                failure_exit=fail,
                firer=firer,
            )
        )
    return decls


# ---------------------------------------------------------------------------
# BC5.2 — the HARD part: CP4 COMPOSES-WITH parley's completeness gate (§7.3)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ActivationGate:
    """The result of the draft→active composition gate (§7.3).

    ``allowed`` iff BOTH legs hold. ``cp4_pass`` is WL2's own predicate;
    ``completeness_pass`` is parley's ``completeness_checked_at`` stamp. The two
    are reported separately so neither leg is collapsed into the other — the
    composition is additive, never a short-circuit.
    """

    allowed: bool
    cp4_pass: bool
    completeness_pass: bool
    missing: tuple[str, ...]


def activation_gate(
    *, cp4_pass: bool, completeness_checked_at: str | None
) -> ActivationGate:
    """draft→active is permitted ONLY when **both** WL2's CP4 predicate passes
    AND parley stamped ``completeness_checked_at`` (§7.3, KA-18 / C6-a).

    **Composition, not duplication:** the two legs are evaluated independently
    and conjoined; neither overrides the other and **either failure blocks
    ``active``** (fail-closed). WL2 never short-circuits parley's gate (it does
    not treat its own CP4 pass as sufficient), and it never bypasses CP4 (a
    parley stamp alone is not sufficient).
    """
    cp4_ok = bool(cp4_pass)
    parley_ok = bool(completeness_checked_at)
    missing: list[str] = []
    if not cp4_ok:
        missing.append("cp4_state_completeness")
    if not parley_ok:
        missing.append("completeness_checked_at")
    return ActivationGate(
        allowed=cp4_ok and parley_ok,
        cp4_pass=cp4_ok,
        completeness_pass=parley_ok,
        missing=tuple(missing),
    )


def attempt_registration_transition(
    registration: KindRegistration,
    to_state: RegistrationState,
    *,
    cp4_pass: bool | None = None,
    completeness_checked_at: str | None = None,
) -> N1Return:
    """Transition a ``kind_registration`` (rides N1 ``transition``, §7.2).

    The ``draft → active`` edge is GATED by the §7.3 composition: it fires only
    when CP4 ∧ ``completeness_checked_at`` both hold. A miss surfaces as the
    N1 ``transition_guard_failed`` typed return (§7.2) — the record STAYS in
    ``draft`` (no fail-state slide, §9.3). A structurally-impossible edge is
    also a typed ``transition_guard_failed`` (never a silent move).
    """
    frm = registration.registration_state
    base = dict(op="transition", kind=registration.kind, request_id=registration.kind)
    edge = (frm, to_state)
    if edge not in REGISTRATION_EDGES:
        return N1Return(
            status=N1Status.TRANSITION_GUARD_FAILED,
            **base,
            error=f"no registration edge {frm.value} → {to_state.value}",
        )
    if edge == (RegistrationState.DRAFT, RegistrationState.ACTIVE):
        gate = activation_gate(
            cp4_pass=bool(cp4_pass),
            completeness_checked_at=completeness_checked_at,
        )
        if not gate.allowed:
            return N1Return(
                status=N1Status.TRANSITION_GUARD_FAILED,
                **base,
                error="draft→active blocked: missing " + ", ".join(gate.missing),
                payload={"gate": gate},
            )
    return N1Return(status=N1Status.OK, **base, payload={"to_state": to_state})


# ---------------------------------------------------------------------------
# BC5.3 — the 4 GATED consumed-shape bindings (spec §2.4 + App D.2; parley N3
# @25115f0)
# ---------------------------------------------------------------------------

# WL2's 7 consumed-shape NAMES are WL2's own abstraction; each binds to a
# concrete parley kind/field. Only FOUR are GATED (bound to field level now);
# the other three are FORWARD-BOUND / un-gated and FENCED per §0.1 — they bind
# at their owning cohort's LAND, NOT here.


class ConsumedShape(str, Enum):
    """WL2's 7 consumed-shape names (§2.4)."""

    # GATED — bound now (App D.2):
    ATTACHMENT_POINT = "attachment-point"
    CLOSURE_SIGNAL = "closure-signal"
    PLAN_REF = "plan-ref"
    GATE_RULE = "gate-rule"
    # FORWARD-BOUND / un-gated — FENCED (§0.1); NOT bound in Wave-1:
    VERDICT = "verdict"
    DECISION_REF = "decision-ref"
    BLOCK_GATE = "block-gate"


GATED_SHAPES: frozenset[ConsumedShape] = frozenset(
    {
        ConsumedShape.ATTACHMENT_POINT,
        ConsumedShape.CLOSURE_SIGNAL,
        ConsumedShape.PLAN_REF,
        ConsumedShape.GATE_RULE,
    }
)
FORWARD_BOUND_SHAPES: frozenset[ConsumedShape] = frozenset(
    {ConsumedShape.VERDICT, ConsumedShape.DECISION_REF, ConsumedShape.BLOCK_GATE}
)


class ConsumedShapeNotGated(ValueError):
    """Raised when a binding is requested for an un-gated (fenced) shape — the
    KA-6 invariant: a consumed-shape binding must NEVER fire against an ungated
    target."""


@dataclass(frozen=True)
class ConsumedShapeBinding:
    """One GATED WL2-shape → parley-kind binding (App D.2). ``fields`` carries
    the field-level shape transcribed from the spec — never re-defined."""

    shape: ConsumedShape
    parley_kind: str
    parley_section: str
    fields: Mapping[str, object]


# --- closure-signal: the layer-map disposition ↦ outcome (§2.4 / §11.3) -------

# parley ``outcome`` enum (App D.2): the R2 label on the transition INTO
# cleaned-up.
PARLEY_OUTCOMES: frozenset[str] = frozenset({"done", "abandoned", "superseded"})

# WL2's own closure-record ``disposition`` vocab (§11.3).
WL2_DISPOSITIONS: frozenset[str] = frozenset({"completed", "superseded", "abandoned"})

# The layer-map (§2.4 / §11.3): one concept, two layers. ``completed ↦ done`` is
# the ONLY value that differs; ``superseded`` / ``abandoned`` are identical.
_DISPOSITION_TO_OUTCOME: dict[str, str] = {
    "completed": "done",
    "superseded": "superseded",
    "abandoned": "abandoned",
}


def disposition_to_outcome(disposition: str) -> str:
    """Map a WL2 closure-record ``disposition`` to its parley ``outcome``
    (§2.4 / §11.3 layer-map). ``completed ↦ done``; the others are identity.
    An unknown disposition is refused (no silent mismap, C6 — KA-7)."""
    try:
        return _DISPOSITION_TO_OUTCOME[disposition]
    except KeyError as exc:
        raise ValueError(
            f"unknown disposition {disposition!r}; expected one of "
            f"{sorted(WL2_DISPOSITIONS)}"
        ) from exc


# --- the 4 GATED bindings (field-level, transcribed from App D.2) -------------

_GATED_BINDINGS: dict[ConsumedShape, ConsumedShapeBinding] = {
    ConsumedShape.ATTACHMENT_POINT: ConsumedShapeBinding(
        shape=ConsumedShape.ATTACHMENT_POINT,
        parley_kind="attachment",
        parley_section="§5.1.3",
        fields={
            # the R2 binding signal; binds the OPAQUE seam (C2 — parley reads
            # the seam, never the task body).
            "lifecycle": ("open", "bound", "reaping", "closed"),
            "extra_states": ("reap-blocked",),
            # work_item back-pointer: set on bind, cleared on closed.
            "back_pointer": "work_item.current_attachment_ref",
            "opaque_seam": True,
        },
    ),
    ConsumedShape.CLOSURE_SIGNAL: ConsumedShapeBinding(
        shape=ConsumedShape.CLOSURE_SIGNAL,
        parley_kind="work_item",
        parley_section="§5.4.1",
        fields={
            # bound to lifecycle.R6_STATES so the work-state cannot drift from
            # R6 on this parley-bound edge (D.3 alignment).
            "states": lifecycle.R6_STATES,
            "sole_terminal": lifecycle.TERMINAL_STATE,
            # R2 label carried on the transition INTO cleaned-up (labels, not
            # states; ADR-WS-17).
            "outcome_enum": tuple(sorted(PARLEY_OUTCOMES)),
            "outcome_carried_on": "transition into cleaned-up",
            # layer-map: WL2 disposition ↦ parley outcome.
            "disposition_to_outcome": dict(_DISPOSITION_TO_OUTCOME),
        },
    ),
    ConsumedShape.PLAN_REF: ConsumedShapeBinding(
        shape=ConsumedShape.PLAN_REF,
        parley_kind="work_order",
        parley_section="§5.1.2",
        fields={
            "ratification_states": (
                "drafted", "ratified", "fulfilled", "superseded",
                "declined", "cancelled",
            ),
            "mandated_by_edge": "mandated_by",
            "authorization_metadata": ("scope_ref",),
        },
    ),
    ConsumedShape.GATE_RULE: ConsumedShapeBinding(
        shape=ConsumedShape.GATE_RULE,
        parley_kind="work_item",
        parley_section="§5.1.1",
        fields={
            # the R8 acceptance gate-rule is a framework-fired transition GUARD,
            # NOT a human-approval gate_required surface.
            "transition": "accept",
            "guard": "acceptance_verdict_pass",
            "complement_transition": "rework",
            "complement_guard": "acceptance_verdict_fail_or_insufficient",
            "firer": "framework",
            "inferred_by": "reconciler",
        },
    ),
}


def binding_for(shape: ConsumedShape) -> ConsumedShapeBinding:
    """Return the GATED binding for ``shape``.

    Refuses a FORWARD-BOUND / un-gated shape with :class:`ConsumedShapeNotGated`
    — the KA-6 invariant: a consumed-shape binding must never fire against the
    wrong / ungated target. The three fenced shapes (``verdict`` /
    ``decision-ref`` / ``block-gate``) bind at their owning cohort's LAND.
    """
    if shape in FORWARD_BOUND_SHAPES:
        raise ConsumedShapeNotGated(
            f"{shape.value} is forward-bound / un-gated (FENCED §0.1); "
            "it binds at its owning cohort's LAND, not in Wave-1"
        )
    binding = _GATED_BINDINGS.get(shape)
    if binding is None:  # pragma: no cover - exhaustive over the enum
        raise ConsumedShapeNotGated(f"no gated binding for {shape!r}")
    return binding
