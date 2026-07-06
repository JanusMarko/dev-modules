"""CLI entrypoint for /auto-decision-doc — invoked by the SKILL.md flow.

Reads the parley msg body from `--from-file` or stdin, runs the
detection + funnel pipeline, prints a structured JSON result on stdout.
Exit code 0 on `filed` / `dry_run` / `already_filed` / `no_trigger` /
`low_confidence`; non-zero only on hard errors (missing args, bad scope).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# When invoked as a script, ensure the adjacent `detect.py` and the dev-mgmt
# lib are importable.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
_LIB = _HERE.parent.parent / "scripts" / "dev-mgmt"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

import auto_file  # noqa: E402  (path-mutate first by design)


def _read_body(args) -> str:
    if args.from_file:
        return Path(args.from_file).read_text(encoding="utf-8")
    if args.stdin or not sys.stdin.isatty():
        return sys.stdin.read()
    raise SystemExit("auto-decision-doc: pass --from-file PATH or pipe via --stdin")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="auto-decision-doc",
        description=(
            "v1-AUTO: detect CTO-RATIFY shape + classify decision_shape in "
            "a parley msg body and file a workshop-lite Decision entity "
            "(via the record-decision dual-recording funnel). Hard Rule 2: "
            "writes own cwd only. Cohort C D2 added v1-AUTO categorization "
            "(decision_shape ∈ {go-no-go, select-from-n, ratify-direction, "
            "deferral, ambiguous}); operator override via "
            "--decision-shape-override."
        ),
    )
    p.add_argument("--msg-id", required=True,
                   help="parley msg-id (provenance + idempotency key)")
    p.add_argument("--scope", required=True,
                   help="decision scope (e.g. `sprint:foo.1`, `design:bar`, `repo:area`)")
    p.add_argument("--author", required=True,
                   help="filing member id (e.g. @wl-alpha)")
    p.add_argument("--authored-with", default="",
                   help="comma-separated co-authors (e.g. @plan)")
    p.add_argument("--from-file", help="read body from path")
    p.add_argument("--stdin", action="store_true",
                   help="read body from stdin (default if not a tty)")
    p.add_argument("--title-override",
                   help="override detected title (recommended; detection is heuristic)")
    p.add_argument("--rationale-override",
                   help="override detected rationale")
    p.add_argument(
        "--decision-shape-override",
        choices=["go-no-go", "select-from-n", "ratify-direction",
                 "deferral", "ambiguous"],
        default=None,
        help="cohort C D2 v1-AUTO: override the auto-classified "
             "decision_shape (default: use detector classification)",
    )
    p.add_argument("--repo-root", help="override the write target (default: cwd)")
    p.add_argument("--dry-run", action="store_true",
                   help="parse + report would-file payload without writing")
    p.add_argument("--min-confidence", default="medium",
                   choices=["low", "medium", "high"],
                   help="minimum detection confidence required to file")
    args = p.parse_args(argv)

    body = _read_body(args)
    authored_with = [a.strip() for a in args.authored_with.split(",") if a.strip()]

    out = auto_file.auto_file_from_msg(
        msg_id=args.msg_id,
        body=body,
        scope=args.scope,
        author=args.author,
        authored_with=authored_with,
        title_override=args.title_override,
        rationale_override=args.rationale_override,
        decision_shape_override=args.decision_shape_override,
        repo_root=args.repo_root,
        dry_run=args.dry_run,
        min_confidence=args.min_confidence,
    )

    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
