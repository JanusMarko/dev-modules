"""WL2 continuity mechanics (spec §11.6 / §10.2; BC2.6).

The three continuity records — **resume-ledger** (in-flight, for this worker's
next incarnation), **handoff** (settled post-state, for the next worker),
**conversation** (durable chat snapshot) — plus the **canonical-pointer** (the
one source-of-truth head) are kinds with writers (BC1). BC2.6 is the *mechanics*
that bind them (the continuity *detector* proper is BC4.1):

  (1) **durable-at-creation (C3)** — a record is real only once *written* at the
      moment it is created (an unrecorded decision did not happen). The writers
      land the file before returning; ``require_durable`` is the guard.
  (2) **fires off the observable moment, not memory (P7)** — the moments a
      continuity record is needed (a worker ending / compacting, an arc closing,
      a task finishing) are observable *events* (DOC1 §2, the event-spine). WL2
      prompts or requires the record *at that moment*, at whatever §6.2/§10 rung
      the environment supports — never deferred, never left only in live context.

The **continuity-at-the-moment** negative-space detector (§10.2) is the
silent-failure backstop: an arc-close event with **no** continuity record written
in its window must be flagged (injected-reminder), never silently passed (C6-c).
This module supplies the detector *mechanics* (``uncovered_arc_closes``); BC4
wires it into the on-event run loop.

Parley-agnostic at base (Hard Rule #1): pure library, no parley import / shell.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence


class ContinuityError(ValueError):
    """Raised when a durable-at-creation binding is violated."""


# §11.6 — the arc-close observable moments (P7) and the continuity record kinds.
ARC_CLOSE_EVENT_KINDS: frozenset[str] = frozenset(
    {"worker-end", "compact", "task-finish", "arc-close"}
)
CONTINUITY_RECORD_KINDS: frozenset[str] = frozenset(
    {"resume-ledger", "handoff", "conversation"}
)


@dataclass(frozen=True)
class NegativeSpaceDetector:
    """§10.1 detector schema. Read-only + bounded; surfaces, never blocks."""
    gate_id: str
    silent_failure_tell: str
    check_id: str
    surface: str   # warn | injected-reminder
    run_on: str    # on-read | on-stop | on-event


# §10.2 — the continuity-at-the-moment realization (mechanics side; BC4 wires it).
CONTINUITY_AT_THE_MOMENT_DETECTOR = NegativeSpaceDetector(
    gate_id="continuity-at-the-moment",
    silent_failure_tell=(
        "an arc-close event (worker-end / compact / task-finish) with no "
        "continuity record written in its window"
    ),
    check_id="uncovered_arc_closes",
    surface="injected-reminder",
    run_on="on-event",
)


def require_durable(record_path: str | Path) -> Path:
    """C3 durable-at-creation guard: a continuity record is real only once
    WRITTEN. Returns the path if the file exists on disk; raises otherwise.

    The writers (``write_resume_ledger`` / ``record_handoff`` /
    ``capture_conversation`` / ``write_canonical_pointer``) land the file before
    returning, so this passing is the post-condition that "the record happened."
    """
    path = Path(record_path)
    if not path.exists():
        raise ContinuityError(
            f"continuity record not durable: {path} was not written at creation "
            f"(an unrecorded record did not happen, C3)"
        )
    return path


def _covered_subjects(record: Mapping[str, object]) -> set[str]:
    """The subject identities a continuity record speaks for.

    A resume-ledger keys on ``worker``; a handoff/conversation may reference the
    closed subject via ``subject`` / ``covers`` / ``linked_subjects``. Empty when
    the record names nothing it covers.
    """
    out: set[str] = set()
    for key in ("worker", "subject"):
        val = record.get(key)
        if val:
            out.add(str(val))
    for key in ("covers", "linked_subjects"):
        val = record.get(key)
        if isinstance(val, (list, tuple)):
            out.update(str(v) for v in val)
        elif val:
            out.add(str(val))
    return out


def covers_arc_close(
    record: Mapping[str, object], event: Mapping[str, object]
) -> bool:
    """Whether a continuity ``record`` covers an arc-close ``event`` (P7 binding).

    TRUE iff the record is a continuity kind AND it names the event's
    ``subject`` among what it covers. This is the observable-moment binding: the
    record fired *for that closing moment's subject*.
    """
    if record.get("type") not in CONTINUITY_RECORD_KINDS:
        return False
    subject = event.get("subject")
    if subject is None:
        return False
    return str(subject) in _covered_subjects(record)


def uncovered_arc_closes(
    events: Sequence[Mapping[str, object]],
    records: Sequence[Mapping[str, object]],
) -> list[Mapping[str, object]]:
    """The arc-close events with NO covering continuity record (§10.2/§11.6).

    These are the silent-failure tells — the continuity-at-the-moment detector
    flags them (injected-reminder); they are NEVER silently passed (C6-c). Only
    events whose ``kind`` is an arc-close moment are considered; non-arc-close
    events are ignored. Bounded + read-only (it scans the supplied window only).
    """
    flagged: list[Mapping[str, object]] = []
    for event in events:
        if event.get("kind") not in ARC_CLOSE_EVENT_KINDS:
            continue
        if not any(covers_arc_close(r, event) for r in records):
            flagged.append(event)
    return flagged
