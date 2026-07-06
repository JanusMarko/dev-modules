"""Context-aware filter + auto context_bundle for consult-skill v2.0.

Per the ratified PRD at
``docs/prds/2026-06-03-01-consult-skill-v2-context-aware-consult.md``
(R1-R6 requirements + R7-R12 risk mitigations + R13 impl specifics).

Two public surfaces:

1. **R1 + R3 + R8 + R13 filter** — :func:`discover_visible_files`
   computes the file list visible to a consult invocation, using the
   par-plan-ratified PG-2 strategy: ``git ls-files --exclude-standard``
   for baseline .gitignore (cheap, correct, no Python re-implementation
   of gitwildmatch semantics) layered with a ``pathspec`` PathSpec
   parsed from ``.consultignore`` (positive excludes only; negation
   patterns stripped + diagnosed per PG-1 / R10).

2. **R2 auto context_bundle** — :func:`build_context_bundle` walks the
   target entity's forward links (``linked_decisions`` /
   ``linked_issues`` / ``linked_reviews`` / ``linked_handoffs`` /
   ``linked_conversations`` / ``linked_dispatches`` / ``linked_prds`` /
   ``linked_wip``), resolves each 1-hop only (no transitive expansion;
   loop guard for self-references), strips frontmatter, and assembles a
   deterministic-order markdown bundle. ``linked_msg_ids`` is excluded
   from auto-resolution because parley msg-ids cannot be resolved at
   the workshop-lite lib layer (CLAUDE.md HR-#1 parley-agnostic at base).

R9 ``--strict-context`` mode escalates MissingTarget from warn-and-skip
to fail-fast via :class:`MissingTargetStrict`.

R13 ``--verbose`` exposes the three filter stages
(a=raw / b=post-.gitignore / c=post-.consultignore) via the
``stages`` return value of :func:`discover_visible_files`.

R7 / R13 token-budget gate: :func:`estimate_token_count` and
:func:`estimate_files_payload` provide the byte-count // 4 estimation
(documented approximation per R13).

PARLEY-AGNOSTIC (CLAUDE.md HR-#1): this module imports neither parley
nor any parley wrapper. ``git`` subprocesses are permitted (HR-#1
constrains parley-coupling, not all shell-outs).
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import frontmatter as _fm
import ledger_paths


# Map ``linked_<field>`` to ``docs/<dir>`` + entity-kind label.
# Superset of cross_links._FIELD_TO_KIND because the v2.0 PRD R2
# explicitly enumerates dispatches / prds / wip too. Order is
# alphabetical for deterministic bundle traversal.
_FIELD_TO_DIR: dict[str, str] = {
    "linked_conversations": "conversations",
    "linked_decisions":     "decisions",
    "linked_dispatches":    "dispatches",
    "linked_handoffs":      "handoffs",
    "linked_issues":        "issues",
    "linked_prds":          "prds",
    "linked_reviews":       "reviews",
    "linked_wip":           "wip",
}

# Singular-kind label for bundle section headings.
_FIELD_TO_KIND_LABEL: dict[str, str] = {
    "linked_conversations": "conversation",
    "linked_decisions":     "decision",
    "linked_dispatches":    "dispatch",
    "linked_handoffs":      "handoff",
    "linked_issues":        "issue",
    "linked_prds":          "prd",
    "linked_reviews":       "review",
    "linked_wip":           "wip",
}


# R13: token-budget default. PRD: 500_000 tokens with headroom for
# 1M-token gemini Flash context window. Operator overrides via
# --token-budget CLI flag.
DEFAULT_TOKEN_BUDGET = 500_000


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class MissingTargetStrict(RuntimeError):
    """R9 ``--strict-context`` raises this when a linked entity does
    not resolve under any expected ``docs/<kind>/`` path. Carries the
    kind + bad-id for clear machine-readable diagnostics (R13).
    """

    def __init__(self, kind: str, bad_id: str, field: str):
        self.kind = kind
        self.bad_id = bad_id
        self.field = field
        super().__init__(
            f"consult: missing linked entity '{kind}:{bad_id}' "
            f"(target's {field} references it; --strict-context: "
            f"aborting per R9)"
        )


# ---------------------------------------------------------------------------
# R1 + R3 + R8 + R13 — filter mechanism
# ---------------------------------------------------------------------------


def _is_git_repo(repo_root: Path) -> bool:
    cmd = ["git", "-C", str(repo_root), "rev-parse", "--is-inside-work-tree"]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, check=False, timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0 and proc.stdout.strip() == "true"


def _git_ls_files(repo_root: Path, *flags: str) -> list[str]:
    """Run ``git ls-files [flags]``; return relative paths or [] on error."""
    cmd = ["git", "-C", str(repo_root), "ls-files", *flags]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, check=False, timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if proc.returncode != 0:
        return []
    return [line for line in proc.stdout.splitlines() if line]


def _read_consultignore(repo_root: Path):
    """Parse ``<repo_root>/.consultignore`` per PG-1 / R10 disposition.

    Strips ``!``-prefixed negation patterns (defer to v2.1) + emits a
    machine-readable diagnostic line per stripped pattern.

    Returns ``(PathSpec | None, list[diagnostic_strings])``.
    Missing file or empty file → ``(None, [])`` (no filter applied).
    """
    # local import: pathspec is a v2.0-introduced dep. OBS-G Part 2 catch:
    # surface an actionable bootstrap instruction when this hits the
    # interpreter-resolution edge case (cli.py re-exec was inert because no
    # ``.venv`` was reachable AND ``yaml`` happened to be system-installed
    # so the cli.py-top import-chain guard didn't fire).
    try:
        import pathspec
    except ImportError as exc:
        raise ImportError(
            f"workshop-lite consult: missing dependency {exc.name!r}. "
            f"From the project root, run `python3 -m venv .venv && "
            f".venv/bin/pip install -e .` then retry — cli.py auto-detects "
            f"an adjacent ``.venv`` and re-execs under it. Original error: "
            f"{exc}"
        ) from exc
    path = repo_root / ".consultignore"
    if not path.is_file():
        return None, []
    try:
        raw_lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as e:
        return None, [
            f"ERROR: consult: failed to read .consultignore: {e}",
        ]
    kept: list[str] = []
    negation_diagnostics: list[str] = []
    for lineno, raw in enumerate(raw_lines, start=1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            kept.append(raw)
            continue
        if stripped.startswith("!"):
            negation_diagnostics.append(
                f"WARNING: consult: .consultignore:{lineno}: negation "
                f"pattern {stripped!r} stripped (R10 defer-negation-to-v2.1; "
                f"v2.0 supports positive excludes only)"
            )
            continue
        kept.append(raw)
    # Compile PathSpec only if at least one effective pattern remains.
    if not any(
        line.strip() and not line.strip().startswith("#") for line in kept
    ):
        return None, negation_diagnostics
    spec = pathspec.PathSpec.from_lines("gitwildmatch", kept)
    return spec, negation_diagnostics


def discover_visible_files(
    repo_root: Path,
) -> tuple[list[str], dict[str, list[str]], list[str]]:
    """Compute the v2.0 filtered file list relative to ``repo_root``.

    Returns ``(visible_files, stages, diagnostics)``:

    - ``visible_files`` — sorted list of relpaths after all filtering
      (== ``stages["c"]``).
    - ``stages`` — dict with keys ``"a"`` / ``"b"`` / ``"c"`` exposing
      the three R13 ``--verbose`` debug stages:
      - ``"a"`` raw ``git ls-files`` output (tracked, no exclude flag).
      - ``"b"`` post-.gitignore (``git ls-files --exclude-standard``).
      - ``"c"`` post-.consultignore (b minus pathspec matches).
    - ``diagnostics`` — non-fatal stderr-bound warnings (negation strips,
      no-git fallback notes).

    Strategy per PG-2 / R13 insight 7: rely on ``git ls-files
    --exclude-standard`` for baseline .gitignore (honors global +
    system + repo-local + nested .gitignore). Layer ``.consultignore``
    via ``pathspec`` (positive excludes only — R10 / PG-1).

    No-git fallback: enumerate via filesystem walk; ``.gitignore``
    filtering skipped (diagnostic emitted); ``.consultignore`` layer
    still applies.
    """
    diagnostics: list[str] = []
    stages: dict[str, list[str]] = {"a": [], "b": [], "c": []}

    if _is_git_repo(repo_root):
        stages["a"] = sorted(_git_ls_files(repo_root))
        stages["b"] = sorted(_git_ls_files(repo_root, "--exclude-standard"))
    else:
        diagnostics.append(
            f"WARNING: consult: {repo_root} is not a git repo; "
            f".gitignore filtering skipped (R3 no-git fallback). "
            f"Enumerating via filesystem walk."
        )
        all_files: list[str] = []
        for p in repo_root.rglob("*"):
            if p.is_file():
                try:
                    rel = str(p.relative_to(repo_root))
                except ValueError:
                    continue
                all_files.append(rel)
        stages["a"] = sorted(all_files)
        stages["b"] = sorted(all_files)

    spec, neg_diag = _read_consultignore(repo_root)
    diagnostics.extend(neg_diag)
    if spec is None:
        stages["c"] = list(stages["b"])
    else:
        stages["c"] = sorted(
            p for p in stages["b"] if not spec.match_file(p)
        )

    return stages["c"], stages, diagnostics


def estimate_token_count(text: str) -> int:
    """R13 estimation: byte-count of UTF-8 encoding // 4 (rough
    char-to-token ratio for English/code; documented approximation,
    NOT exact tokenization).
    """
    return len(text.encode("utf-8")) // 4


def estimate_files_payload(repo_root: Path, files: list[str]) -> int:
    """Sum on-disk byte size of ``files`` (relative to ``repo_root``).

    Files that fail to stat are skipped (HR-#3 never-silent: caller
    can compare ``len(files)`` to expected count if precision matters).
    """
    total = 0
    for rel in files:
        try:
            total += (repo_root / rel).stat().st_size
        except OSError:
            continue
    return total


# ---------------------------------------------------------------------------
# R2 — Auto context_bundle from target's linked_*
# ---------------------------------------------------------------------------


def _strip_frontmatter_body(path: Path) -> str:
    """Parse + return the body only (frontmatter stripped). Errors
    propagate to caller for catch-and-skip / catch-and-strict handling.
    """
    _meta, body = _fm.parse(path)
    return (body or "").rstrip()


def _resolve_linked_entity(
    repo_root: Path, field: str, entity_id: str,
) -> Path | None:
    """Resolve a linked entity id to ``docs/<kind>/<entity_id>.md``.

    Returns the resolved Path if the file exists; None otherwise.
    """
    target_dir = _FIELD_TO_DIR.get(field)
    if target_dir is None:
        return None
    p = ledger_paths.compat_kind_dir(repo_root, target_dir) / f"{entity_id}.md"
    return p if p.is_file() else None


def build_context_bundle(
    repo_root: Path,
    target_fm: dict,
    target_id: str,
    *,
    strict: bool = False,
) -> tuple[str, list[str]]:
    """R2: walk target's forward links, resolve 1-hop, return bundle.

    Returns ``(bundle_text, diagnostics)``.

    Bundle layout (deterministic — sort by ``(kind, id)``):

        ### <kind>: <id>

        <body>

        ---

    1-hop only; no transitive expansion. Self-references to
    ``target_id`` silently skipped (R2 loop guard).

    Resolution failure disposition:
    - default (``strict=False``): emit machine-readable stderr diagnostic
      per R13 ("ERROR: consult: missing linked entity '<kind>:<id>'")
      followed by a human-readable explanation line; skip the entry.
    - ``strict=True`` (R9 --strict-context): raise
      :class:`MissingTargetStrict` at the first miss.

    Per HR-#1 parley-agnostic: ``linked_msg_ids`` is NOT auto-resolved
    (parley msg-ids live in chat.jsonl outside workshop-lite). If the
    target has non-empty ``linked_msg_ids``, a single informational
    diagnostic surfaces; operator sees msg-id list in the target body's
    frontmatter section of the prompt.
    """
    diagnostics: list[str] = []

    msg_ids = target_fm.get("linked_msg_ids")
    if isinstance(msg_ids, list) and msg_ids:
        diagnostics.append(
            f"INFO: consult: target has {len(msg_ids)} linked_msg_ids "
            f"entries; v2.0 does NOT auto-resolve parley msg-ids into "
            f"the context bundle (HR-#1 parley-agnostic at the lib "
            f"layer). The msg-id list remains visible to the persona "
            f"in the target frontmatter."
        )

    entries: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str]] = set()
    for field in sorted(_FIELD_TO_DIR.keys()):
        kind = _FIELD_TO_KIND_LABEL[field]
        raw = target_fm.get(field)
        if not raw:
            continue
        if not isinstance(raw, list):
            continue
        for entry in raw:
            if not isinstance(entry, str) or not entry:
                continue
            # R2 self-reference loop guard.
            if entry == target_id:
                continue
            key = (kind, entry)
            if key in seen:
                continue
            seen.add(key)
            entries.append((kind, entry, field))

    # Deterministic order: by kind alphabetically, then by id
    # chronologically (lexicographic on the YYYY-MM-DD-NN- prefix
    # satisfies both for workshop-lite ids; ascending order).
    entries.sort(key=lambda e: (e[0], e[1]))

    parts: list[str] = []
    for kind, entry_id, field in entries:
        path = _resolve_linked_entity(repo_root, field, entry_id)
        if path is None:
            target_dir = _FIELD_TO_DIR[field]
            diagnostics.append(
                f"ERROR: consult: missing linked entity "
                f"'{kind}:{entry_id}'\n"
                f"  (target's {field} references {entry_id!r} but no "
                f"file at docs/{target_dir}/{entry_id}.md; "
                + (
                    "--strict-context: aborting per R9)"
                    if strict
                    else "skipping per R2 warn-and-skip; pass "
                         "--strict-context to fail fast)"
                )
            )
            if strict:
                raise MissingTargetStrict(kind, entry_id, field)
            continue
        try:
            body = _strip_frontmatter_body(path)
        except Exception as e:
            diagnostics.append(
                f"ERROR: consult: failed to parse linked entity "
                f"'{kind}:{entry_id}': {e}"
            )
            if strict:
                raise
            continue
        parts.append(f"### {kind}: {entry_id}\n\n{body}\n\n---")

    if not parts:
        return "", diagnostics
    return "\n\n".join(parts) + "\n", diagnostics
