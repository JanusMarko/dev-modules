"""Cross-session namespace `<host>:<id>` resolution (Phase 4 of the
workshop-lite re-arch arc).

Per master design §3.1 (binding):

1. Bare ID (no colon) resolves to ``(current_host, bare_id)``.
2. ``<host>:<id>`` form resolves to ``(host, id)``.
3. ``org:<id>`` is a reserved org-level bucket (currently a placeholder
   per master §8.2 row "D-RA-7 mapping"; resolution deferred to the
   multi-host gateway primitive in parley Phase 3 per audit MED #10).

PARLEY-AGNOSTIC (CLAUDE.md Hard Rule 1): this module is pure string
parsing. NO parley imports, NO shell-outs, NO I/O. The resolver is
called from :mod:`cross_links` (also parley-agnostic) + the entity
writers, never from a skill/hook layer.

NOT A JUDGMENT COMPONENT (Hard Rule 7): pure deterministic parsing on
a fixed grammar.

D-RA-7 alignment: parley's per-host workshop-lite namespace prefix
scheme is reflected here as the parsing layer. A cross-host reference
``maxai:D15`` cited inside a ``workshop-lite`` repo's entity is treated
as VALID by the cross-link validator — the target lives on another
host's filesystem and is unreachable here by construction; emitting an
"unresolved" warning would be a false positive.
"""
from __future__ import annotations


DEFAULT_HOST = "workshop-lite"
ORG_HOST = "org"

# Hosts other than the current-host that are recognized as valid
# cross-host prefixes. The ``org:`` bucket is a placeholder for the
# multi-host gateway primitive (parley Phase 3) per master §8.2.
# Empty here means "any non-current host string is treated as a valid
# cross-host prefix" — we don't enumerate hosts at the WL layer
# (deferred to the gateway).


class IdResolverError(ValueError):
    """Raised when an entity-id string is malformed.

    Subclass of ``ValueError`` so callers can catch either name; the
    sub-class lets the validator surface a more specific category if
    needed without breaking the existing ``except ValueError`` paths
    in the entity writers.
    """


def _validate_input(entity_id: str) -> None:
    if not isinstance(entity_id, str):
        raise IdResolverError(
            f"entity_id must be a string, got: {type(entity_id).__name__}"
        )
    if not entity_id:
        raise IdResolverError("entity_id must be a non-empty string")
    # Reject whitespace-only strings + leading/trailing whitespace
    # (parley FQID convention forbids whitespace; the bare-id form
    # must also be whitespace-free).
    if entity_id != entity_id.strip():
        raise IdResolverError(
            f"entity_id must not have leading/trailing whitespace: "
            f"{entity_id!r}"
        )
    if any(c.isspace() for c in entity_id):
        raise IdResolverError(
            f"entity_id must not contain whitespace: {entity_id!r}"
        )


def resolve_id(
    entity_id: str,
    *,
    current_host: str = DEFAULT_HOST,
) -> tuple[str, str]:
    """Parse an entity-id string into ``(host, bare_id)``.

    Per master design §3.1:

    1. Bare ID (no ``:``) → ``(current_host, entity_id)``.
    2. ``<host>:<id>`` → ``(host, id)``; first colon is the separator.
    3. ``org:<id>`` → ``("org", id)``; treated like any other host
       prefix at the parsing layer.

    Raises :class:`IdResolverError` (subclass of ``ValueError``) for:

    - Empty / non-string inputs.
    - Inputs containing whitespace.
    - Inputs with empty host or empty bare-id after split
      (e.g. ``":D15"`` or ``"maxai:"``).
    - Multi-colon inputs (e.g. ``"foo:bar:baz"``) — the grammar is
      first-colon-only-split; an additional colon is reserved for the
      future ``<host>:<session>:<member>`` FQID grammar at the parley
      layer and would be ambiguous at the WL entity-id layer.

    The first-colon-only-split is documented above; additional colons
    raise. This is the stricter of the two options outlined in the
    test plan: explicit failure on ambiguity beats silent misroute.
    """
    _validate_input(entity_id)

    if ":" not in entity_id:
        return (current_host, entity_id)

    parts = entity_id.split(":")
    # Multi-colon → raise (per docstring / test 10).
    if len(parts) != 2:
        raise IdResolverError(
            f"entity_id with multiple colons is ambiguous; "
            f"first-colon-only-split grammar requires exactly one "
            f"colon, got: {entity_id!r}"
        )

    host, bare_id = parts
    if not host:
        raise IdResolverError(
            f"entity_id host prefix must be non-empty, got: {entity_id!r}"
        )
    if not bare_id:
        raise IdResolverError(
            f"entity_id bare-id portion must be non-empty, got: {entity_id!r}"
        )
    return (host, bare_id)


def is_cross_host(
    entity_id: str,
    *,
    current_host: str = DEFAULT_HOST,
) -> bool:
    """Return True if ``entity_id`` resolves to a host other than
    ``current_host``.

    Bare IDs (no colon) are NEVER cross-host (they resolve to the
    current host by construction). ``<current_host>:<id>`` is also
    NOT cross-host (the prefix is equivalent to bare form). Any other
    prefix — including ``org:`` — is cross-host.

    Mirrors :func:`resolve_id`'s parsing; raises the same errors on
    malformed input (callers that pre-validate can ignore the raise).
    """
    host, _bare = resolve_id(entity_id, current_host=current_host)
    return host != current_host


def canonical_id(host: str, bare_id: str) -> str:
    """Return the full ``<host>:<bare_id>`` canonical form.

    No parsing, no validation beyond non-empty checks — the function
    is the dual of :func:`resolve_id` and assumes ``host`` + ``bare_id``
    are already-split components. Useful when the caller has a
    ``(host, bare_id)`` tuple and wants the canonical string form for
    storage or comparison.
    """
    if not isinstance(host, str) or not host:
        raise IdResolverError(
            f"canonical_id host must be a non-empty string, got: {host!r}"
        )
    if not isinstance(bare_id, str) or not bare_id:
        raise IdResolverError(
            f"canonical_id bare_id must be a non-empty string, got: "
            f"{bare_id!r}"
        )
    if ":" in host:
        raise IdResolverError(
            f"canonical_id host must not contain ':', got: {host!r}"
        )
    if ":" in bare_id:
        raise IdResolverError(
            f"canonical_id bare_id must not contain ':', got: {bare_id!r}"
        )
    return f"{host}:{bare_id}"
