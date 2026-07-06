"""Substrate router for /whereami cross-repo any-pane-any-substrate
discovery (Sprint workshop-lite.25, closes issue 2026-05-16-02).

Pure JSON-dict processing — consumes a parley `whoami` dict and an
optional selector, returns the chosen SPRINT_ROOT path. Parley-agnostic
at the lib layer (Hard Rule 1): the parley CLI invocation lives at the
SKILL layer; this module never imports or shells out to parley.

D3 (per issue 2026-05-16-02): generalize the wl.12 D1 single-substrate
derivation to "any pane → any substrate." Currently gated on
@Par `parley.session-substrate-init` landing `peers[].substrate_path`;
the mechanism here ships with graceful degradation so when the peer
field arrives, routing activates without further WL-side change.

Routing precedence:

1. selector matches a `@<peer-id>` whose `peers[].substrate_path` is
   populated → use that peer's substrate.
2. selector is a path that exists on disk → use it directly.
3. No selector + `whoami_dict["substrate_path"]` is set → session-level
   substrate (the forward-compat field, populated by parley.session-
   substrate-init when it lands).
4. No selector + `session.sid` is set → derived
   `~/.parley/sessions/<sid>/dev-track` (the wl.12 D1 fallback that
   covers the current single-session case).
5. Else → None (unresolved).

Graceful degradation: in the current gated state (no peers carry
substrate_path, session-level substrate_path may also be None), the
router falls through to precedence #4 — the wl.12 D1 behavior.
"""
from __future__ import annotations

from pathlib import Path
from typing import NamedTuple


class RouteResult(NamedTuple):
    """The router's return shape — the resolved SPRINT_ROOT path
    (or None if unresolved) + a `route_kind` tag for caller logging.
    """
    sprint_root: Path | None
    route_kind: str


# Route-kind tags. Stable strings the SKILL/hook layer can render.
_ROUTE_PEER_SELECTOR = "peer-selector-substrate"
_ROUTE_PATH_SELECTOR = "path-selector"
_ROUTE_SESSION_SUBSTRATE = "session-substrate"
_ROUTE_SID_DERIVED = "sid-derived"
_ROUTE_UNRESOLVED = "unresolved"


def _coerce_peers(whoami_dict: dict) -> list[dict]:
    """Defensive coercion of whoami["peers"] to a list of dicts.
    Returns [] for any unexpected shape (forward-compatible against
    schema additions).
    """
    raw = whoami_dict.get("peers")
    if not isinstance(raw, list):
        return []
    return [p for p in raw if isinstance(p, dict)]


def _coerce_session_sid(whoami_dict: dict) -> str | None:
    """Defensive extraction of session.sid from whoami dict.
    Returns None when shape doesn't match.
    """
    sess = whoami_dict.get("session")
    if not isinstance(sess, dict):
        return None
    sid = sess.get("sid")
    if isinstance(sid, str) and sid:
        return sid
    return None


def _sid_derived_path(sid: str) -> Path:
    """Apply the wl.12 D1 derivation convention: a session with id
    `<sid>` has its dev-track substrate at
    `~/.parley/sessions/<sid>/dev-track`.

    Note: we DO NOT shell-eval the sid — `Path(...).expanduser()` is the
    safe operation (cf. W12-F2 / P4-MF2 unsanitized-sid hazard).
    """
    return Path(f"~/.parley/sessions/{sid}/dev-track").expanduser()


def _selector_is_peer_form(selector: str) -> bool:
    """Heuristic: a selector starting with `@` is a peer-id form."""
    return selector.startswith("@") and len(selector) > 1


def resolve_sprint_root(
    whoami_dict: dict,
    selector: str | None = None,
) -> RouteResult:
    """Resolve SPRINT_ROOT for the /whereami render.

    See module docstring for precedence semantics.

    Args:
        whoami_dict: parsed `parley whoami` JSON (or fixture equivalent).
        selector: optional `@<peer-id>` or absolute filesystem path.

    Returns:
        RouteResult(sprint_root, route_kind). sprint_root is None when
        unresolved (caller falls back to local single-root behavior).
    """
    if selector:
        if _selector_is_peer_form(selector):
            peer_id = selector[1:]  # strip leading '@'
            for peer in _coerce_peers(whoami_dict):
                if peer.get("id") != peer_id:
                    continue
                sp = peer.get("substrate_path")
                if isinstance(sp, str) and sp:
                    return RouteResult(
                        Path(sp).expanduser(), _ROUTE_PEER_SELECTOR,
                    )
            # Peer id matched no peer or peer had no substrate_path →
            # fall through to default routing; caller can flag.
        else:
            p = Path(selector).expanduser()
            if p.is_dir():
                return RouteResult(p, _ROUTE_PATH_SELECTOR)
            # Selector was a path but didn't resolve → fall through.

    # Precedence #3: session-level substrate_path is the forward-compat
    # field at the top level of whoami output (NOT inside session.*).
    # This is the field @Par will populate via parley.session-substrate-init.
    sp = whoami_dict.get("substrate_path")
    if isinstance(sp, str) and sp:
        return RouteResult(Path(sp).expanduser(), _ROUTE_SESSION_SUBSTRATE)

    # Precedence #4: wl.12 D1 fallback — derive from session.sid.
    sid = _coerce_session_sid(whoami_dict)
    if sid:
        return RouteResult(_sid_derived_path(sid), _ROUTE_SID_DERIVED)

    # Precedence #5: unresolved.
    return RouteResult(None, _ROUTE_UNRESOLVED)


def enumerable_substrates(
    whoami_dict: dict,
) -> list[tuple[str, Path]]:
    """Return list of `(peer_id, substrate_path)` for peers carrying a
    populated substrate_path.

    Caller (the SKILL layer) can use this to surface a "which substrate?"
    selection prompt when multiple options are available. Returns [] in
    the current gated state (no peers carry the field yet), preserving
    single-substrate behavior by graceful degradation.
    """
    out: list[tuple[str, Path]] = []
    for peer in _coerce_peers(whoami_dict):
        pid = peer.get("id")
        sp = peer.get("substrate_path")
        if isinstance(pid, str) and pid and isinstance(sp, str) and sp:
            out.append((pid, Path(sp).expanduser()))
    return out
