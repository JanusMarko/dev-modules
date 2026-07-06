"""MCP server exposing workshop-lite verbs to MCP clients.

Stdio MCP transport wrapping the existing `.claude/scripts/dev-mgmt/` callables
(entities / dispatch / prd / wip_claim / whereami / pending_views / cross_links)
as MCP tools. CLI stays canonical; this is strictly additive per decision
2026-06-04-05 Option A.

Charter (5 decisions in force):
  * 2026-06-04-05  Option A shape (8 write verbs, thin wrapper around Python lib)
  * 2026-06-04-06  build sequencing + 5-item test plan
  * 2026-06-04-07  amendment 1: 4 read tools (wl_whereami / wl_list_pending /
                   wl_read_entity / wl_cross_links_walk)
  * 2026-06-05-01  amendment 2: 11 transition verbs (record_dispatch / record_prd
                   / record_wip + 8 state-machine variants)
  * 2026-06-05-02  amendment 3a: domain-error-translation requirement; test-4
                   REVERT to single-write codex-spawn; LOC estimate revised up
  * 2026-06-05-03  amendment 3b: stdout-isolation + canonical typed-schema
                   derivation + structured MCP error translation

Hard rule 1 (parley-agnostic): this module does NOT import or shell out to parley.

Chunk-1 deliverable (this file): skeleton + robustness infra (q2-agnostic).
Chunks 2/3/4 register the 23 verbs via `register_*` entry points.
"""

# ---------------------------------------------------------------------------
# Venv-aware re-exec (matching cli.py OBS-G Part 2.2 convention). When
# mcp_server.py is invoked under a Python interpreter that isn't under the
# project `.venv/`, search ancestors for `.venv/bin/python` and re-exec.
# Required because host configs (CC mcp.json / codex config.toml / gemini
# extensions manifest) invoke as `python3 .claude/scripts/dev-mgmt/
# mcp_server.py` per workshop-lite flat-lib convention (CLAUDE.md).
# ---------------------------------------------------------------------------
from __future__ import annotations

import os as _os
import sys as _sys
from pathlib import Path as _Path


def _find_project_venv_dir(*, here: _Path | None = None) -> _Path | None:
    """Walk from this script upward for the project `.venv/`, stopping at the
    project boundary. Returns the .venv dir, not the python binary —
    caller resolves the launcher path.

    Three root-anchor markers stop the walk: ``pyproject.toml``,
    ``.git`` (file or dir), or a ``.claude/`` dir directly under the
    candidate. Closes wl:2026-06-06-08 finding F2: in a non-pyproject
    consumer, the walk previously leaked past repo root in search of
    pyproject.toml and could resolve to an unrelated parent-directory
    venv. The ``here`` kwarg exists for testability (matches cli.py
    convention).
    """
    here = (here or _Path(__file__).resolve())
    for d in (here.parent, *here.parent.parents):
        venv_dir = d / ".venv"
        if (venv_dir / "bin" / "python").is_file():
            return venv_dir
        if (d / "pyproject.toml").is_file():
            break
        if (d / ".git").exists():
            break
        if (d / ".claude").is_dir():
            break
    return None


def _maybe_reexec_via_venv() -> None:
    """Re-exec under the project `.venv` if not already inside it.

    Uses `sys.prefix` (not `sys.executable` path comparison) because on Linux
    `.venv/bin/python` is commonly a symlink chain ending at the system
    interpreter; resolved-path comparison would falsely conclude "already
    inside venv" and skip re-exec, leaving the venv's site-packages
    inaccessible. `sys.prefix` reflects the launcher's pyvenv.cfg resolution
    so it correctly distinguishes the two cases.
    """
    if _os.environ.get("WORKSHOP_LITE_SKIP_VENV_REEXEC"):
        return
    venv_dir = _find_project_venv_dir()
    if venv_dir is None:
        return
    if _Path(_sys.prefix).resolve() == venv_dir.resolve():
        return
    launcher = venv_dir / "bin" / "python"
    _os.execv(str(launcher), [str(launcher), *_sys.argv])


_maybe_reexec_via_venv()


# ---------------------------------------------------------------------------
# Finding 1 (HIGH) per decision 2026-06-05-03 — STDOUT ISOLATION
# MCP-over-stdio writes JSON-RPC frames to stdout. Any stray print() / log /
# warning from imported modules will corrupt the stream and immediately crash
# the client connection. Route ALL diagnostics to stderr BEFORE any other
# import that might emit on load.
# ---------------------------------------------------------------------------

import logging as _logging
import warnings as _warnings

_logging.basicConfig(stream=_sys.stderr, level=_logging.WARNING, force=True)


def _warn_to_stderr(message, category, filename, lineno, file=None, line=None):
    del file, line  # unused but required by warnings.showwarning signature
    print(
        f"{filename}:{lineno}: {category.__name__}: {message}",
        file=_sys.stderr,
    )


_warnings.showwarning = _warn_to_stderr

# ---------------------------------------------------------------------------
# Imports (all safe-for-stdio now that diagnostics are routed)
# ---------------------------------------------------------------------------
import asyncio
import functools
import inspect
import json
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in _sys.path:
    _sys.path.insert(0, str(_HERE))

import argparse  # noqa: E402

import mcp.server.stdio  # noqa: E402
import mcp.types as mcp_types  # noqa: E402
from mcp.server.lowlevel import NotificationOptions, Server  # noqa: E402
from mcp.server.models import InitializationOptions  # noqa: E402

# Workshop-lite domain exceptions (per Finding 3 error-translation surface)
from validators import ValidationError  # noqa: E402
from wip_claim import WipClaimCollisionError  # noqa: E402
from id_resolver import IdResolverError  # noqa: E402

# q2 ratify msg-6ef9864a89bd: argparse-introspection canonical (option c).
from mcp_schema_derive import argparse_to_json_schema, get_subparser  # noqa: E402

# Path-aware cli loader: same hardening as mcp_adapters._load_canonical_cli.
# `import cli` is fragile in pytest's full-suite run where another test
# (tests/test_auto_decision_doc.py) inserts .claude/skills/auto-decision-doc/
# at sys.path[0], shadowing this dir's cli.py. spec_from_file_location loads
# the right file unambiguously.
import importlib.util as _il_util  # noqa: E402


def _load_canonical_cli():
    cli_path = Path(__file__).resolve().parent / "cli.py"
    spec = _il_util.spec_from_file_location("_wl_canonical_cli", cli_path)
    assert spec is not None and spec.loader is not None
    mod = _il_util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod



SERVER_NAME = "workshop-lite"
SERVER_VERSION = "0.1.0"


# ---------------------------------------------------------------------------
# Tool registry (q2 ratified: option (c) 2.iii-argparse-introspection)
#
# Each `VerbSpec` carries a handler callable, a description, and the
# `schema_source` argparse subparser introspected at server boot to emit
# the MCP tool's `inputSchema` (per `mcp_schema_derive.argparse_to_json_schema`).
#
# Chunks 2/3/4 register each of the 23 verbs by binding the verb name to the
# matching cli.py subparser + a per-verb adapter function that replays cli.py
# main()'s post-parse logic before calling the entities/dispatch/prd/wip_claim
# handler. This preserves CLI/MCP byte-identical parity (test #3 per -02).
# ---------------------------------------------------------------------------


@dataclass
class VerbSpec:
    name: str
    handler: Callable[..., Any]
    description: str
    # Schema source can be either an argparse subparser (q2=(c) introspection
    # path; used for verbs that match a cli.py subparser 1:1) OR a literal
    # JSON Schema dict (used for verbs without a CLI equivalent — e.g. the
    # chunk-3 read tools wl_read_entity / wl_cross_links_walk; the chunk-3
    # wl_list_* tools that don't have CLI subparsers; wl_whereami composing
    # from multiple lib calls). `_derive_input_schema` picks based on type.
    schema_source: argparse.ArgumentParser | dict[str, Any] | None = None
    kind: str = "write"  # "write" | "read" | "transition"


class ToolRegistry:
    def __init__(self) -> None:
        self._verbs: dict[str, VerbSpec] = {}

    def register(self, spec: VerbSpec) -> None:
        if spec.name in self._verbs:
            raise ValueError(f"verb {spec.name!r} already registered")
        self._verbs[spec.name] = spec

    def get(self, name: str) -> VerbSpec | None:
        return self._verbs.get(name)

    def all(self) -> list[VerbSpec]:
        return list(self._verbs.values())


_REGISTRY = ToolRegistry()


def get_registry() -> ToolRegistry:
    return _REGISTRY


def _derive_input_schema(spec: VerbSpec) -> dict[str, Any]:
    """Derive the MCP `inputSchema` JSON-Schema for a verb.

    For verbs with a CLI counterpart (chunk-2 + chunk-4 transition verbs that
    match cli.py subparsers): `schema_source` is an `argparse.ArgumentParser`
    introspected per q2=(c) ratify (msg-6ef9864a89bd).

    For verbs without a CLI counterpart (chunk-3 read tools wl_read_entity /
    wl_cross_links_walk / wl_whereami / wl_list_* variants): `schema_source`
    is a hand-written JSON Schema dict, returned as-is.

    Falls back to a permissive object schema when no source is bound (chunk-1
    pre-registration state or a test-stub VerbSpec).
    """
    if spec.schema_source is None:
        return {"type": "object", "additionalProperties": True}
    if isinstance(spec.schema_source, dict):
        return spec.schema_source
    return argparse_to_json_schema(spec.schema_source)


def _coerce_args(spec: VerbSpec, arguments: dict[str, Any]) -> dict[str, Any]:
    """Pass through MCP args; the SDK's call_tool with validate_input=True
    enforces the inputSchema before this is reached. Per-verb post-parse
    (CSV splits, JSON parsing of --options-json, etc.) lives in the adapter
    bound at `spec.handler` (chunks 2/3/4).
    """
    return dict(arguments)


# ---------------------------------------------------------------------------
# Finding 3 (MEDIUM) per decision 2026-06-05-03 — STRUCTURED ERROR TRANSLATION
# Convergent with decision 2026-06-05-02 (I) and collaborator review
# 2026-06-05-05 insight #2.
#
# Every domain-exception class raised by a workshop-lite handler must be caught
# at the dispatch boundary and translated into a structured MCP `CallToolResult`
# with `isError=true` carrying actionable diagnostic text the LLM can parse and
# act on. Raw Python tracebacks must NEVER surface to the MCP client.
# ---------------------------------------------------------------------------


# Domain-exception → error-tag map. Tag goes in the error text so agents can
# pattern-match without parsing free-form messages.
_DOMAIN_EXCEPTION_TAGS: dict[type[BaseException], str] = {
    ValidationError: "validation_error",
    WipClaimCollisionError: "wip_collision",
    IdResolverError: "id_not_found",
    FileNotFoundError: "file_not_found",
    KeyError: "key_error",
    ValueError: "value_error",
}


def _format_domain_error(exc: BaseException, verb_name: str) -> str:
    """Build an actionable error-text body for a domain exception.

    Format:  `[<tag>] <verb_name>: <message>`
    Agents can match on the leading `[<tag>]` to branch on error class
    without parsing free-form Python repr.
    """
    tag = "domain_error"
    for cls, t in _DOMAIN_EXCEPTION_TAGS.items():
        if isinstance(exc, cls):
            tag = t
            break
    msg = str(exc) or exc.__class__.__name__
    return f"[{tag}] {verb_name}: {msg}"


def _format_unexpected_error(exc: BaseException, verb_name: str) -> str:
    """Build error-text for an unexpected (non-domain) exception.

    Includes the exception class name + message but NOT the traceback (the
    traceback goes to stderr so the operator sees it, but the MCP client
    only sees the structured body).
    """
    return f"[unexpected_error] {verb_name}: {exc.__class__.__name__}: {exc}"


def translate_errors(verb_name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator: catch domain + unexpected exceptions, return structured text.

    Wraps a handler so it returns `(ok: bool, text: str, payload: Any)`
    instead of raising. The MCP call_tool dispatch builds the CallToolResult
    from the tuple.
    """

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> tuple[bool, str, Any]:
            try:
                result = fn(*args, **kwargs)
                return (True, "", result)
            except tuple(_DOMAIN_EXCEPTION_TAGS.keys()) as exc:
                # stderr trace for operator visibility; client sees only the
                # structured body.
                traceback.print_exc(file=_sys.stderr)
                return (False, _format_domain_error(exc, verb_name), None)
            except Exception as exc:  # noqa: BLE001 — last-resort net
                traceback.print_exc(file=_sys.stderr)
                return (False, _format_unexpected_error(exc, verb_name), None)

        return wrapper

    return decorator


# ---------------------------------------------------------------------------
# MCP Server setup + list_tools / call_tool handlers
# ---------------------------------------------------------------------------

_server: Server = Server(SERVER_NAME, version=SERVER_VERSION)


@_server.list_tools()
async def _handle_list_tools() -> list[mcp_types.Tool]:
    """Return the registered tool inventory.

    Chunk-1 ships an empty registry; chunks 2/3/4 register the 23 verbs via
    the `register_*` entry points called from `_register_all_verbs()`.
    """
    return [
        mcp_types.Tool(
            name=spec.name,
            description=spec.description,
            inputSchema=_derive_input_schema(spec),
        )
        for spec in _REGISTRY.all()
    ]


def _result_text(text: str, is_error: bool = False) -> mcp_types.CallToolResult:
    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(type="text", text=text)],
        isError=is_error,
    )


@_server.call_tool()
async def _handle_call_tool(
    name: str, arguments: dict[str, Any] | None
) -> mcp_types.CallToolResult:
    """Dispatch an MCP `tools/call` to the registered handler.

    Routes through `translate_errors` (Finding 3) so domain exceptions become
    structured `isError=true` results with `[<tag>]`-prefixed actionable text.
    """
    spec = _REGISTRY.get(name)
    if spec is None:
        return _result_text(
            f"[unknown_tool] no verb registered under name {name!r}",
            is_error=True,
        )

    arguments = arguments or {}
    try:
        coerced = _coerce_args(spec, arguments)
    except (ValidationError, ValueError) as exc:
        return _result_text(_format_domain_error(exc, name), is_error=True)

    # Sync handlers run via the wrapped callable; async handlers (none yet
    # in the workshop-lite lib, but reserved) run via await.
    wrapped = translate_errors(name)(spec.handler)
    if inspect.iscoroutinefunction(spec.handler):
        ok, err_text, payload = await wrapped(**coerced)  # type: ignore[misc]
    else:
        ok, err_text, payload = wrapped(**coerced)

    if not ok:
        return _result_text(err_text, is_error=True)

    # Default payload serialization: pathlib.Path → str; everything else
    # via str() fallback. Chunks 2/3/4 may override per-verb if structured
    # content needs richer shape.
    if isinstance(payload, Path):
        body = str(payload)
    elif isinstance(payload, (dict, list)):
        body = json.dumps(payload, default=str, indent=2)
    elif payload is None:
        body = "(ok)"
    else:
        body = str(payload)

    return _result_text(body)


# ---------------------------------------------------------------------------
# Per-chunk verb registration entry points (filled in by chunks 2/3/4)
# ---------------------------------------------------------------------------


def register_chunk2_write_verbs(registry: ToolRegistry) -> None:
    """Register the 8 write verbs from decision 2026-06-04-05.

    record_decision / record_issue / record_review / record_handoff /
    capture_conversation / start_sprint / end_sprint / add_task

    Each verb binds (a) the cli.py argparse subparser as `schema_source` for
    inputSchema derivation per q2=(c) and (b) a per-verb adapter from
    `mcp_adapters` that replays cli.py main()'s post-parse logic.
    """
    import mcp_adapters
    cli = _load_canonical_cli()

    top = cli._build_parser()
    for cli_name, mcp_name, adapter, description, kind in mcp_adapters.chunk2_bindings():
        subparser = get_subparser(top, cli_name)
        registry.register(VerbSpec(
            name=mcp_name,
            handler=adapter,
            description=description,
            schema_source=subparser,
            kind=kind,
        ))


def register_chunk3_read_tools(registry: ToolRegistry) -> None:
    """Register the read tools from decision 2026-06-04-07.

    wl_whereami / wl_list_pending (4 variants) / wl_read_entity /
    wl_cross_links_walk. 7 MCP tools total per charter wording.

    These tools have no 1:1 CLI subparser counterpart (the 4 charter slots
    are lib-callables backed by whereami_substrate_router / pending_views /
    entities / cross_links); `schema_source` is a hand-written JSON Schema
    dict per tool, picked up by `_derive_input_schema` via isinstance check.
    """
    import mcp_adapters

    for mcp_name, adapter, description, input_schema in mcp_adapters.chunk3_bindings():
        registry.register(VerbSpec(
            name=mcp_name,
            handler=adapter,
            description=description,
            schema_source=input_schema,
            kind="read",
        ))


def register_chunk4_transition_verbs(registry: ToolRegistry) -> None:
    """Register the 11 transition verbs from decision 2026-06-05-01.

    record_dispatch + satisfy + supersede / record_prd + 4 state transitions
    / record_wip + release + extend

    Same q2=(c) argparse-introspection pattern as chunk-2: each verb binds the
    cli.py argparse subparser as `schema_source` and a per-verb adapter from
    `mcp_adapters`. The chunk-4 subparsers use positional ids (claim_id,
    dispatch_id, prd_id, new_id, old_id, duration) — picked up by the chunk-4
    extension to `mcp_schema_derive.argparse_to_json_schema` which emits
    positionals as `required` properties.
    """
    import mcp_adapters
    cli = _load_canonical_cli()

    top = cli._build_parser()
    for cli_name, mcp_name, adapter, description, kind in mcp_adapters.chunk4_bindings():
        subparser = get_subparser(top, cli_name)
        registry.register(VerbSpec(
            name=mcp_name,
            handler=adapter,
            description=description,
            schema_source=subparser,
            kind=kind,
        ))


def _register_all_verbs() -> None:
    register_chunk2_write_verbs(_REGISTRY)
    register_chunk3_read_tools(_REGISTRY)
    register_chunk4_transition_verbs(_REGISTRY)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def main() -> None:
    _register_all_verbs()
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await _server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name=SERVER_NAME,
                server_version=SERVER_VERSION,
                capabilities=_server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


def main_sync() -> None:
    """Synchronous entry point for the `wl-mcp-server` console script."""
    asyncio.run(main())


if __name__ == "__main__":
    main_sync()
