"""WL2 canonical denial/degrade envelope (spec §9, CP7).

THE single canonical envelope for every refusal / denial / degrade point
(DOC1 §13 / Covenant C6 "no silent failure"). §11.4 **reuses** this shape; it
does not redefine it. Lifecycle guards (work-readiness §11.2, the acceptance
conjunction §11.4) build their typed denials *through this module* — so the
reuse is genuine-by-construction, never a parallel redefinition (BC2.4 hard
part).

Parley-agnostic at base (Hard Rule #1): pure library, no parley import / shell.

Envelope (§9.1):
    { id, type=denial, denied_subject, denial_class, from_state, reason_ref,
      raised_by, handler, resolution, created_at }

Two normative invariants enforced here (§9.3):
  * A denial is NOT a lifecycle failure-exit — the ``denied_subject`` **stays in
    its ``from_state``**. The envelope therefore carries NO ``to_state`` /
    target-state field; one present is rejected (a denial that "transitions" its
    subject is malformed — KA-19 stays-put).
  * ``raised_by`` (detector) is **distinct from** ``handler`` (accountable
    resolver); ``raised_by == handler`` is rejected (KA-19 raised_by≠handler).
"""
from __future__ import annotations

from types import MappingProxyType
from typing import Mapping


class DenialError(ValueError):
    """Raised when a denial envelope is malformed or a derivation is ambiguous."""


# §9.1 — the six distinct denial classes (not aliases).
DENIAL_CLASSES: frozenset[str] = frozenset(
    {
        "guard-miss",         # a lifecycle-guard miss (e.g. work-readiness, §11.2)
        "authority-denied",   # an override-authority / precedence refusal
        "gate-refused",       # an acceptance-conjunction refusal (verified→done, §11.4)
        "coverage-gap",       # the coverage gate (§4, UNDERCOVERED ≠ ∅)
        "store-unavailable",  # the read path could not reach the store
        "degrade",            # a degrade detector (stale / absent read) — loud
    }
)

# §9.1 — resolution lifecycle: open until exactly one terminal fires
# (forward-only). ``resolution`` is the denial kind's lifecycle field (there is
# no separate ``status``).
RESOLUTIONS: frozenset[str] = frozenset({"open", "resolve", "reroute", "cancel"})
_TERMINAL_RESOLUTIONS: frozenset[str] = frozenset({"resolve", "reroute", "cancel"})

# §9.2 — per-class ``raised_by`` (detector) / ``handler`` (accountable resolver)
# derivation. The labels are role-KINDS, not concrete role-ids; a caller with a
# context-specific accountable resolver passes ``handler=`` to override the
# default label (e.g. the exact role that must satisfy an unmet readiness
# criterion). ``raised_by`` is always the framework-side detector for the class.
_RAISED_BY_HANDLER: Mapping[str, dict[str, str]] = MappingProxyType(
    {
        "guard-miss": {
            "raised_by": "framework-lifecycle-guard",
            "handler": "readiness-criterion-owner",
        },
        "authority-denied": {
            "raised_by": "override-authority-precedence-check",
            "handler": "override-authority",
        },
        "gate-refused": {
            "raised_by": "acceptance-gate-conjunction",
            "handler": "unmet-condition-owner",
        },
        "coverage-gap": {
            "raised_by": "coverage-gate",
            "handler": "build-plan-owner",
        },
        "store-unavailable": {
            "raised_by": "read-path",
            "handler": "operator-environment",
        },
        "degrade": {
            "raised_by": "degrade-detector",
            "handler": "operator",
        },
    }
)

_REQUIRED_FIELDS = (
    "id", "type", "denied_subject", "denial_class", "from_state",
    "reason_ref", "raised_by", "handler", "resolution", "created_at",
)

# A denial NEVER carries a target/destination state — the subject stays put
# (§9.3). Any of these keys present is a malformed "transitioning" denial.
_FORBIDDEN_TRANSITION_KEYS = ("to_state", "target_state", "transitions_to", "next_state")


def derive_raised_by_handler(
    denial_class: str, handler: str | None = None
) -> tuple[str, str]:
    """Derive ``(raised_by, handler)`` for a denial class (§9.2).

    ``raised_by`` is the framework-side detector for the class. ``handler`` is
    the per-class default accountable-resolver label unless an explicit
    context-specific ``handler`` is supplied (e.g. the concrete role that must
    satisfy an unmet readiness criterion). Enforces the §9.3 invariant
    ``raised_by != handler``.
    """
    if denial_class not in _RAISED_BY_HANDLER:
        raise DenialError(
            f"unknown denial_class {denial_class!r}; "
            f"must be one of {sorted(DENIAL_CLASSES)}"
        )
    derived = _RAISED_BY_HANDLER[denial_class]
    raised_by = derived["raised_by"]
    resolved_handler = handler if handler else derived["handler"]
    if raised_by == resolved_handler:
        raise DenialError(
            f"raised_by ({raised_by!r}) must differ from handler "
            f"({resolved_handler!r}) — a detector cannot be its own "
            f"accountable resolver (§9.3)"
        )
    return raised_by, resolved_handler


def build_denial(
    *,
    id: str,
    denied_subject: str,
    denial_class: str,
    from_state: str,
    reason_ref: str,
    created_at: str,
    handler: str | None = None,
    resolution: str = "open",
) -> dict:
    """Build a canonical denial envelope (§9.1) with derived raised_by/handler.

    The envelope is born ``resolution="open"`` (forward-only; §9.1). It records
    the ``from_state`` the ``denied_subject`` STAYS in — it never carries a
    target state (§9.3 stays-put). Callers that need a context-specific
    accountable resolver pass ``handler=``.
    """
    if denial_class not in DENIAL_CLASSES:
        raise DenialError(
            f"unknown denial_class {denial_class!r}; "
            f"must be one of {sorted(DENIAL_CLASSES)}"
        )
    if resolution not in RESOLUTIONS:
        raise DenialError(
            f"resolution {resolution!r} must be one of {sorted(RESOLUTIONS)}"
        )
    raised_by, resolved_handler = derive_raised_by_handler(denial_class, handler)
    return {
        "id": id,
        "type": "denial",
        "denied_subject": denied_subject,
        "denial_class": denial_class,
        "from_state": from_state,
        "reason_ref": reason_ref,
        "raised_by": raised_by,
        "handler": resolved_handler,
        "resolution": resolution,
        "created_at": created_at,
    }


def resolve_denial(fm: dict, resolution: str) -> dict:
    """Advance a denial's ``resolution`` forward-only (open → one terminal).

    A denial is ``open`` until exactly one of resolve / reroute / cancel fires
    (§9.1). Re-resolving an already-terminal denial is rejected (forward-only).
    Returns a new envelope dict; does not mutate the input.
    """
    if resolution not in _TERMINAL_RESOLUTIONS:
        raise DenialError(
            f"resolution must be one of {sorted(_TERMINAL_RESOLUTIONS)} to close "
            f"a denial, got {resolution!r}"
        )
    current = fm.get("resolution")
    if current != "open":
        raise DenialError(
            f"denial {fm.get('id')!r} already resolved ({current!r}); "
            f"resolution is forward-only (§9.1)"
        )
    updated = dict(fm)
    updated["resolution"] = resolution
    return updated


def validate_denial(fm: dict) -> None:
    """Validate a denial envelope against the §9.1 schema + §9.3 invariants.

    Raises ``validators.ValidationError`` (imported lazily to keep this module
    free of an import cycle) collecting every problem.
    """
    import validators  # local import: validators imports nothing from denial

    errors: list[str] = []

    for field in _REQUIRED_FIELDS:
        if field not in fm:
            errors.append(f"missing required field: {field}")
        elif fm[field] in (None, ""):
            errors.append(f"required field is empty: {field}")

    type_val = fm.get("type")
    if type_val is not None and type_val != "denial":
        errors.append(f"type must be 'denial', got: {type_val!r}")

    denial_class = fm.get("denial_class")
    if denial_class is not None and denial_class not in DENIAL_CLASSES:
        errors.append(
            f"denial_class must be one of {sorted(DENIAL_CLASSES)}, got: {denial_class!r}"
        )

    resolution = fm.get("resolution")
    if resolution is not None and resolution not in RESOLUTIONS:
        errors.append(
            f"resolution must be one of {sorted(RESOLUTIONS)}, got: {resolution!r}"
        )

    # §9.3 raised_by ≠ handler (a detector cannot be its own resolver).
    raised_by = fm.get("raised_by")
    handler = fm.get("handler")
    if raised_by is not None and handler is not None and raised_by == handler:
        errors.append(
            "raised_by must differ from handler — a denial's detector cannot be "
            "its own accountable resolver (§9.3)"
        )

    # §9.3 stays-put: a denial NEVER transitions its subject. A target-state
    # key present means it was modelled as a transition — malformed.
    for key in _FORBIDDEN_TRANSITION_KEYS:
        if key in fm:
            errors.append(
                f"denial must not carry a target-state field ({key!r}); a denial "
                f"leaves its subject in from_state (§9.3 stays-put)"
            )

    # A denial does not carry owner_user (it is a framework-fired record keyed
    # to its denied_subject, like the block-signal transient).
    if "owner_user" in fm:
        errors.append("denial does not carry owner_user (framework record)")

    if errors:
        raise validators.ValidationError(errors)
