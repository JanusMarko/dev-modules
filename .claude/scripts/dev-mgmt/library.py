"""WL2 library layering + same-layer collision resolver (BC1.4; spec §2.3).

`workflow` and `role-set` entries form a **layered override stack** on
`library_layer`: ``user ▷ project ▷ built-in`` (higher wins, **per entry**).
Precedence is **authority-gated, not positional** — a `user`-layer entry from a
principal lacking project-layer authority does NOT override the project entry.

A **same-layer, same-key collision** is resolved by the collision resolver
(realizing DOC1 §18 #13). Its rule is **deterministic, never positional-only,
gated by the placing principal's authority**. There is **no separate authority-
rank scalar** — authority is the existing identity model (§12 / DOC1 §8/§12),
consumed here through the :class:`AuthorityModel` protocol. The resolver reads
only already-defined authority relations; it introduces no new rank field.

Same-layer rule, in order:
  (1) if one principal holds **override-authority** (§12) over the other → it wins;
  (2) else if one placed via an authority the other lacks for this layer
      (the §8 layer-placement authority) → it wins;
  (3) else (genuine peer authority — neither dominates) → **`conflicts-with`**,
      surfaced for human resolution (never silently merged — C6/§5.3; never an
      arbitrary/positional pick).

A `conflicts-with` is a normal, loud result — NOT an exception. Callers MUST
surface it; silently picking one side or merging is the C6-b violation the
KA-25 cert axis kills.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Protocol, runtime_checkable


# The fixed layer-precedence order (spec §2.3). This is the *layer* ordering,
# NOT an authority rank — higher index = higher precedence. Authority gating
# (below) decides whether a higher-layer entry actually overrides a lower one.
LIBRARY_LAYERS: tuple[str, ...] = ("built-in", "project", "user")
_LAYER_RANK = {layer: rank for rank, layer in enumerate(LIBRARY_LAYERS)}


class LibraryError(ValueError):
    """Raised on malformed resolver input (e.g. duplicate (key,layer,principal))."""


@dataclass(frozen=True)
class LibraryEntry:
    """One workflow/role-set library entry in the override stack.

    ``key`` is the entry's identity within its kind (the slug). ``principal``
    is the placing identity (the authority model reasons over it). ``entry_id``
    + ``payload`` are opaque to the resolver — carried through for the caller.
    """

    key: str
    kind: str
    library_layer: str
    principal: str
    entry_id: str | None = None
    payload: object = None

    def __post_init__(self) -> None:
        if self.library_layer not in _LAYER_RANK:
            raise LibraryError(
                f"unknown library_layer {self.library_layer!r}; "
                f"must be one of {LIBRARY_LAYERS}"
            )


@runtime_checkable
class AuthorityModel(Protocol):
    """The identity-model interface the resolver consumes (§12 / DOC1 §8/§12).

    Abstraction-first: the resolver depends ONLY on this protocol, never on a
    concrete rank scalar. Any identity model that can answer these two
    relations plugs in.
    """

    def holds_override_authority(self, a: str, b: str) -> bool:
        """True iff principal ``a`` holds override-authority over ``b`` (§12)."""
        ...

    def holds_layer_authority(self, principal: str, layer: str) -> bool:
        """True iff ``principal`` holds the §8 layer-placement authority for
        ``layer`` (e.g. a project-lead identity for the ``project`` layer)."""
        ...


@dataclass(frozen=True)
class Resolved:
    """A key resolved to a single winning entry."""

    key: str
    winner: LibraryEntry
    shadowed: tuple[LibraryEntry, ...] = ()


@dataclass(frozen=True)
class ConflictsWith:
    """A key that could NOT be resolved — surfaced for human resolution.

    This is the loud C6-b outcome of a genuine same-layer peer-authority tie.
    It is NOT an error and NOT a silent merge; the caller must surface it.
    """

    key: str
    layer: str
    entries: tuple[LibraryEntry, ...]
    reason: str = "same-layer peer-authority tie (neither principal dominates)"


Resolution = Resolved | ConflictsWith


@dataclass(frozen=True)
class DefaultAuthorityModel:
    """A data-driven :class:`AuthorityModel` for the standalone floor.

    Reads *already-defined* relations — no rank invented:
      - ``override_edges``: set of ``(a, b)`` meaning principal ``a`` holds
        override-authority over ``b`` (§12). Directed, not auto-transitive.
      - ``layer_authorities``: mapping ``principal -> set(layer)`` — the §8
        layer-placement authorities the principal holds.
    """

    override_edges: frozenset[tuple[str, str]] = field(default_factory=frozenset)
    layer_authorities: dict[str, frozenset[str]] = field(default_factory=dict)

    def holds_override_authority(self, a: str, b: str) -> bool:
        return (a, b) in self.override_edges

    def holds_layer_authority(self, principal: str, layer: str) -> bool:
        return layer in self.layer_authorities.get(principal, frozenset())


def _dominates(a: LibraryEntry, b: LibraryEntry, layer: str,
               authority: AuthorityModel) -> bool:
    """Same-layer dominance of ``a`` over ``b`` per the spec's steps (1)+(2).

    (1) override-authority of a over b; OR
    (2) a holds the §8 layer-placement authority for ``layer`` and b does not.
    Step (3) (conflicts-with) is decided by the caller from the absence of a
    strict dominator — it is NOT a positional fallback.
    """
    if authority.holds_override_authority(a.principal, b.principal):
        return True
    if (authority.holds_layer_authority(a.principal, layer)
            and not authority.holds_layer_authority(b.principal, layer)):
        return True
    return False


def _resolve_same_layer(
    entries: list[LibraryEntry], layer: str, authority: AuthorityModel,
) -> LibraryEntry | ConflictsWith:
    """Resolve a same-(key,layer) group to a single winner or ConflictsWith.

    Returns the unique entry that **strictly dominates every other** entry in
    the group (a dominates b and b does not dominate a). If no such unique
    strict dominator exists → ConflictsWith (step 3): never a positional pick.
    """
    if len(entries) == 1:
        return entries[0]

    key = entries[0].key
    strict_dominators: list[LibraryEntry] = []
    for cand in entries:
        others = [e for e in entries if e is not cand]
        if all(
            _dominates(cand, other, layer, authority)
            and not _dominates(other, cand, layer, authority)
            for other in others
        ):
            strict_dominators.append(cand)

    if len(strict_dominators) == 1:
        return strict_dominators[0]
    return ConflictsWith(
        key=key, layer=layer, entries=tuple(entries),
    )


def resolve_key(
    entries: Iterable[LibraryEntry], authority: AuthorityModel,
) -> Resolution:
    """Resolve all entries for a single key to one winner or ConflictsWith.

    Two-stage:
      1. Within each layer, run the same-layer collision resolver. Any layer
         that yields ConflictsWith short-circuits the whole key to that
         conflict (loud; never resolved past an unresolved tie).
      2. Across layers, apply the authority-gated override stack top-down
         (user → project → built-in): the current winner overrides the next
         lower layer's representative IFF its principal holds the lower layer's
         placement authority OR override-authority over that principal. If it
         cannot override, the lower representative stands (and becomes the
         current winner — the gate denied the higher entry, per §2.3).
    """
    entry_list = list(entries)
    if not entry_list:
        raise LibraryError("resolve_key called with no entries")

    keys = {e.key for e in entry_list}
    if len(keys) != 1:
        raise LibraryError(f"resolve_key got mixed keys: {sorted(keys)}")
    key = keys.pop()

    # Precondition: at most one entry per (layer, principal). A caller placing
    # two distinct entries for the same (key, layer, principal) is malformed —
    # the resolver reasons over distinct placing principals.
    seen: set[tuple[str, str]] = set()
    for e in entry_list:
        sig = (e.library_layer, e.principal)
        if sig in seen:
            raise LibraryError(
                f"duplicate (layer={e.library_layer!r}, principal={e.principal!r}) "
                f"for key {key!r}; one entry per (key, layer, principal)"
            )
        seen.add(sig)

    # Stage 1 — per-layer same-layer resolution.
    by_layer: dict[str, list[LibraryEntry]] = {}
    for e in entry_list:
        by_layer.setdefault(e.library_layer, []).append(e)

    layer_reps: dict[str, LibraryEntry] = {}
    for layer, group in by_layer.items():
        rep = _resolve_same_layer(group, layer, authority)
        if isinstance(rep, ConflictsWith):
            return rep  # loud short-circuit (C6-b)
        layer_reps[layer] = rep

    # Stage 2 — authority-gated cross-layer override, top layer down.
    ordered_layers = sorted(layer_reps, key=lambda L: _LAYER_RANK[L], reverse=True)
    shadowed: list[LibraryEntry] = []
    current = layer_reps[ordered_layers[0]]
    for layer in ordered_layers[1:]:
        lower = layer_reps[layer]
        if _overrides_lower(current, lower, authority):
            shadowed.append(lower)
        else:
            # Gate denied: the higher entry cannot override the lower one, so
            # the lower entry stands (spec §2.3 user-lacking-project example).
            shadowed.append(current)
            current = lower

    return Resolved(key=key, winner=current, shadowed=tuple(shadowed))


def _overrides_lower(
    higher: LibraryEntry, lower: LibraryEntry, authority: AuthorityModel,
) -> bool:
    """Cross-layer override gate: ``higher`` (higher-precedence layer)
    overrides ``lower`` IFF its principal holds the lower layer's §8
    placement authority OR override-authority over the lower principal.

    This is the "authority-gated, not positional" rule — a higher-layer entry
    from a principal lacking authority over the lower layer does NOT override.
    """
    if authority.holds_override_authority(higher.principal, lower.principal):
        return True
    return authority.holds_layer_authority(higher.principal, lower.library_layer)


def resolve_library(
    entries: Iterable[LibraryEntry], authority: AuthorityModel,
) -> dict[str, Resolution]:
    """Resolve a whole library (many keys) → ``{key: Resolution}``.

    Each key resolves independently via :func:`resolve_key`. A ConflictsWith on
    one key never silently drops it — it surfaces in the result map for the
    caller to handle loudly.
    """
    by_key: dict[str, list[LibraryEntry]] = {}
    for e in entries:
        by_key.setdefault(e.key, []).append(e)
    return {key: resolve_key(group, authority) for key, group in by_key.items()}
