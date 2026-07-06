"""WL2 block-signal lifecycle + derived attention-state (spec §11.5; BC2.5).

The `block-signal` kind (schema §2.3, validator in ``validators.py``) carries
``{blocked_subject, waits_on, deadline, class}`` with **exactly two classes** and
this complete CP4 lifecycle (§11.5):

  | class · state    | normal exit            | failure / timeout exit          |
  |------------------|------------------------|---------------------------------|
  | HALT · raised    | unblock (human) → resolved | none — waits INDEFINITELY     |
  | wait_for · raised| release (arrival) → resolved | expired on max-TTL (on-read)|
  | wait_for · expired | re-release if it still arrives | — (warn rung standalone)  |

Indefinite waiting is **forbidden for `wait_for`** (bounded TTL required); only
`HALT` may wait indefinitely. The **derived attention-state** (DOC1 §6.3) makes
"blocked vs dead" legible; precedence is deterministic — awaiting wins over
working (a blocked-but-claimed task is never "working").

**HALT-stuck trigger = JUDGMENT UNIT (RE=yes / OQ-2).** "Is this agent genuinely
stuck (→ HALT) vs merely awaiting a named dependency (→ wait_for)?" is a judgment
component. This module supplies the CODE to the spec contract — mirroring the
BC1.4 collision-resolver pattern: a deterministic mechanism with the judgment
delegated to an injected :class:`StuckJudge` protocol (no hardcoded judgment).
The TRUSTED behavior ships only behind a FRESH-INDEPENDENT-supplied,
@cto-ratified, cold-graded eval corpus (evals-first, C4/§5) — this code does not
self-certify the judgment.

Parley-agnostic at base (Hard Rule #1): pure library, no parley import / shell.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping, Protocol, Sequence, runtime_checkable

import validators


class BlockSignalError(ValueError):
    """Raised on an illegal block-signal transition (wrong class/state)."""


HALT = "HALT"
WAIT_FOR = "wait_for"
BLOCK_SIGNAL_CLASSES: frozenset[str] = frozenset({HALT, WAIT_FOR})


# ---------------------------------------------------------------------------
# TTL / deadline mechanics (the wait_for bound)
# ---------------------------------------------------------------------------

_DURATION_RE = re.compile(r"^\s*(\d+)\s*([smhd])\s*$")
_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400}
_ISO_FMT = "%Y-%m-%dT%H:%M:%SZ"


def parse_ttl_seconds(ttl: object) -> int | None:
    """Parse a simple ``<int><s|m|h|d>`` TTL to seconds. None if unparseable."""
    if not isinstance(ttl, str):
        return None
    m = _DURATION_RE.match(ttl)
    if not m:
        return None
    return int(m.group(1)) * _UNIT_SECONDS[m.group(2)]


def _parse_iso(ts: object) -> datetime | None:
    if not isinstance(ts, str):
        return None
    try:
        return datetime.strptime(ts, _ISO_FMT).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def effective_deadline(signal: Mapping[str, object]) -> datetime | None:
    """The absolute moment a wait_for expires.

    An explicit ``deadline`` wins; otherwise it is ``created_at + ttl``. Returns
    None when neither is resolvable (the caller treats "no resolvable deadline"
    as not-yet-expired — a malformed wait_for is caught by the validator, not
    silently expired here).
    """
    explicit = _parse_iso(signal.get("deadline"))
    if explicit is not None:
        return explicit
    created = _parse_iso(signal.get("created_at"))
    ttl_secs = parse_ttl_seconds(signal.get("ttl"))
    if created is not None and ttl_secs is not None:
        from datetime import timedelta
        return created + timedelta(seconds=ttl_secs)
    return None


# ---------------------------------------------------------------------------
# Lifecycle transitions (forward-only; class-gated per the §11.5 table)
# ---------------------------------------------------------------------------


def _revalidate(updated: dict) -> dict:
    validators.validate_block_signal(updated)
    return updated


def unblock(signal: Mapping[str, object]) -> dict:
    """HALT · raised → resolved (a HUMAN clears). HALT only (§11.5)."""
    if signal.get("class") != HALT:
        raise BlockSignalError("unblock applies only to a HALT block-signal")
    if signal.get("status") != "raised":
        raise BlockSignalError(
            f"unblock requires status=raised, got {signal.get('status')!r}"
        )
    updated = dict(signal)
    updated["status"] = "resolved"
    return _revalidate(updated)


def release(signal: Mapping[str, object]) -> dict:
    """wait_for → resolved on the dependency's arrival.

    Fires from ``raised`` (normal exit) OR from ``expired`` (re-release if the
    dependency still arrives, §11.5). wait_for only — a HALT needs a human
    ``unblock``.
    """
    if signal.get("class") != WAIT_FOR:
        raise BlockSignalError("release applies only to a wait_for block-signal")
    if signal.get("status") not in ("raised", "expired"):
        raise BlockSignalError(
            f"release requires status in (raised, expired), got "
            f"{signal.get('status')!r}"
        )
    updated = dict(signal)
    updated["status"] = "resolved"
    return _revalidate(updated)


def infer_expired(signal: Mapping[str, object], *, now: datetime | None = None) -> dict:
    """On-read max-TTL inference: wait_for · raised → expired once past deadline.

    WL2 infers ``expired`` at read time (§11.5) — it is not a stored flip a
    firer writes. A HALT never expires (indefinite by declaration). A wait_for
    not yet past its deadline, or with no resolvable deadline, is returned
    unchanged. Idempotent on an already-expired/resolved signal.
    """
    if signal.get("class") == HALT:
        return dict(signal)  # HALT may wait indefinitely — never expires
    if signal.get("status") != "raised":
        return dict(signal)
    deadline = effective_deadline(signal)
    if deadline is None:
        return dict(signal)
    moment = now or datetime.now(timezone.utc)
    if moment >= deadline:
        updated = dict(signal)
        updated["status"] = "expired"
        return _revalidate(updated)
    return dict(signal)


def is_expired(signal: Mapping[str, object], *, now: datetime | None = None) -> bool:
    """Whether a wait_for is past its deadline (on-read predicate, §10.2)."""
    if signal.get("class") == HALT:
        return False
    deadline = effective_deadline(signal)
    if deadline is None:
        return False
    return (now or datetime.now(timezone.utc)) >= deadline


# ---------------------------------------------------------------------------
# Derived attention-state (DOC1 §6.3) — "blocked vs dead" legibility
# ---------------------------------------------------------------------------

WORKING = "working"
AWAITING = "awaiting-a-named-gate"
IDLE = "idle-no-active-task"
ATTENTION_STATES: tuple[str, ...] = (WORKING, AWAITING, IDLE)

# A worker "holds" a task while it is claimed mid-flight (§11.1).
_CLAIMED_TASK_STATES = frozenset({"picked-up", "in-progress", "verified"})


def _is_active_block(signal: Mapping[str, object]) -> bool:
    """An open (unresolved) block-signal still parks the role. raised + expired
    both still await the named gate; only ``resolved`` clears it."""
    return signal.get("status") != "resolved"


def attention_state(
    *,
    task_statuses: Sequence[str],
    block_signals: Sequence[Mapping[str, object]] = (),
) -> str:
    """Derive the per-active-role attention-state (§11.5; DOC1 §6.3).

    Deterministic precedence — **awaiting wins over working**: a role carrying an
    active (HALT or wait_for) block-signal reads ``awaiting-a-named-gate`` even
    while it holds a claimed task (a blocked-but-claimed task is NEVER
    "working"). Else a held claimed task reads ``working``; else
    ``idle-no-active-task``. A derived predicate — never a stored field.
    """
    if any(_is_active_block(bs) for bs in block_signals):
        return AWAITING
    if any(s in _CLAIMED_TASK_STATES for s in task_statuses):
        return WORKING
    return IDLE


# ---------------------------------------------------------------------------
# HALT-stuck trigger — THE JUDGMENT UNIT (code only; eval gates trusted-ship)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BlockContext:
    """The situation a block decision is made over.

    ``waits_on`` + ``bounded_arrival`` are the STRUCTURAL signals (a named
    dependency with a bounded arrival is a wait_for by construction). The
    remaining flags are the stuck-ness *tells* the :class:`StuckJudge` reasons
    over — they are the judgment surface, not a deterministic verdict.
    """

    blocked_subject: str
    waits_on: str | None = None
    bounded_arrival: bool = False
    recurring_failure: bool = False
    unresolvable_gate: bool = False
    unfixable_environment: bool = False
    ambiguous_scope: bool = False


@runtime_checkable
class StuckJudge(Protocol):
    """The injected judgment the HALT-stuck trigger consumes (the eval surface).

    Abstraction-first (BC1.4 ``AuthorityModel`` precedent): the trigger depends
    ONLY on this protocol. The TRUSTED implementation is supplied behind a
    fresh-independent, @cto-ratified, cold-graded eval corpus — this module ships
    the CODE contract, not the certified judgment.
    """

    def is_genuinely_stuck(self, ctx: BlockContext) -> bool:
        """True iff the agent is genuinely stuck (→ HALT, indefinite) rather than
        merely awaiting a dependency (→ wait_for, bounded)."""
        ...


@dataclass(frozen=True)
class DefaultStuckJudge:
    """The CERTIFIED HALT-stuck judge (graded GREEN vs the frozen behavioral
    corpus 2026-06-27-02; replaces the prior non-certified 4-tell floor that
    RED'd 14/16 on DA-stuck-not-bounded by defaulting genuinely-stuck states to
    wait_for — the dangerous direction).

    The discriminant is **named ≠ reachable**, applied at the point the judge is
    consulted (a reachable, bounded named dependency is already short-circuited
    to ``wait_for`` by :func:`classify_block` before the judge runs). So whenever
    the judge IS asked, exactly one of two genuinely-stuck shapes holds — both
    → HALT (no ttl; only a human ``unblock`` clears):

      1. **silent stall / no-dependency stuck** (``not waits_on``) — a surfaced
         block that names NO dependency. There is nothing to wait *for*; a
         claimed task gone silent, an unfixable toolchain with no fulfilment
         event, a stuck item whose tells were stripped — all genuinely stuck.
      2. **named-but-unreachable dependency** (``waits_on`` set but
         ``not bounded_arrival``) — the named fulfilment event has no reachable
         path (owner departed / no successor / not scheduled). A "dependency"
         that can never arrive is NOT a wait_for; attaching a TTL to it would let
         the item silently drop on expiry (the DA-stuck-not-bounded harm).

    The explicit tells (recurring_failure / unresolvable_gate /
    unfixable_environment / ambiguous_scope) corroborate shape (1) but are not
    required — reasoning is over reachability of the world-state, not keyword
    tells (so a stripped-tell or despair-phrasing perturbation does not fool it).
    """

    def is_genuinely_stuck(self, ctx: BlockContext) -> bool:
        if not ctx.waits_on:
            return True  # nothing to wait for → genuinely stuck (silent stall)
        if not ctx.bounded_arrival:
            return True  # named but unreachable → can never arrive → HALT
        return False     # a bounded, reachable named dependency → wait_for


def classify_block(ctx: BlockContext, judge: StuckJudge) -> str:
    """Classify a block as ``HALT`` or ``wait_for`` (the §11.5 distinction).

    Deterministic structural shortcut first: a **named dependency with a bounded
    arrival** is a ``wait_for`` by construction (bounded TTL) — no judgment, no
    HALT. Otherwise the JUDGMENT UNIT decides: genuinely-stuck → ``HALT``
    (indefinite), else still-awaiting → ``wait_for``. The judgment lives entirely
    in ``judge.is_genuinely_stuck`` (the eval-gated surface).
    """
    if ctx.waits_on and ctx.bounded_arrival:
        return WAIT_FOR
    return HALT if judge.is_genuinely_stuck(ctx) else WAIT_FOR
