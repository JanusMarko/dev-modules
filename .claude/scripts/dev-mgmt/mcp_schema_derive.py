"""argparse → JSON Schema introspection for the workshop-lite MCP server.

Per decision 2026-06-05-03 Finding 2 + q2 ratify msg-6ef9864a89bd:
option (c) 2.iii-argparse approved. Introspect cli.py's argparse subparsers
(`cli._build_parser()._actions[*].choices[verb]`) at MCP server boot to emit
MCP tool inputSchemas. CLI stays the canonical source of truth for both arg
shapes and validation; MCP server derives.

The 23 workshop-lite verbs use simple argparse patterns:
  * `add_argument("--foo", required=, default=, choices=, help=, type=)`
  * `add_argument("name")` positional args (e.g. record-prd-ratify <prd_id>,
    record-dispatch-supersede <new_id> <old_id>)
  * `action="store_true"` / `action="store_false"`
  * `action="append"` for repeatable list args (e.g. record-dispatch
    `--linked-msg-id X --linked-msg-id Y`); MCP side emits a `type=array,
    items=string` schema for these (chunk-4 emergent extension)
  * `nargs="*"` / `nargs="+"` (a couple of cases for list-valued args)

If cli.py later introduces a non-mappable pattern (custom `type=callable`,
`action=` callback, `nargs="?"`, etc.) the introspector should be EXTENDED
here, NOT worked around in `mcp_server.py`.
"""

from __future__ import annotations

import argparse
from typing import Any


def get_subparser(
    top: argparse.ArgumentParser, verb_name: str
) -> argparse.ArgumentParser:
    """Return the named subparser from a top-level argparse parser.

    Raises ``KeyError`` if the verb is not registered or if the top-level
    parser has no subparsers action.
    """
    for action in top._actions:
        if isinstance(action, argparse._SubParsersAction):
            choices = action.choices
            if verb_name not in choices:
                raise KeyError(
                    f"verb {verb_name!r} not registered in top-level parser; "
                    f"available: {sorted(choices.keys())}"
                )
            return choices[verb_name]
    raise KeyError("no subparsers action in top-level parser")


def argparse_to_json_schema(
    subparser: argparse.ArgumentParser,
) -> dict[str, Any]:
    """Convert an argparse subparser to a JSON Schema describing its kwargs.

    Keys are argparse `dest` names (e.g. `options_json` from `--options-json`)
    so the dispatched handler can consume the result as ``**kwargs`` with no
    rename pass.
    """
    properties: dict[str, dict[str, Any]] = {}
    required: list[str] = []
    for action in subparser._actions:
        if action.dest == "help":
            continue
        if not action.option_strings:
            # Positional arg — argparse positionals are always required (unless
            # nargs makes them optional, which workshop-lite doesn't use).
            # Chunk-4 transition verbs introduced positional ids (claim_id,
            # dispatch_id, prd_id, new_id, old_id, duration).
            properties[action.dest] = _action_to_property(action)
            required.append(action.dest)
            continue
        properties[action.dest] = _action_to_property(action)
        if action.required:
            required.append(action.dest)
    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }
    if required:
        schema["required"] = required
    return schema


def _action_to_property(action: argparse.Action) -> dict[str, Any]:
    prop: dict[str, Any] = {}

    # Boolean flag (store_true / store_false): default lives on the action.
    if isinstance(action, (argparse._StoreTrueAction, argparse._StoreFalseAction)):
        prop["type"] = "boolean"
        prop["default"] = bool(action.default)
        if action.help and action.help != argparse.SUPPRESS:
            prop["description"] = action.help
        return prop

    # Repeatable list arg (action="append"): emit array-of-string. Chunk-4
    # transition verbs use this shape for --linked-msg-id on record-dispatch
    # and record-prd. Default is omitted (action=append's argparse default is
    # None which isn't a valid `default` for type=array; the adapter defends
    # via `list(kw.get(dest) or [])`).
    if isinstance(action, argparse._AppendAction):
        prop["type"] = "array"
        prop["items"] = {"type": "string"}
        if action.help and action.help != argparse.SUPPRESS:
            prop["description"] = action.help
        return prop

    # Enum-via-choices. Some CLI args list None as a valid choice (e.g.
    # `--stage default=None choices=[None, "plan", "execute", "retro"]`); the
    # JSON Schema form widens type to allow null in those cases.
    if action.choices is not None and action.nargs is None:
        choices = list(action.choices)
        has_none = None in choices
        non_none = [c for c in choices if c is not None]
        if has_none:
            prop["type"] = ["string", "null"]
            prop["enum"] = [None, *non_none]
        else:
            prop["enum"] = choices
            if action.type is int:
                prop["type"] = "integer"
            elif action.type is float:
                prop["type"] = "number"
            else:
                prop["type"] = "string"
    elif action.nargs in ("*", "+"):
        prop["type"] = "array"
        prop["items"] = {"type": "string"}
    elif action.type is int:
        prop["type"] = "integer"
    elif action.type is float:
        prop["type"] = "number"
    else:
        prop["type"] = "string"

    if action.default is not None and action.default != argparse.SUPPRESS:
        prop["default"] = action.default

    if action.help and action.help != argparse.SUPPRESS:
        prop["description"] = action.help

    return prop
