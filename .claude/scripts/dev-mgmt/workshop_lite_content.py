"""Workshop-Lite substrate-emission helpers (WL.30 D2).

Backs the ``wl install-workshop-lite-content`` CLI verb. Propagates
the workshop-lite substrate content set into a non-parley consumer
repository (ccweb, maxai, future consumers) so they get the WL
helper lib + skills + hooks + conventions + templates + bin/ entry
shims as first-class participants.

Two file-classes per chunk-0 [drift-policy PG] (DA M-1 amendment in
charter §2 D2 + chunk-0 ratify msg-d91261e535ed):

  - **CLASS-A (whole-file artifacts)**: ``.py`` helper-lib modules,
    skill dir contents (``SKILL.md`` + sidecar files), ``.sh`` + ``.py``
    hook scripts, convention ``.md`` files, template ``.md`` files,
    ``bin/`` entry-point shims. File-level drift-detect: if target
    bytes differ from source, REFUSE without ``--accept-drift``; with
    ``--accept-drift``, OVERWRITE.
  - **CLASS-B (consumer-customizable marker-delimited)**:
    ``.claude/settings.json`` hook entries (each ``workshop-lite-*``
    named entry merged idempotently per HR #3 prefix discipline;
    non-prefixed entries untouched); ``CLAUDE.md`` fragment wrapped
    in ``<!-- workshop-lite-start -->`` / ``<!-- workshop-lite-end -->``
    markers per WL.29 AGENTS.md precedent. Outside-marker content
    NEVER touched.

No FROM-workshop-lite header on whole-file artifacts (defeats
idempotency goal — see chunk-0 [drift-policy PG] resolution).

HR #1 (parley-agnostic at base) holds: this module never imports or
shells out to parley. The parley-coupled hooks (``parley-unread.sh``,
``sync_from_parley_hook.py``) propagate as CLASS-A whole files but
are NOT auto-registered in the target settings.json — consumer opts
in by hand.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path


# ---------------------------------------------------------------------------
# Source-root resolution (PG-1.1 — new helper per chunk-0 forensic; charter
# §6 cited a WL.29 _resolve_workshop_lite_root that does not exist).
# ---------------------------------------------------------------------------


def resolve_workshop_lite_source_root(
    *, here: Path | None = None,
) -> Path | None:
    """Walk from ``here`` (default ``__file__``) upward looking for the
    workshop-lite repo root.

    Stop conditions (in order):

    - candidate has ``.claude/scripts/dev-mgmt/`` AND ``bin/wl`` AND
      ``docs/conventions/`` → it's a workshop-lite repo root; return it.
    - candidate has ``pyproject.toml`` or ``.git`` → root anchor reached;
      stop search (return None — caller must pass ``--source``).

    Mirrors the ``_find_project_venv_python`` walking-discipline in
    ``cli.py`` (bounded walk; no leaking past root anchors).
    """
    here = (here or Path(__file__).resolve()).resolve()
    for d in (here.parent, *here.parent.parents):
        # Workshop-lite-substrate-root signature: three load-bearing
        # path-witnesses must all be present.
        if (
            (d / ".claude" / "scripts" / "dev-mgmt").is_dir()
            and (d / "bin" / "wl").is_file()
            and (d / "docs" / "conventions").is_dir()
        ):
            return d
        # Root-anchor stop: don't leak past pyproject/.git boundary.
        if (d / "pyproject.toml").is_file():
            break
        if (d / ".git").exists():
            break
    return None


# ---------------------------------------------------------------------------
# CLASS-A whole-file discovery (PG-2.1 dynamic discovery; PG-2.3 bin/ added).
#
# Each entry: (source_relative_subtree, file_filter, recursive)
# - source_relative_subtree: rel path under wl source root
# - file_filter: callable(Path) -> bool deciding which files to include
# - recursive: True walks subdirs; False is iterdir-only
# ---------------------------------------------------------------------------


def _is_devmgmt_lib_file(p: Path) -> bool:
    """``.claude/scripts/dev-mgmt/`` files we propagate.

    Includes ``.py`` modules + ``.txt`` (requirements-workshop-lite.txt).
    Excludes ``__pycache__/`` artifacts.
    """
    if not p.is_file():
        return False
    if "__pycache__" in p.parts:
        return False
    return p.suffix in {".py", ".txt"}


def _is_skill_file(p: Path) -> bool:
    """``.claude/skills/<name>/`` files we propagate.

    Includes any regular file under a skill dir (SKILL.md + sidecars).
    Excludes hidden files (``.DS_Store`` etc.) + ``__pycache__/``.
    """
    if not p.is_file():
        return False
    if any(part.startswith(".") for part in p.parts[-1:]):
        return False
    if "__pycache__" in p.parts:
        return False
    return True


def _is_hook_file(p: Path) -> bool:
    """``.claude/hooks/`` files we propagate.

    Includes ``.sh`` shell hooks + ``.py`` python sidecars.
    """
    if not p.is_file():
        return False
    if "__pycache__" in p.parts:
        return False
    return p.suffix in {".sh", ".py"}


def _is_markdown_file(p: Path) -> bool:
    """``docs/conventions/`` + ``docs/.templates/`` files we propagate.

    Includes ``.md`` files only.
    """
    if not p.is_file():
        return False
    return p.suffix == ".md"


def _is_bin_file(p: Path) -> bool:
    """``bin/`` entry-point shims we propagate.

    Includes any regular file (these are executable shell scripts +
    occasional .py wrappers).
    """
    if not p.is_file():
        return False
    return True


# CLASS-A discovery spec — each entry produces (rel_path, source_path)
# tuples via dynamic discovery. Order is deterministic via sorted().
CLASS_A_DISCOVERY: list[tuple[str, str, bool]] = [
    # (kind-tag, relative-subtree, recursive)
    ("dev-mgmt-lib",    ".claude/scripts/dev-mgmt", True),
    ("skill",           ".claude/skills",            True),
    ("hook",            ".claude/hooks",             False),
    ("convention",      "docs/conventions",          False),
    ("template",        "docs/.templates",           False),
    ("bin",             "bin",                       False),
]

# Per-kind file-filter dispatch.
_KIND_FILTER = {
    "dev-mgmt-lib":    _is_devmgmt_lib_file,
    "skill":           _is_skill_file,
    "hook":            _is_hook_file,
    "convention":      _is_markdown_file,
    "template":        _is_markdown_file,
    "bin":             _is_bin_file,
}


# WL.31 D1 ownership split. Ordered first-match-wins path rules over the
# source-relative POSIX path; files not listed here are WL-canonical mirrors.
OWNERSHIP_MIRROR = "mirror"
OWNERSHIP_CONSUMER_OWNED = "consumer_owned"
OWNERSHIP_RULES: list[tuple[str, str]] = [
    ("docs/conventions/INDEX.md", OWNERSHIP_CONSUMER_OWNED),
    (".claude/skills/parley/", OWNERSHIP_CONSUMER_OWNED),
    # The .codex mirror of the consumer-owned parley skill is likewise
    # consumer-owned: parley's own installer ships .codex/skills/parley
    # (_write_codex_skill); the dev-mgmt bundle must not fight it. Noop if
    # present, never drift-refuse/overwrite.
    (".codex/skills/parley/", OWNERSHIP_CONSUMER_OWNED),
]


def ownership_for_path(rel_path: str | Path) -> str:
    """Return the ownership class for a source-relative path.

    Rules are path-scoped, ordered, and first-match-wins. Default
    ``mirror`` is safe because discovery walks the WL source tree only;
    target-local novel files never enter the sync plan.
    """
    rel_s = Path(rel_path).as_posix()
    for pattern, ownership in OWNERSHIP_RULES:
        if pattern.endswith("/"):
            if rel_s.startswith(pattern):
                return ownership
            continue
        if rel_s == pattern:
            return ownership
    return OWNERSHIP_MIRROR


def discover_class_a_files(source: Path) -> list[tuple[str, Path, Path]]:
    """Walk the source tree per ``CLASS_A_DISCOVERY`` and yield the file set.

    Returns a list of ``(kind-tag, source_path, rel_path)`` triples in
    deterministic sorted order. ``rel_path`` is relative to the source
    root (suitable to compute the target path as ``target / rel_path``).
    """
    out: list[tuple[str, Path, Path]] = []
    for kind, subtree, recursive in CLASS_A_DISCOVERY:
        root = source / subtree
        if not root.is_dir():
            # Substrate may not have every subtree (e.g., a fresh
            # workshop-lite checkout pre-cohort-PW may lack docs/.templates).
            # Skip silently — discovery is opportunistic.
            continue
        file_filter = _KIND_FILTER[kind]
        walker = root.rglob("*") if recursive else root.iterdir()
        files = [p for p in walker if file_filter(p)]
        files.sort()
        for p in files:
            rel = p.relative_to(source)
            out.append((kind, p, rel))
    return out


def discover_class_a_entries(source: Path) -> list[dict]:
    """Return Class-A entries with ownership metadata.

    This wraps the legacy tuple-returning discovery function so callers can
    migrate incrementally while the canonical ownership resolver stays in one
    module.
    """
    return [
        {
            "kind": kind,
            "source_path": src_path,
            "rel_path": rel_path,
            "ownership": ownership_for_path(rel_path),
        }
        for kind, src_path, rel_path in discover_class_a_files(source)
    ]


# ---------------------------------------------------------------------------
# Agent Skills adoption — Phase 1+2 (spec
# dev-mgmt-session/docs/cross-session/2026-06-29-agent-skills-adoption-
# implementation-spec.md §2-§3; cto v3-3186 + factoring directive v3-3228).
#
# The dev-mgmt bundle already propagates ``.claude/skills/<name>/SKILL.md``
# (CLASS-A "skill" kind). Per the spec the SAME install path must also emit
# ``.codex/skills/<name>/SKILL.md`` with a BYTE-IDENTICAL body for every
# skill in the PORTABLE SUBSET, so Codex seats autoload the same skills. The
# gap is pure distribution: ~95% of skills never reach .codex today.
#
# Factoring (cto v3-3228): the actual writer is the importable
# ``emit_codex_copy(skill_dir, repo_root)`` helper — NOT inlined in the
# bundle loop — so the bundle installer AND the Phase-4 ``/skill-port`` skill
# call the SAME writer.
# ---------------------------------------------------------------------------

SKILL_BODY_FILENAME = "SKILL.md"
CLAUDE_SKILLS_SUBTREE = ".claude/skills"
CODEX_SKILLS_SUBTREE = ".codex/skills"

# Portable-by-default allowlist (spec §3). The ~3 CC-only skills orchestrate
# Claude-Code-specific machinery (subagent spawn / parley substrate / Task
# tool) and are NOT ported to Codex. ``code-audit`` is listed defensively —
# it is not present in this repo today but is named in the spec exclusion set.
NON_PORTABLE_SKILLS: frozenset[str] = frozenset({
    "cc-vs-codex-benchmark",
    "consultant",
    "code-audit",
})

_NON_PORTABLE_REASON = (
    "CC-only — orchestrates Claude-Code-specific machinery (subagent spawn / "
    "Task tool / parley substrate); port a Codex variant only if a Codex seat "
    "needs it (spec §3)"
)


def is_portable(skill_dir: Path | str) -> tuple[bool, str | None]:
    """S2 (Phase-4 Appendix A): the portability decision for ONE skill dir.

    Default-portable allowlist: returns ``(True, None)`` for every skill
    EXCEPT the explicit CC-only exclusion set, for which it returns
    ``(False, <reason>)``. Single source of truth for "portable" — consumed
    by the dev-mgmt bundle, ``/skill-port``, and ``/skill-census`` so the
    answer is identical everywhere.
    """
    name = Path(skill_dir).name
    if name in NON_PORTABLE_SKILLS:
        return False, _NON_PORTABLE_REASON
    return True, None


def is_portable_skill(skill_name: str) -> bool:
    """Name-keyed convenience over :func:`is_portable` (bool only)."""
    return skill_name not in NON_PORTABLE_SKILLS


def portable_skill_dirs(repo_root: Path) -> list[Path]:
    """Return ``<repo_root>/.claude/skills/<name>`` dirs that are portable
    AND carry a top-level ``SKILL.md``, in deterministic sorted order.

    Only the skill dir's own ``SKILL.md`` is portable — sidecar files
    (``funnel.py``, ``personas/`` …) stay CC-side. The byte-identical
    ``SKILL.md`` body IS the spec's required portable surface; Codex autoload
    reads ``SKILL.md``.
    """
    claude_skills = repo_root / ".claude" / "skills"
    if not claude_skills.is_dir():
        return []
    out: list[Path] = []
    for skill_md in sorted(claude_skills.glob("*/SKILL.md")):
        if not skill_md.is_file():
            continue
        name = skill_md.parent.name
        if not is_portable_skill(name):
            continue
        out.append(skill_md.parent)
    return out


def plan_codex_copy(
    skill_dir: Path, repo_root: Path, *, accept_drift: bool = False,
) -> dict:
    """Pure planner for ONE skill's ``.codex/skills/<name>/SKILL.md`` copy.

    Reuses the CLASS-A ``_class_a_step`` state machine so the .codex copy
    inherits the identical create/noop/drift/symlink discipline (and exec-bit
    handling) as every other propagated artifact. The step's ``source_path``
    is the ``.claude`` ``SKILL.md``, so the planned ``new_bytes`` are
    byte-identical to the canonical body BY CONSTRUCTION. No disk write.
    """
    name = skill_dir.name
    source_md = skill_dir / SKILL_BODY_FILENAME
    rel_path = Path(CODEX_SKILLS_SUBTREE) / name / SKILL_BODY_FILENAME
    return _class_a_step(
        kind="codex-skill",
        source_path=source_md,
        rel_path=rel_path,
        ownership=ownership_for_path(rel_path),
        target=repo_root,
        accept_drift=accept_drift,
    )


def shared_skill_bytes(skill_md: Path) -> bytes:
    """S3 (Phase-4 Appendix A) — canonical ``{name, description, body}`` surface
    bytes for byte-equality across host copies.

    **Cross-repo "one definition of equal" (cto v3-3312/v3-3320).** The
    canonical contract home is ``parley/parley/skills_ref.py``. WL is
    parley-agnostic (HR #1) and parley does not import WL, so this is a
    DUPLICATE of that contract kept byte-compatible BY AGREEMENT + the Phase-4
    ``/drift-guard`` cross-check — not by a shared import. The serialization
    MUST match the canonical exactly: ``name`` + ``description`` + ``body``,
    each ``strip()``-ed, joined by a NUL (``\\x00``) delimiter. Incidental
    frontmatter formatting (block-scalar vs inline, key order, harness-only
    keys) is NOT drift; a differing name/description/body IS.

    Raises ``FileNotFoundError`` (absent) / ``ValueError`` (malformed
    frontmatter) — a loud failure at gate time beats a falsely-equal surface,
    matching the canonical. NB: the WL install-time assert
    (:func:`find_skill_body_inequalities`) deliberately uses RAW bytes, not
    this surface, so it never depends on frontmatter parsing; this helper is
    for the cross-repo ``/drift-guard`` definition.

    The ``frontmatter`` helper is imported lazily (HR #1: parley-agnostic).
    """
    import frontmatter as _frontmatter

    skill_md = Path(skill_md)
    if not skill_md.is_file():
        raise FileNotFoundError(f"SKILL.md not found: {skill_md}")
    meta, body = _frontmatter.parse(skill_md)
    name = str((meta or {}).get("name", "")).strip()
    description = str((meta or {}).get("description", "")).strip()
    surface = "\x00".join((name, description, body.strip()))
    return surface.encode("utf-8")


def emit_codex_copy(skill_dir: Path, repo_root: Path) -> Path:
    """S1 (Phase-4 Appendix A contract; cto v3-3228) — THE single ``.codex``
    skill writer. **One writer, two callers.**

    Writes ``<repo_root>/.codex/skills/<name>/SKILL.md`` byte-identical to
    ``<skill_dir>/SKILL.md`` and returns the destination ``Path``. Called by
    the dev-mgmt bundle installer loop (for every portable skill) AND the
    Phase-4 ``/skill-port`` skill (for one skill) — exactly one writer, so a
    resync and a port are the same operation.

    ``skill_dir`` is a ``.claude/skills/<name>`` directory (source of truth);
    ``repo_root`` is the repo whose ``.codex/skills`` receives the copy (the
    consumer target for the bundle; the same repo for /skill-port).

    This is an unconditional resync writer: it overwrites any existing dest
    with the canonical body (``/drift-guard`` / ``/skill-port`` own the
    "don't clobber differing content without --force" policy; the bundle
    gates drift earlier via :func:`plan_codex_copy`). It REFUSES to write
    through a symlinked destination (boundary guard, parity with CLASS-A) and
    asserts the post-write copy is BYTE-IDENTICAL to the source (cto
    deliverable 2 / spec §2 — a raw-byte guarantee, never frontmatter-parse-
    dependent, so it cannot crash on a skill whose YAML is unconventional).
    """
    name = skill_dir.name
    source_md = skill_dir / SKILL_BODY_FILENAME
    dest = repo_root / ".codex" / "skills" / name / SKILL_BODY_FILENAME

    violates, reason = _violates_symlink_boundary(dest, repo_root)
    if violates:
        raise ValueError(
            f"emit_codex_copy: refusing symlinked destination for skill "
            f"'{name}': {reason}"
        )

    source_bytes = source_md.read_bytes()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(source_bytes)

    if dest.read_bytes() != source_bytes:
        raise AssertionError(
            f"emit_codex_copy: post-write byte-equality assertion FAILED for "
            f"skill '{name}': {dest} != {source_md}"
        )
    return dest


def find_skill_body_inequalities(repo_root: Path) -> list[dict]:
    """Install-time byte-equality assertion (spec §2 Phase-2.3 / acceptance
    §5.2) over an INSTALLED repo.

    For every PORTED (mirror-owned, portable) skill present at
    ``.codex/skills/<name>/SKILL.md``, assert its bytes equal the in-repo
    ``.claude/skills/<name>/SKILL.md`` bytes. Compares the two copies that
    coexist in the same repo via RAW bytes (cto deliverable 2/4:
    "byte-identical SKILL.md content") — robust, never frontmatter-parse-
    dependent. This is the ``.claude``-vs-``.codex`` drift class that
    ``skills-ref validate`` cannot see (both copies individually spec-legal
    yet differing).

    Returns a list of mismatch dicts (empty == all ported copies byte-equal)::

        {skill, reason, codex_path, claude_path}

    ``reason`` ∈ {``body-byte-mismatch``, ``codex-skill-without-claude-body``}.
    SKIPPED: non-portable skills (no .codex copy expected) AND consumer-owned
    skills (e.g. ``parley`` — the consumer may legitimately diverge from
    upstream; the bundle does not port/manage those bodies).
    """
    codex_root = repo_root / ".codex" / "skills"
    if not codex_root.is_dir():
        return []
    claude_root = repo_root / ".claude" / "skills"
    mismatches: list[dict] = []
    for codex_md in sorted(codex_root.glob("*/SKILL.md")):
        name = codex_md.parent.name
        if not is_portable_skill(name):
            continue
        rel = Path(CODEX_SKILLS_SUBTREE) / name / SKILL_BODY_FILENAME
        if ownership_for_path(rel) == OWNERSHIP_CONSUMER_OWNED:
            continue
        claude_md = claude_root / name / SKILL_BODY_FILENAME
        if not claude_md.is_file():
            mismatches.append({
                "skill": name,
                "reason": "codex-skill-without-claude-body",
                "codex_path": codex_md,
                "claude_path": claude_md,
            })
            continue
        if codex_md.read_bytes() != claude_md.read_bytes():
            mismatches.append({
                "skill": name,
                "reason": "body-byte-mismatch",
                "codex_path": codex_md,
                "claude_path": claude_md,
            })
    return mismatches


# ---------------------------------------------------------------------------
# skills-ref validation wiring (spec §2 Phase-2.1; cto deliverable 5).
#
# skills-ref is the EXTERNAL canonical Agent Skills validator
# (github.com/agentskills/agentskills/tree/main/skills-ref) — it checks each
# SKILL.md is spec-legal (name<=64, description<=1024, frontmatter parses).
# It is NOT vendored here (spec §7: "don't build a registry"). The installer
# WIRES the call point: run it post-write when on PATH; otherwise surface the
# exact dependency gap. HR #1 holds — no parley coupling.
# ---------------------------------------------------------------------------

SKILLS_REF_DEP_GAP = (
    "skills-ref not found on PATH — the canonical Agent Skills validator "
    "(github.com/agentskills/agentskills/tree/main/skills-ref) is NOT "
    "installed locally, so SKILL.md spec-legality (name<=64, "
    "description<=1024, frontmatter parses) was NOT validated. This is a "
    "dependency gap, not an installer fault: install skills-ref onto PATH "
    "and the installer wires `skills-ref validate <skill-dir>` into the "
    "post-write step automatically. Byte-equality (the .claude-vs-.codex "
    "drift class) IS asserted independently and is unaffected by this gap."
)


def skills_ref_available() -> bool:
    """True iff the external ``skills-ref`` validator is on PATH."""
    return shutil.which("skills-ref") is not None


def skills_ref_validate(skill_md: Path) -> dict:
    """S5 (Phase-4 Appendix A): validate ONE skill via external ``skills-ref``.

    ``skill_md`` may be the ``SKILL.md`` or its containing skill dir — the
    enclosing dir is passed to ``skills-ref validate`` (the tool takes a skill
    directory). Returns a Result dict::

        {available: bool, ok: bool|None, returncode: int|None,
         output: str, gap: str|None}

    DEGRADES TO A WARN (never a hard pass) when ``skills-ref`` is absent:
    ``available=False``, ``ok=None``, ``gap=SKILLS_REF_DEP_GAP``. The caller
    surfaces the gap (cto deliverable 5); ``/skill-port`` / ``/drift-guard``
    treat ``ok is None`` as "validator unavailable", not "valid".
    """
    skill_md = Path(skill_md)
    target = skill_md.parent if skill_md.name == SKILL_BODY_FILENAME else skill_md
    if not skills_ref_available():
        return {
            "available": False,
            "ok": None,
            "returncode": None,
            "output": "",
            "gap": SKILLS_REF_DEP_GAP,
        }
    proc = subprocess.run(
        ["skills-ref", "validate", str(target)],
        capture_output=True,
        text=True,
    )
    return {
        "available": True,
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "output": (proc.stdout + proc.stderr).strip(),
        "gap": None,
    }


def run_skills_ref_validate(skill_dirs: list[Path]) -> dict:
    """Run ``skills-ref validate <dir>`` over each skill dir IF available.

    Returns a structured result (never raises on a missing tool)::

        {available: bool, gap: str|None,
         results: [{dir, returncode, output}, ...],
         failures: [<dir>, ...]}

    When ``skills-ref`` is absent, ``available`` is False, ``gap`` carries
    ``SKILLS_REF_DEP_GAP``, and ``results``/``failures`` are empty — the
    caller surfaces the gap (cto deliverable 5). When present, each non-zero
    return code lands in ``failures`` so the caller can gate the install.
    """
    if not skills_ref_available():
        return {
            "available": False,
            "gap": SKILLS_REF_DEP_GAP,
            "results": [],
            "failures": [],
        }
    results: list[dict] = []
    failures: list[Path] = []
    for d in skill_dirs:
        res = skills_ref_validate(d)  # delegate to the S5 singular helper
        results.append({
            "dir": d,
            "returncode": res["returncode"],
            "output": res["output"],
        })
        if not res["ok"]:
            failures.append(d)
    return {
        "available": True,
        "gap": None,
        "results": results,
        "failures": failures,
    }


# ---------------------------------------------------------------------------
# CLASS-B (1) — settings.json hook-entry merge
#
# Source hooks: SessionStart, PreCompact, PostCompact, Stop — each with a
# single ``workshop-lite-*`` named entry pointing at .claude/hooks/<file>.sh.
# Merge discipline: each target settings.json event-list keeps its
# non-workshop-lite-* entries; the workshop-lite-* entry is replaced (or
# inserted) with the source canonical version. HR #3 marker-prefix.
# ---------------------------------------------------------------------------


def _load_source_workshop_lite_hooks(source: Path) -> dict:
    """Read the WL source settings.json + return the ``hooks`` dict.

    Returns an empty dict if the file is absent (rare; source-root
    detection should have caught this).
    """
    src = source / ".claude" / "settings.json"
    if not src.is_file():
        return {}
    try:
        data = json.loads(src.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data.get("hooks", {}) or {}


def _filter_workshop_lite_entries(event_list: list) -> list:
    """Return the workshop-lite-* prefixed entries within an event-list."""
    return [
        e for e in event_list
        if isinstance(e, dict)
        and isinstance(e.get("name"), str)
        and e["name"].startswith("workshop-lite-")
    ]


def _filter_non_workshop_lite_entries(event_list: list) -> list:
    """Return entries that are NOT workshop-lite-* prefixed (consumer-owned)."""
    return [
        e for e in event_list
        if not (
            isinstance(e, dict)
            and isinstance(e.get("name"), str)
            and e["name"].startswith("workshop-lite-")
        )
    ]


def compute_settings_json_merge(
    existing_text: str | None, source_hooks: dict,
) -> tuple[str, str]:
    """Compute the desired settings.json text + action.

    State machine:

    - ``existing_text is None`` (file absent) → action=``create-file``,
      text = JSON object with only the workshop-lite-* hook block.
    - existing has no workshop-lite-* entries AND source has no entries →
      action=``noop``.
    - existing's workshop-lite-* entries match source canonical exactly →
      action=``noop``.
    - otherwise → action=``merge-hooks``, text = existing with each
      event's workshop-lite-* entries replaced by source canonical
      while preserving non-workshop-lite-* entries.

    Source workshop-lite-* entries become canonical: any existing
    workshop-lite-* entry in target is REPLACED. Non-workshop-lite-*
    entries (consumer-owned hooks like SDLC-tool-hooks) are PRESERVED.
    """
    if not source_hooks:
        # No source hooks to propagate — odd but treat as noop.
        if existing_text is None:
            return "", "noop"
        return existing_text, "noop"

    # Build the workshop-lite-* entry sets per event from source.
    source_wl_entries: dict[str, list] = {}
    for event, entries in source_hooks.items():
        if not isinstance(entries, list):
            continue
        wl = _filter_workshop_lite_entries(entries)
        if wl:
            source_wl_entries[event] = wl

    if existing_text is None or not existing_text.strip():
        merged_hooks: dict = {}
        for event, wl in source_wl_entries.items():
            merged_hooks[event] = wl
        new_obj = {"hooks": merged_hooks}
        new_text = json.dumps(new_obj, indent=2) + "\n"
        return new_text, "create-file"

    # Parse existing.
    try:
        existing_obj = json.loads(existing_text)
    except json.JSONDecodeError:
        # Refuse to overwrite a non-JSON file silently — caller treats
        # this as drift (handled by the planner via byte-compare). Here
        # we return a no-op + a sentinel action the caller can detect.
        return existing_text, "skip-malformed"

    if not isinstance(existing_obj, dict):
        return existing_text, "skip-malformed"

    existing_hooks = existing_obj.get("hooks", {})
    if not isinstance(existing_hooks, dict):
        existing_hooks = {}

    # Build target hooks by event: non-WL entries preserved, WL entries
    # replaced with source canonical.
    target_hooks: dict[str, list] = {}
    all_events = set(existing_hooks.keys()) | set(source_wl_entries.keys())
    for event in sorted(all_events):
        existing_list = existing_hooks.get(event) or []
        if not isinstance(existing_list, list):
            existing_list = []
        non_wl = _filter_non_workshop_lite_entries(existing_list)
        source_wl = source_wl_entries.get(event, [])
        # Source-canonical workshop-lite-* entries come first; consumer
        # non-workshop-lite-* entries follow (stable order preservation).
        target_hooks[event] = source_wl + non_wl

    # Detect noop: existing equals proposed (event-by-event ordered compare).
    if existing_hooks == target_hooks:
        return existing_text, "noop"

    new_obj = dict(existing_obj)
    new_obj["hooks"] = target_hooks
    new_text = json.dumps(new_obj, indent=2) + "\n"
    return new_text, "merge-hooks"


# ---------------------------------------------------------------------------
# CLASS-B (2) — CLAUDE.md fragment (workshop-lite-marker-delimited)
#
# Per chunk-0 PG-2.5 disposition: gates-paragraph + HALT.md-paragraph
# (from source CLAUDE.md "Cross-session gates and HALT.md" section) +
# a Reference subsection pointing at target's docs/design + conventions.
# Markers per WL.29 AGENTS.md precedent.
# ---------------------------------------------------------------------------


CLAUDE_MD_MARKER_START = "<!-- workshop-lite-start -->"
CLAUDE_MD_MARKER_END = "<!-- workshop-lite-end -->"


CLAUDE_MD_FRAGMENT_BODY = """## Workshop-Lite substrate

This repository carries the workshop-lite dev-management substrate
(`.claude/scripts/dev-mgmt/` helper lib + `.claude/skills/` skills +
`.claude/hooks/` hooks + `docs/conventions/` Tier-1 rules +
`docs/.templates/` entity templates + `bin/` entry-point shims).
Refreshed via `wl install-workshop-lite-content --target <this-repo>`.

### Cross-session gates and HALT.md

**Cross-session gates.** Before any non-trivial work (LAND, push,
schema change, cross-repo substrate sync, etc.) check `docs/gates/`.
If any gate has `status: open`, respect its `what_you_cannot_do`
list. Surface to the value in `gated_by:` if you need to override or
believe the gate is stale. If a gate is past its `ttl_until` and you
can't reach the gater, surface to your operator. Discovery is by-
convention only — the substrate does not auto-enforce; the discipline
is yours. See `docs/design/LIGHTWEIGHT-DEV-MGMT-SYSTEM.md` §6 for the
schema.

**HALT.md.** If you reach a state where you cannot make progress — an
unresolvable gate, an environment you can't fix, a recurring failure
you can't diagnose, ambiguous scope you can't disambiguate — write a
top-level `HALT.md` describing your state (using the frontmatter shape
in `docs/.templates/halt.md`), print
`HALT.md WRITTEN - AGENT HALTED, NEEDS OPERATOR` to stdout, and STOP.
Do not retry. Do not loop. Wait until either (a) the `HALT.md` file
is deleted, or (b) an operator types "continue" in your pane.

### Reference

- Comprehensive design: `docs/design/LIGHTWEIGHT-DEV-MGMT-SYSTEM.md`
  (refreshed from the workshop-lite upstream as needed)
- Tier-1 conventions index: `docs/conventions/INDEX.md`
- Entity templates: `docs/.templates/`
- Bootstrap deps: `pip install -r .claude/scripts/dev-mgmt/requirements-workshop-lite.txt`
"""


def render_claude_md_fragment() -> str:
    """Return the canonical workshop-lite CLAUDE.md fragment bracketed by
    HR #3 ``workshop-lite-*`` markers.
    """
    return (
        f"{CLAUDE_MD_MARKER_START}\n\n"
        f"{CLAUDE_MD_FRAGMENT_BODY.rstrip()}\n\n"
        f"{CLAUDE_MD_MARKER_END}\n"
    )


def compute_claude_md_update(
    existing_text: str | None,
) -> tuple[str, str]:
    """Compute the desired ``CLAUDE.md`` text + action.

    State machine (mirrors WL.29 ``_install_agents_md``):

    - file absent → action=``create-file``, text = marker section only.
    - file present, markers absent → action=``append-section``, text =
      existing + blank line + marker section.
    - file present, markers present, content matches canonical → action=
      ``noop``, text = existing.
    - file present, markers present, content differs → action=
      ``refresh-section``, text = existing with marker section replaced.

    Outside-marker content is NEVER touched.
    """
    canonical_section = render_claude_md_fragment()

    if existing_text is None:
        return canonical_section, "create-file"

    start_idx = existing_text.find(CLAUDE_MD_MARKER_START)
    end_idx = existing_text.find(CLAUDE_MD_MARKER_END)

    if start_idx == -1 or end_idx == -1 or end_idx < start_idx:
        sep = "" if existing_text.endswith("\n") else "\n"
        return (
            existing_text + sep + "\n" + canonical_section,
            "append-section",
        )

    section_end = end_idx + len(CLAUDE_MD_MARKER_END)
    if section_end < len(existing_text) and existing_text[section_end] == "\n":
        section_end += 1
    existing_section = existing_text[start_idx:section_end]

    if existing_section == canonical_section:
        return existing_text, "noop"

    new_text = (
        existing_text[:start_idx]
        + canonical_section
        + existing_text[section_end:]
    )
    return new_text, "refresh-section"


# ---------------------------------------------------------------------------
# Plan / apply orchestrator
# ---------------------------------------------------------------------------


def _violates_symlink_boundary(
    target_path: Path, target_root: Path,
) -> tuple[bool, str | None]:
    """Boundary guard for symlinks at any path component (verifier 2nd-amend
    N2 + N3): refuses both file-level symlinks AND parent-dir symlinks
    AND chains whose resolve() escapes the target root.

    Returns ``(violates, reason)`` where ``reason`` is a human-readable
    description of the offending component (suitable for stderr).

    Two checks (both → refuse):

    1. **Symlink at any ancestor** — walk from ``target_path`` upward to
       ``target_root``; if any component is a symlink, refuse. This
       catches the N2 parent-dir symlink case (``<target>/.claude`` as
       a symlink: child files report ``is_symlink()=False`` because the
       child IS a regular file at the resolved location, but a write
       through the parent symlink materializes / mutates content the
       operator did not intend to touch).
    2. **Resolved path escapes target** — defense-in-depth against
       resolve-outside via symlink-chain or path-traversal patterns.
       ``target_path.resolve(strict=False).relative_to(target_root)``
       → ``ValueError`` means resolved location is outside.

    The 2 checks overlap (most symlink-to-outside cases trip both), but
    each catches edge cases the other misses (in-tree symlinks: only
    check #1; resolve-outside without explicit symlink leaves: only
    check #2).
    """
    target_root_resolved = target_root.resolve()
    cur = target_path
    while True:
        if cur.is_symlink():
            try:
                link_target = str(cur.readlink())
            except OSError:
                link_target = "?"
            return True, f"symlink at {cur} -> {link_target}"
        if cur == target_root or cur == target_root_resolved:
            break
        if cur.parent == cur:
            break
        cur = cur.parent
    try:
        target_path.resolve(strict=False).relative_to(target_root_resolved)
    except ValueError:
        return True, (
            f"resolved path escapes target: "
            f"{target_path.resolve(strict=False)}"
        )
    return False, None


def _class_a_step(
    *,
    kind: str,
    source_path: Path,
    rel_path: Path,
    ownership: str,
    target: Path,
    accept_drift: bool,
) -> dict:
    """Build one CLASS-A plan step from a (kind, source, rel) triple.

    Action labels:

      - ``create-file`` — target missing; emit source bytes.
      - ``noop`` — target matches source bytes; no write.
      - ``noop`` — ``consumer_owned`` target exists; no diff/refuse/
        overwrite, even with ``--accept-drift``.
      - ``drift-refuse`` — target differs and ``--accept-drift`` NOT set;
        caller surfaces + non-zero exits unless --dry-run.
      - ``overwrite-drift`` — target differs and ``--accept-drift`` set;
        target bytes get replaced.
      - ``symlink-refuse`` — target path IS a symlink (per verifier
        verdict msg-439e042b1b10 axes S1+S2): broken symlinks would
        materialize a file at the resolved-but-missing destination
        outside the worktree; resolving symlinks would write through
        to the destination on overwrite-drift. Either way the write
        escapes the worktree boundary. Refuse + surface; operator
        unlinks first to make intent explicit.
    """
    target_path = target / rel_path
    source_bytes = source_path.read_bytes()
    source_is_exec = source_path.stat().st_mode & 0o111 != 0
    if ownership == OWNERSHIP_CONSUMER_OWNED and (
        target_path.exists() or target_path.is_symlink()
    ):
        return {
            "kind": f"class-a:{kind}:{rel_path.as_posix()}",
            "source_path": source_path,
            "target_path": target_path,
            "action": "noop",
            "ownership": ownership,
            "new_bytes": None,
            "exec": source_is_exec,
            "drift_detected": False,
        }
    # Symlink boundary guard (verifier M16/M18 + N2 parent-dir bypass).
    # Lifted to resolved-path-ancestor check via
    # _violates_symlink_boundary — catches leaf symlink (S1/S2), parent-
    # dir symlink (N2), and resolve-escapes-target chains in one helper.
    violates, reason = _violates_symlink_boundary(target_path, target)
    if violates:
        return {
            "kind": f"class-a:{kind}:{rel_path.as_posix()}",
            "source_path": source_path,
            "target_path": target_path,
            "action": "symlink-refuse",
            "ownership": ownership,
            "new_bytes": None,
            "exec": source_is_exec,
            "drift_detected": False,
            "symlink_reason": reason,
        }
    if not target_path.exists():
        return {
            "kind": f"class-a:{kind}:{rel_path.as_posix()}",
            "source_path": source_path,
            "target_path": target_path,
            "action": "create-file",
            "ownership": ownership,
            "new_bytes": source_bytes,
            "exec": source_is_exec,
            "drift_detected": False,
        }
    target_bytes = target_path.read_bytes()
    if target_bytes == source_bytes:
        return {
            "kind": f"class-a:{kind}:{rel_path.as_posix()}",
            "source_path": source_path,
            "target_path": target_path,
            "action": "noop",
            "ownership": ownership,
            "new_bytes": None,
            "exec": source_is_exec,
            "drift_detected": False,
        }
    if accept_drift:
        action = "overwrite-drift"
        new_bytes = source_bytes
    else:
        action = "drift-refuse"
        new_bytes = None
    return {
        "kind": f"class-a:{kind}:{rel_path.as_posix()}",
        "source_path": source_path,
        "target_path": target_path,
        "action": action,
        "ownership": ownership,
        "new_bytes": new_bytes,
        "exec": source_is_exec,
        "drift_detected": True,
    }


def plan_install(
    target: Path,
    *,
    source: Path,
    accept_drift: bool = False,
) -> list[dict]:
    """Plan all install-workshop-lite-content steps. Returns a list of
    step dicts in execution order.

    Step kinds:

    - ``class-a:<kind>:<rel-path>`` — whole-file artifact (helper-lib,
      skill, hook, convention, template, bin).
    - ``class-b:settings.json`` — settings.json workshop-lite-* hook
      entries merge.
    - ``class-b:CLAUDE.md`` — CLAUDE.md marker-delimited fragment.

    Each step has keys: ``kind``, ``source_path`` (CLASS-A only),
    ``target_path``, ``action``, ``new_bytes`` (CLASS-A) or
    ``new_text`` (CLASS-B), and ``drift_detected`` (CLASS-A).

    ``accept_drift`` toggles between ``drift-refuse`` (default — safe)
    and ``overwrite-drift`` (operator-acknowledged destructive) for
    CLASS-A artifacts. CLASS-B drift is inside-marker-only; outside-
    marker content is always preserved, so the flag does not apply.
    """
    target = target.resolve()
    source = source.resolve()
    plan: list[dict] = []

    # CLASS-A: whole-file artifacts via dynamic discovery.
    for entry in discover_class_a_entries(source):
        plan.append(
            _class_a_step(
                kind=entry["kind"],
                source_path=entry["source_path"],
                rel_path=entry["rel_path"],
                ownership=entry["ownership"],
                target=target,
                accept_drift=accept_drift,
            )
        )

    # CLASS-B step 1: settings.json hook-entry merge.
    # Verifier 2nd-amend N3a: symlink guard MUST also cover CLASS-B
    # paths. Run the same _violates_symlink_boundary check; refuse via
    # the symlink-refuse action that plan_has_blocking_symlinks already
    # surfaces.
    target_settings = target / ".claude" / "settings.json"
    settings_violates, settings_reason = _violates_symlink_boundary(
        target_settings, target,
    )
    if settings_violates:
        plan.append({
            "kind": "class-b:settings.json",
            "target_path": target_settings,
            "action": "symlink-refuse",
            "new_text": None,
            "drift_detected": False,
            "symlink_reason": settings_reason,
        })
    else:
        existing_settings = (
            target_settings.read_text(encoding="utf-8")
            if target_settings.is_file() else None
        )
        source_hooks = _load_source_workshop_lite_hooks(source)
        settings_text, settings_action = compute_settings_json_merge(
            existing_settings, source_hooks,
        )
        plan.append({
            "kind": "class-b:settings.json",
            "target_path": target_settings,
            "action": settings_action,
            "new_text": (
                None if settings_action in {"noop", "skip-malformed"}
                else settings_text
            ),
            "drift_detected": False,
        })

    # CLASS-B step 2: CLAUDE.md fragment.
    # Verifier 2nd-amend N3b: same symlink guard.
    target_claude_md = target / "CLAUDE.md"
    claude_violates, claude_reason = _violates_symlink_boundary(
        target_claude_md, target,
    )
    if claude_violates:
        plan.append({
            "kind": "class-b:CLAUDE.md",
            "target_path": target_claude_md,
            "action": "symlink-refuse",
            "new_text": None,
            "drift_detected": False,
            "symlink_reason": claude_reason,
        })
    else:
        existing_claude = (
            target_claude_md.read_text(encoding="utf-8")
            if target_claude_md.is_file() else None
        )
        claude_text, claude_action = compute_claude_md_update(existing_claude)
        plan.append({
            "kind": "class-b:CLAUDE.md",
            "target_path": target_claude_md,
            "action": claude_action,
            "new_text": None if claude_action == "noop" else claude_text,
            "drift_detected": False,
        })

    return plan


def apply_install_step(step: dict) -> None:
    """Apply a single planned step to disk.

    Skips noop + drift-refuse + symlink-refuse + skip-malformed steps.
    Creates parent directories as needed; preserves exec bits for
    CLASS-A files whose source had the exec bit set.

    ``drift-refuse`` and ``symlink-refuse`` steps are NEVER applied to
    disk — the caller is responsible for surfacing + exiting non-zero.
    ``overwrite-drift`` DOES apply (operator opted in via
    --accept-drift); the symlink guard takes precedence over the drift
    branch so --accept-drift cannot bypass the boundary check.
    """
    action = step["action"]
    if action in {"noop", "drift-refuse", "symlink-refuse", "skip-malformed"}:
        return
    target_path: Path = step["target_path"]
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if "new_bytes" in step and step["new_bytes"] is not None:
        target_path.write_bytes(step["new_bytes"])
        if step.get("exec"):
            target_path.chmod(0o755)
    elif "new_text" in step and step["new_text"] is not None:
        target_path.write_text(step["new_text"], encoding="utf-8")


def plan_has_blocking_drift(plan: list[dict]) -> bool:
    """Return True iff the plan contains at least one ``drift-refuse``
    step (i.e., target has hand-edits and ``--accept-drift`` was NOT
    passed). Caller exits non-zero + emits per-file diff guidance.
    """
    return any(s["action"] == "drift-refuse" for s in plan)


def plan_has_blocking_symlinks(plan: list[dict]) -> bool:
    """Return True iff the plan contains at least one ``symlink-refuse``
    step (verifier M16 + M18 boundary guard). Caller exits non-zero
    regardless of --accept-drift — symlinks always refuse.
    """
    return any(s["action"] == "symlink-refuse" for s in plan)
