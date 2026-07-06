"""SessionStart-time sidecar driver for sync-from-parley.

Per the binding sub-spec at
``docs/design/2026-05-29-wl-sync-from-parley-spec.md`` §6.1 (Phase 1
default = sidecar at SessionStart). This driver:

1. Reads the consolidated workshop-lite config (Hard Rule 3 prefix).
   Opted-out (``enabled=false`` or absent): silent no-op.
2. Detects parley on PATH. Absent: silent no-op (Hard Rule 5).
3. Discovers the current session id via ``parley whoami`` when the
   config's ``sessions`` list is empty (sub-spec §7).
4. For each session: loads the cursor, invokes ``parley get --kind
   decision,blocker_raised,blocker_resolved --since <cursor> --json``,
   hands the parsed records to :func:`sync_from_parley.sync_chat_jsonl`
   (which is parley-agnostic per Hard Rule 1), and the library updates
   the cursor + writes entities.

   NOTE: ``epic_shipped`` is intentionally NOT in the ``--kind`` arg.
   Per D-WL-22 (2026-05-30), EpicShipped auto-sync is DEFERRED until
   parley primitive #6 publishes its actual emit-Kind enum binding.
   The current parley CLI (as of the closure cycle) rejects
   ``epic_shipped`` as an unknown ``--kind`` value, and ``parley
   ship-epic`` actually emits a different Kind enum chain
   (``SHIP_EPIC_REQUESTED → LANDED → LOADED → SHIPPED | ABORTED``).
   The EpicShipped entity TYPE + manual writer remain in the library
   for direct callers; only the auto-sync path is gated.

PARLEY-COUPLED (sidecar layer only — Hard Rule 1 conformance):
the library import ``sync_from_parley`` does NOT shell out to parley.
This driver is the ONLY place in the Phase 2 Cycle 2 deliverable that
runs ``parley`` as a subprocess. The boundary is precise: library
takes records-in / writes entities-out; driver does the parley I/O.

D33 + Hard Rule 5: this driver always exits 0. Any failure (parley
absent, parley error, cursor corruption, entity-write exception)
logs to the structured JSONL log and continues. Never blocks.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

# Make the dev-mgmt library importable.
_REPO_ROOT_HINT = Path(__file__).resolve().parent.parent.parent
_LIB_DIR = _REPO_ROOT_HINT / ".claude" / "scripts" / "dev-mgmt"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument(
        "--repo-root", required=True,
        help="Repo root (the parent of .claude/ and docs/).",
    )
    return p.parse_args(argv)


def _discover_current_session(parley_path: str) -> str | None:
    """Run ``parley whoami`` and pluck the session id. Return ``None``
    on any failure (parley not a member / parley error / parse error).
    """
    try:
        out = subprocess.run(
            [parley_path, "whoami"],
            capture_output=True, text=True, timeout=3,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if out.returncode != 0 or not out.stdout.strip():
        return None
    try:
        data = json.loads(out.stdout)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    session = data.get("session")
    if isinstance(session, dict):
        sid = session.get("sid")
        if isinstance(sid, str) and sid:
            return sid
    return None


def _fetch_records(
    parley_path: str, since: str | None,
) -> list[dict]:
    """Run ``parley get --kind ... --json --since <cursor>``. Returns the
    parsed record list, or ``[]`` on any failure.

    The library does the per-record dispatch; this driver only fetches.
    """
    # Per D-WL-22: only parley-supported Kinds in the --kind filter.
    # ``epic_shipped`` is excluded — current parley rejects it (rc=2) and
    # rc=2 on the comma-list fails the WHOLE invocation, suppressing
    # decision/blocker_raised/blocker_resolved sync as collateral damage.
    cmd = [
        parley_path, "get",
        "--kind", "decision,blocker_raised,blocker_resolved",
        "--json",
    ]
    if since:
        cmd += ["--since", since]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=8,
        )
    except (subprocess.TimeoutExpired, OSError):
        return []
    if proc.returncode != 0:
        return []
    raw = proc.stdout.strip()
    if not raw:
        return []
    # Try JSON-array first; fall back to JSONL.
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [r for r in data if isinstance(r, dict)]
    except json.JSONDecodeError:
        pass
    records: list[dict] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            if isinstance(obj, dict):
                records.append(obj)
        except json.JSONDecodeError:
            continue
    return records


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    repo = Path(args.repo_root).resolve()

    # Importing here so a missing library file doesn't crash the hook —
    # Hard Rule 5: never block.
    try:
        import sync_from_parley as _sfp  # type: ignore
    except Exception:
        return 0

    cfg = _sfp.load_sync_config(repo)
    if not cfg.get("enabled"):
        return 0

    parley_path = shutil.which("parley")
    if not parley_path:
        return 0

    sessions = list(cfg.get("sessions") or [])
    if not sessions:
        sid = _discover_current_session(parley_path)
        if sid:
            sessions = [sid]
    if not sessions:
        return 0

    cursor_path = repo / cfg["cursor_path"]
    log_path = repo / cfg["log_path"]

    # Defensive: corrupted cursor recovery (sub-spec §9 failure-mode #2).
    # `load_cursor` returns the empty default on parse failure; if the
    # file existed and is non-empty but produced the default, back it
    # up + reinit.
    if cursor_path.exists():
        try:
            text = cursor_path.read_text(encoding="utf-8")
            json.loads(text)
        except (OSError, json.JSONDecodeError):
            _sfp.backup_corrupted_cursor(cursor_path)

    cursor = _sfp.load_cursor(cursor_path)

    for sid in sessions:
        state = (cursor.get("sessions") or {}).get(sid) or {}
        since = state.get("last_msg_id")
        records = _fetch_records(parley_path, since)
        if not records:
            continue
        try:
            _sfp.sync_chat_jsonl(
                repo_root=repo,
                session_id=sid,
                chat_records=records,
                cursor_path=cursor_path,
                log_path=log_path,
            )
        except Exception:
            # Hard Rule 5: never block. Cursor stays at prior position
            # for this session; next SessionStart retries.
            continue
        # Re-read so the next session sees its own cursor state.
        cursor = _sfp.load_cursor(cursor_path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
