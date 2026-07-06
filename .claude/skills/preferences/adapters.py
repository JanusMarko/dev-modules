"""Preferences SKILL/HOOK-layer adapters (D27 — parley-coupling lives
HERE, never in the lib).

These are REAL, independently-usable second implementations of the
lib's ``Storage`` / ``ScopeResolver`` Protocols — substitutable into
``preferences.PreferenceProvider`` / ``get_preference`` WITHOUT
touching the lib (the non-vacuous swappability the design promises:
the interfaces are exercised by a genuine 2nd impl, not a decorative
ABC). The lib NEVER imports this module; this module only depends on
the lib's Protocol *shape* (structural — no import needed).

Hard Rule 1: ``ParleyHumanScopeResolver`` shells ``parley`` — that is
why it is here at the skill/hook layer and NOT in the parley-agnostic
lib. Any failure degrades to the injected fallback resolver (never
raises into the consumer; "default" is the safe terminal).
"""

from __future__ import annotations

import json
import os
import subprocess
from typing import Any


class ParleyHumanScopeResolver:
    """SKILL/HOOK-layer ScopeResolver: resolve the HUMAN operator's
    stable user-id from the live parley session (``parley whoami`` ->
    ``humans[0].id``). The user is the human, NOT the agent member
    (@plan ruling (b)). Parley absent / any failure => delegate to
    ``fallback`` (default = the lib's parley-agnostic resolver).
    """

    def __init__(self, fallback: Any | None = None) -> None:
        if fallback is None:
            # imported lazily so this module has no hard lib import at
            # definition time; the lib stays unaware of this adapter.
            import importlib.util
            import sys
            from pathlib import Path
            lib = Path(__file__).resolve().parents[2] / "scripts" / "dev-mgmt"
            if str(lib) not in sys.path:
                sys.path.insert(0, str(lib))
            spec = importlib.util.spec_from_file_location(
                "preferences", lib / "preferences.py")
            assert spec is not None and spec.loader is not None
            mod = importlib.util.module_from_spec(spec)
            sys.modules.setdefault("preferences", mod)
            spec.loader.exec_module(mod)
            fallback = mod.DefaultScopeResolver()
        # always a real resolver past this point (never None):
        self._fallback: Any = fallback

    def resolve_user(self) -> str:
        try:
            r = subprocess.run(["parley", "whoami"],
                               capture_output=True, text=True, timeout=10)
            if r.returncode == 0 and r.stdout.strip():
                data = json.loads(r.stdout)
                humans = data.get("humans") or []
                if humans and isinstance(humans, list):
                    hid = str(humans[0].get("id") or "").strip()
                    if hid:
                        return hid
        except Exception:
            pass
        # parley absent / no human / any failure: delegate.
        try:
            return self._fallback.resolve_user() or "default"
        except Exception:
            return "default"


class EnvPreferenceStorage:
    """A REAL second Storage backend (proves non-vacuous swappability:
    a path-LESS backend riding the exact same interface as the
    file-backed default). Reads a JSON preferences document from an
    environment variable (default ``WSL_PREFS_JSON``). Graceful: unset
    / malformed => ``{}`` (never raises).
    """

    def __init__(self, var: str = "WSL_PREFS_JSON",
                 *, env: dict[str, str] | None = None) -> None:
        self._var = var
        self._env = os.environ if env is None else env
        self._doc: dict[str, Any] = {}

    def load(self) -> dict[str, Any]:
        raw = self._env.get(self._var)
        if not raw:
            return {}
        try:
            doc = json.loads(raw)
            return doc if isinstance(doc, dict) else {}
        except Exception:
            return {}

    def save(self, doc: dict[str, Any]) -> None:
        # In-process only (env is not ours to mutate durably); keeps
        # the Storage contract total without a filesystem path.
        self._doc = dict(doc)
        self._env[self._var] = json.dumps(doc)
