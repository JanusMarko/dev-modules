"""WL2 acceptance-class tags + the C7 SoD floor (spec §12; BC3.6).

The ``verified → done`` acceptance carries zero-or-more **acceptance-class
tags** (SHIP / EXTERNAL / IRREVERSIBLE). The **C7 immovable SoD floor keys off
these tags**: on a tagged acceptance the SoD conjunct is immovable — the
override-authority's opt-out (P9/CP3) is rejected; review + SoD both bind.

Kill-axis this module targets:
  * **KA-24** — a SoD opt-out accepted on a SHIP/EXTERNAL/IRREVERSIBLE-tagged
    acceptance, **or** ``assigner == builder`` validating → die.
    :func:`effective_sod_holds` rejects the opt-out when tagged;
    :func:`acceptance_class_violations` rejects ``assigned_by == builder``.

Assigner role (§12.2, Kris-ratified 2026-06-24 msg-a3e21ed038b9): the **work's
lead** assigns the tags no later than the acceptance act; the assignment is
immutable once the task is ``done``. **Guardrail:** the lead who assigns the tag
MUST NOT also be the builder of that same item (the floor-tightening authority
cannot accept around its own work).

Parley-agnostic at base (Hard Rule #1): pure library, no parley import / shell.
"""
from __future__ import annotations

from typing import Mapping, Sequence

# §12.1 — the closed acceptance-class vocabulary.
SHIP = "SHIP"
EXTERNAL = "EXTERNAL"
IRREVERSIBLE = "IRREVERSIBLE"
ACCEPTANCE_CLASSES: frozenset[str] = frozenset({SHIP, EXTERNAL, IRREVERSIBLE})


def sod_is_immovable(acceptance_classes: Sequence[str] | None) -> bool:
    """§12.1 — the C7 SoD floor is immovable IFF ``acceptance_classes`` is
    non-empty. Empty (or absent) ⇒ no immovable floor (SoD opt-out remains
    permitted per P9/CP3).
    """
    return bool(acceptance_classes)


def effective_sod_holds(
    *,
    sod_signed: bool,
    sod_opt_out: bool,
    acceptance_classes: Sequence[str] | None,
) -> bool:
    """Whether the SoD conjunct holds for the ``verified → done`` gate (§12.1).

    * **Tagged (immovable, C7):** the opt-out is **rejected** — SoD must
      genuinely be signed. ``sod_opt_out`` is ignored; the floor cannot be
      lowered (KA-24).
    * **Untagged:** the override-authority's opt-out is permitted (P9/CP3) — SoD
      holds if signed **or** opted out.
    """
    if sod_is_immovable(acceptance_classes):
        return sod_signed
    return sod_signed or sod_opt_out


def acceptance_class_violations(
    *,
    acceptance_classes: Sequence[str] | None,
    assigned_by: str | None,
    assigned_at: str | None,
    builder_role: str | None,
) -> list[str]:
    """Validate the §12.1 tag schema + the §12.2 assigner guardrail.

    Empty list ⇒ valid. Checks (fail closed):
      * every class ∈ {SHIP, EXTERNAL, IRREVERSIBLE}.
      * if ``acceptance_classes`` non-empty: ``assigned_by`` + ``assigned_at``
        required (present + non-empty), and **``assigned_by`` ≠ ``builder_role``**
        (KA-24 / §12.2 — the assigner must not be the builder).
    """
    v: list[str] = []
    classes = list(acceptance_classes or [])
    unknown = [c for c in classes if c not in ACCEPTANCE_CLASSES]
    if unknown:
        v.append(f"unknown acceptance class(es) {unknown}; must be ⊆ {sorted(ACCEPTANCE_CLASSES)}")
    if classes:
        if not assigned_by:
            v.append("assigned_by required when acceptance_classes is non-empty")
        if not assigned_at:
            v.append("assigned_at required when acceptance_classes is non-empty")
        if assigned_by and builder_role is not None and assigned_by == builder_role:
            v.append(
                f"assigned_by == builder ({assigned_by!r}); the lead who assigns "
                f"the tag must not be the builder (KA-24 / §12.2 SoD floor)"
            )
    return v


def tag_immutability_violation(
    *,
    task_status: str,
    current_classes: Sequence[str] | None,
    proposed_classes: Sequence[str] | None,
) -> str | None:
    """§12.1 — tags are **immutable once the task is ``done``**.

    Returns a violation string if a ``done`` task's ``acceptance_classes`` would
    change (an accepted task's class cannot be retroactively weakened or
    strengthened); ``None`` otherwise. Ordering-insensitive (set comparison).
    """
    if task_status != "done":
        return None
    if set(current_classes or []) != set(proposed_classes or []):
        return (
            "acceptance_classes are immutable once the task is done "
            f"(current {sorted(set(current_classes or []))} != "
            f"proposed {sorted(set(proposed_classes or []))})"
        )
    return None


def read_acceptance_classes(task: Mapping[str, object]) -> list[str]:
    """Read a task's ``acceptance_classes`` as a clean list of strings."""
    raw = task.get("acceptance_classes")
    if raw is None:
        return []
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, (list, tuple)):
        return [str(c) for c in raw]
    return []
