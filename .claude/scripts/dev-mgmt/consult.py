"""Consult-skill platform — Gemini-CLI-mediated AI fan-out with persona-as-data.

Per the binding charter at
``docs/inbox/2026-06-02-consult-skill-platform-gemini-fanout-charter.md``:
the unified ``/consult <persona-slug> <target>`` skill loads a persona
from ``personas/<slug>.md`` (with repo-overlay precedence), assembles a
prompt from persona + target + cross-linked context, shells out to
``gemini -p`` for heterogeneous-model review/collaboration, parses the
JSON envelope, and lands a Review entity per the persona-mediated
sub-schema (charter §2.1 + chunk-0 PG-1(a) — UNION/DISCRIMINATOR-BY-
SOURCE on ``persona_used`` field presence).

Three v1 alias skills (``/devil``, ``/collaborate``, ``/security``)
pass through to the unified ``/consult`` form. Eight default personas
ship at ``personas/<slug>.md``; per-repo overrides live at
``.workshop-lite/personas/<slug>.md`` and take precedence.

PARLEY-AGNOSTIC (CLAUDE.md Hard Rule 1): this module NEVER imports or
shells out to parley. Gemini CLI shell-out IS permitted (Hard Rule 1
constrains parley-coupling, not all shell-outs); ``parley whoami`` is
called from the skill layer for author seat derivation, never here.

GRACEFUL DEGRADATION (charter §2.4 + HR-#3 never-silent): when ``gemini``
exits non-zero / network-fails / missing-from-PATH / rate-limits / auth-
fails, :class:`GeminiUnavailable` is raised carrying the assembled
prompt. The skill layer catches this, prompts the operator Y/n,
optionally pipes the prompt to the local CC (the operator-CC), then
invokes :func:`record_consult_review` directly with the fallback
response + ``model="claude-code"`` — see ``.claude/skills/consult/SKILL.md``
for the fallback orchestration.

FORWARD-ONLY CROSS-LINK (chunk-0 PG-9 ratify): the Review carries
``target_entity_id`` (charter §2.1) PLUS a ``linked_<target-kind>``
forward link. The target entity is NEVER mutated; reverse projection is
served from the maintained ledger link index via
:func:`cross_links.derived_reverse_links`.

SUPERSEDE (HR-#7): :func:`supersede_review` marks the OLD review's
``status='superseded'`` + ``superseded_by=<new-id>``; the NEW review
carries ``supersedes=<old-id>`` for back-traversal. Mirrors the
dispatch supersede pattern.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import frontmatter as _fm
import ledger_paths
import validators


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_GEMINI_MODEL = "gemini-3.1-pro-preview"  # chunk-0 PG-3 ratify
DEFAULT_TIMEOUT_S = 300
DEFAULT_OWNER_USER = "user/local"
FALLBACK_MODEL = "claude-code"  # charter §2.4 Y branch model field

# wl:2026-06-05-03 PRIMARY auto-narrow heuristic (charter §4.1):
# fires when --include-dirs is unset AND token-budget estimate exceeds
# Mx the configured budget. M defaults to 2; env-overridable for
# operators tuning the trigger sensitivity.
AUTO_NARROW_THRESHOLD_MULTIPLIER_DEFAULT = 2
AUTO_NARROW_THRESHOLD_MULTIPLIER_ENV = "WL_AUTO_NARROW_THRESHOLD_MULTIPLIER"

# ---------------------------------------------------------------------------
# Antigravity (agy) backend constants (cohort R / wl:2026-06-05-06)
#
# Knowledge-parity with parley/adapters/antigravity.py — mirrored INLINE per
# CLAUDE.md HR-#1 (parley-agnostic at lib layer; consult.py does NOT import
# from parley.*). Bumps to either side must be paired-PR'd; tracking-LOW for
# a shared-config refactor is filed post-LAND (canonical seam stays in the
# parley adapter; this is the WL mirror).
# ---------------------------------------------------------------------------

# canonical seam: parley/adapters/antigravity.py:_VERSION_RE
_AGY_VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:-.+)?\s*$")

# canonical seam: parley/adapters/antigravity.py:_MIN_VERSION
_AGY_MIN_VERSION: tuple[int, int, int] = (1, 0, 5)

# canonical seam: parley/adapters/antigravity.py:_VERSION_OVERRIDE_ENV
# (renamed PARLEY_ANTIGRAVITY_VERSION_OVERRIDE → WL_AGY_VERSION_OVERRIDE to
# keep WL parley-agnostic; semantics identical)
AGY_VERSION_OVERRIDE_ENV = "WL_AGY_VERSION_OVERRIDE"

# F4 amendment (cohort R devil-advocate): operator-controllable per-session
# model override. When unset AND --model not on CLI, invoke_agy omits the
# --model flag entirely and lets agy pick its built-in tenant-adapted
# default (chunk-0 forensic confirmed "Gemini 3.5 Flash (Medium)" propagates).
AGY_MODEL_ENV = "WL_AGY_MODEL"

# F2 workaround for agy 1.0.5: when fresh-HOME or expired credentials cause
# auth-fail, agy prints its error preamble (OAuth URL + auth-required text)
# to STDOUT and exits with code 0 (chunk-0 probe A confirmed). We detect
# this by matching against known agy print-mode error prefixes — ANCHORED
# AT stdout start, not anywhere in the response — to avoid false-positives
# on legitimate model responses that happen to discuss auth (per chunk-1
# devil-advocate review 2026-06-05-12 HIGH-1 finding: a prompt asking
# "What does 'You are not logged into Antigravity' mean?" would otherwise
# misfire on the model's response). A length cap layers a second guard:
# the error preamble is short (<2KB observed); a long stdout that starts
# with one of these phrases is overwhelmingly likely a real model response,
# so we let it through to parse. Tracking-LOW filed post-LAND for the
# upstream agy fix; this prefix-anchored detect is the local workaround.
_AGY_PRINT_ERROR_PREFIXES: tuple[str, ...] = (
    "Authentication required",
    "Error: authentication timed out",
    "You are not logged into Antigravity",
    "Error: not authenticated",
    "Error: not logged in",
)
_AGY_PRINT_ERROR_LENGTH_CAP = 2048

# ---------------------------------------------------------------------------
# Cohort GG fix #1 + fix #2: agy adapter improvements (charter §2.1 + §2.2)
#
# Source signals from cohort Y trial review 2026-06-05-30:
#  - Row 6 (forward-compat-checker × LIGHTWEIGHT-DEV-MGMT-SYSTEM.md @ 66KB)
#    degraded agy into "I will run...", "I will read..." shell-narration —
#    R1 + R6 axis floor violation.
#  - R6 schema-compliance aggregate gap: agy −9 vs gemini across the corpus
#    (prose around the JSON, missing required keys, wrong types).
#
# Chunking threshold derivation: cohort Y direct-CLI rows 3 / 7 / 9 / 5 / 4
# (sizes 54,874 / 18,447 / 25,776 / 14,830 / 8,362 bytes) all produced clean
# JSON; row 6 (66,022 bytes) narrated. Threshold sits below row 3 with ~9%
# margin → 50,000 bytes ≈ 12,500 tokens at 4 chars/token.
# ---------------------------------------------------------------------------

# Guardrail block prepended to every agy-bound prompt just before subprocess.
# Mitigates the row-6 shell-narration failure mode. Gemini path is NOT
# touched (cert axis A2: gemini byte-identical regression).
_AGY_PROMPT_GUARD_BLOCK = (
    "CRITICAL: produce a direct response to the target content provided "
    "below.\n"
    "Do NOT narrate tool-use intent (no \"I will run...\", "
    "\"I will read...\", \"Let me check...\").\n"
    "The target content is ALREADY PROVIDED in full — do not request "
    "additional reads or tool calls.\n"
    "Your response must be the structured JSON envelope per the "
    "output-format section."
)

# Secondary safeguard threshold for target_body chunking.
_AGY_TARGET_CHUNK_THRESHOLD_BYTES = 50_000

# Captures the deterministic "### Target body\n\n<body>\n\n## Cross-linked
# context" section produced by assemble_prompt(). Used by the chunking
# helper to extract and rewrite target_body when oversize.
_AGY_TARGET_BODY_BOUNDARY_RE = re.compile(
    r"### Target body\n\n(.*?)\n\n## Cross-linked context",
    re.DOTALL,
)

_AGY_SYNTHESIZE_INSTRUCTION = (
    "Synthesize your response across ALL target parts above; emit a "
    "single JSON envelope per the schema."
)

_PERSONA_REQUIRED_FRONTMATTER = ("slug", "mode", "default_model", "description")
_PERSONA_MODES = {"evaluative", "generative"}

# Optional persona dimensions (rec #14 persona-dims fold, issue
# 2026-06-10-05). When present in persona frontmatter they are
# enum-validated and folded into the assembled consult prompt as
# structured behavioral scaffolding. ``mode`` stays the required
# back-compat alias; dims are additive and never required. Behavioral
# FIDELITY of a dims-scaffolded persona needs an independently-supplied
# eval corpus before design-acceptance (HR-7 / evals-first) — this wave
# lands only the STRUCTURAL fold (schema + plumbing + render).
_PERSONA_REASONING = {"deductive", "empirical", "analogical"}
_PERSONA_REGISTER = {"terse", "expansive", "socratic"}
_PERSONA_CONFLICT = {"adversarial", "collaborative", "neutral"}
_PERSONA_DIMENSION_ENUMS = {
    "reasoning": _PERSONA_REASONING,
    "register": _PERSONA_REGISTER,
    "conflict": _PERSONA_CONFLICT,
}

# Mapping from target entity-type (frontmatter ``type`` field singular)
# to the plural ``linked_<kind>`` field name (per cross_links.py
# ``_FIELD_TO_KIND`` reverse). v1 covers the common flat-dir entities;
# unknown types route to no forward link (target_entity_id alone
# carries the explicit reference).
_TYPE_TO_LINKED_FIELD: dict[str, str] = {
    "decision":          "linked_decisions",
    "issue":             "linked_issues",
    "review":            "linked_reviews",
    "handoff":           "linked_handoffs",
    "conversation":      "linked_conversations",
    "prd":               "linked_prds",
}

# Directories searched for target resolution (flat-dir entities only;
# v1 does not resolve into per-sprint plan.md/retro.md). Order is
# stable for deterministic test behavior.
_TARGET_SEARCH_DIRS: tuple[str, ...] = (
    "docs/decisions",
    "docs/issues",
    "docs/reviews",
    "docs/handoffs",
    "docs/conversations",
    "docs/dispatches",
    "docs/wip",
    "docs/prds",
    "docs/inbox",
)


def _target_search_dir(repo: Path, rel: str) -> Path:
    """Resolve a target-search entry to its active storage directory."""
    prefix = "docs/"
    if rel.startswith(prefix):
        kind = rel[len(prefix):]
        if kind != "inbox":
            try:
                return ledger_paths.compat_kind_dir(repo, kind)
            except KeyError:
                pass
    return repo / rel


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class GeminiUnavailable(Exception):
    """Raised when the ``gemini`` subprocess fails or is unreachable.

    Carries the ``assembled_prompt`` so the caller (skill layer) can
    surface it to the operator for the Y-branch fallback (pipe to
    local CC). The ``reason`` field gives a machine-readable category
    for diagnostic display + cert assertions.

    Per HR-#3 never-silent: every failure path raises here; the skill
    layer ALWAYS surfaces the diagnostic + Y/n prompt before any
    further action.
    """

    def __init__(self, reason: str, assembled_prompt: str):
        self.reason = reason
        self.assembled_prompt = assembled_prompt
        super().__init__(reason)


class PersonaNotFound(FileNotFoundError):
    """Raised when ``<slug>`` resolves neither at the repo-overlay path
    (``.workshop-lite/personas/<slug>.md``) nor the canonical bundled
    path (``personas/<slug>.md``). Charter AXIS-5 — no silent fallback;
    the persona-resolution failure exits cleanly with a diagnostic.
    """


class TargetNotFound(FileNotFoundError):
    """Raised when the ``<target>`` entity-id does not resolve to a
    file under any of :data:`_TARGET_SEARCH_DIRS`. Caller surfaces a
    clear diagnostic naming the searched dirs.
    """


class GeminiResponseParseError(ValueError):
    """Raised when the ``gemini -o json`` envelope's ``response`` field
    cannot be parsed as JSON (the persona-prompt template instructs
    the model to emit JSON; if the model returns prose instead, parse
    fails). The caller treats this as a degradation-class failure
    and routes through the Y/n branch (charter §2.4 + PG-4 ratify
    double-parse pattern).
    """


class AgyUnavailable(Exception):
    """Raised when the ``agy`` subprocess fails or is unreachable.

    Parallel to :class:`GeminiUnavailable`; carries ``assembled_prompt``
    for the skill-layer Y/n fallback. ``reason`` is machine-readable:
    ``not-on-PATH`` / ``version-unsupported`` / ``auth-failed`` /
    ``timeout`` / ``empty-response`` / ``nonzero-exit`` etc.

    Per HR-#3 never-silent + cohort R F2 workaround: substring-detect
    on stdout for ``Authentication required`` / ``not logged in`` is
    the local workaround for agy 1.0.5's exit-code-0-on-auth-fail
    quirk (tracking-LOW filed post-LAND).
    """

    def __init__(self, reason: str, assembled_prompt: str):
        self.reason = reason
        self.assembled_prompt = assembled_prompt
        super().__init__(reason)


class AgyResponseParseError(ValueError):
    """Raised when ``agy`` stdout cannot be parsed per the persona's
    schema. Parallel to :class:`GeminiResponseParseError`.

    Differs from the gemini path: agy emits plain text (no JSON
    envelope), so this triggers when the persona-instructed
    fenced-JSON block fails to extract + parse. Caller routes through
    the same Y/n fallback (degradation-class).
    """


# ---------------------------------------------------------------------------
# Slug / id helpers (mirror prd.py / entities.py homogeneity)
# ---------------------------------------------------------------------------

_FILENAME_LIMIT = 255
_TMP_SUFFIX = ".md.tmp"
_PERSONA_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


def _slugify(text: str) -> str:
    text = (text or "").lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text or "untitled"


def _cap_slug(slug: str, prefix: str) -> str:
    budget = _FILENAME_LIMIT - len(prefix) - len(_TMP_SUFFIX)
    if budget <= 0 or len(slug) <= budget:
        return slug if len(slug) <= budget else slug[: max(budget, 0)]
    head = slug[:budget]
    cut = head.rfind("-")
    return (head[:cut] if cut > 0 else head).strip("-") or "untitled"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _iso(ts: datetime) -> str:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _next_counter(reviews_dir: Path, date_str: str) -> int:
    """Per-day NN counter for the sibling-homogeneous id shape.

    Counts both pre-charter heterogeneous entries and post-charter
    persona-mediated entries on the matching date prefix; the NN is
    monotonic per-day regardless of which sub-schema wrote them.
    """
    pattern = re.compile(rf"^{re.escape(date_str)}-(\d{{2}})-")
    max_n = 0
    if reviews_dir.exists():
        for path in reviews_dir.glob(f"{date_str}-*.md"):
            m = pattern.match(path.name)
            if m:
                max_n = max(max_n, int(m.group(1)))
    return max_n + 1


def _format_id(*, created_at: datetime, counter: int, slug: str) -> str:
    date_str = created_at.strftime("%Y-%m-%d")
    prefix = f"{date_str}-{counter:02d}-"
    return prefix + _cap_slug(slug, prefix)


# ---------------------------------------------------------------------------
# Persona resolution (charter §2.2 + AXIS-4/5/6)
# ---------------------------------------------------------------------------


def resolve_persona(repo_root: Path, slug: str) -> tuple[dict, str, Path]:
    """Resolve a persona slug to ``(frontmatter, body, path)``.

    Resolution order (charter §2.2 — no silent fallback per AXIS-5):

    1. ``<repo_root>/.workshop-lite/personas/<slug>.md`` (repo overlay)
    2. ``<repo_root>/personas/<slug>.md`` (canonical bundled)
    3. raises :class:`PersonaNotFound` with a diagnostic naming both
       searched paths.

    The persona file must carry frontmatter with the AXIS-4 required
    fields: ``slug``, ``mode``, ``default_model``, ``description``
    (+ optional ``output_schema`` for the PG-4 double-parse path).
    The body is the prompt-template markdown (frontmatter-stripped).

    Slug must match ``^[a-z0-9][a-z0-9_-]*$`` — rejects path-traversal
    attempts and surface-confusable forms.
    """
    if not isinstance(slug, str) or not _PERSONA_SLUG_RE.match(slug):
        raise ValueError(
            f"persona slug must match {_PERSONA_SLUG_RE.pattern!r}, "
            f"got: {slug!r}"
        )

    repo = Path(repo_root)
    overlay = repo / ".workshop-lite" / "personas" / f"{slug}.md"
    canonical = repo / "personas" / f"{slug}.md"

    if overlay.is_file():
        path = overlay
    elif canonical.is_file():
        path = canonical
    else:
        raise PersonaNotFound(
            f"persona {slug!r} not found at either "
            f"{overlay} (repo overlay) or {canonical} (canonical). "
            f"Run with --list-personas to discover available slugs."
        )

    fm, body = _fm.parse(path)
    _validate_persona_frontmatter(fm, path)
    return fm, body, path


def _validate_persona_frontmatter(fm: dict, path: Path) -> None:
    errors: list[str] = []
    for field in _PERSONA_REQUIRED_FRONTMATTER:
        if field not in fm:
            errors.append(f"missing required field: {field}")
        elif fm[field] in (None, ""):
            errors.append(f"required field is empty: {field}")
    mode = fm.get("mode")
    if mode is not None and mode not in _PERSONA_MODES:
        errors.append(
            f"mode must be one of {sorted(_PERSONA_MODES)}, got: {mode!r}"
        )
    for dim, allowed in _PERSONA_DIMENSION_ENUMS.items():
        val = fm.get(dim)
        if val is not None and val not in allowed:
            errors.append(
                f"{dim} must be one of {sorted(allowed)}, got: {val!r}"
            )
    if errors:
        raise validators.ValidationError(
            [f"{path}: persona frontmatter invalid — {e}" for e in errors]
        )


def extract_persona_dimensions(fm: dict) -> dict:
    """Return the present, enum-valid persona dimensions from frontmatter.

    Pulls the optional ``reasoning`` / ``register`` / ``conflict`` dims
    (issue 2026-06-10-05) into a flat ``{dim: value}`` dict, omitting
    any that are absent or fall outside their enum. Caller-side
    convenience so :func:`assemble_prompt` receives only clean dims;
    schema validation (the raising path) lives in
    :func:`_validate_persona_frontmatter`. Empty dict when no dims.
    """
    dims: dict[str, str] = {}
    for dim, allowed in _PERSONA_DIMENSION_ENUMS.items():
        val = fm.get(dim)
        if isinstance(val, str) and val in allowed:
            dims[dim] = val
    return dims


def list_personas(repo_root: Path) -> list[str]:
    """Return sorted list of persona slugs visible at this repo.

    Union of overlay + canonical paths (overlay takes precedence
    on conflict; slug only listed once). Used by the skill layer to
    answer "what personas are available here?" without invoking a
    failed lookup per slug.
    """
    repo = Path(repo_root)
    seen: set[str] = set()
    for d in (repo / ".workshop-lite" / "personas", repo / "personas"):
        if not d.is_dir():
            continue
        for p in d.glob("*.md"):
            slug = p.stem
            if _PERSONA_SLUG_RE.match(slug):
                seen.add(slug)
    return sorted(seen)


# ---------------------------------------------------------------------------
# Target resolution (charter AXIS-7 + AXIS-9 cross-link)
# ---------------------------------------------------------------------------


def resolve_target(
    repo_root: Path, target_id: str,
) -> tuple[dict, str, Path]:
    """Resolve a target entity-id to ``(frontmatter, body, path)``.

    Searches :data:`_TARGET_SEARCH_DIRS` for ``<target_id>.md`` in
    deterministic order. Raises :class:`TargetNotFound` if no match.

    v1 scope (charter §10): only flat-dir entities are resolvable.
    Per-sprint plan/retro/tasks targets deferred to v2.
    """
    if not isinstance(target_id, str) or not target_id:
        raise ValueError(
            f"target_id must be a non-empty string, got: {target_id!r}"
        )

    repo = Path(repo_root)
    for rel in _TARGET_SEARCH_DIRS:
        candidate = _target_search_dir(repo, rel) / f"{target_id}.md"
        if candidate.is_file():
            fm, body = _fm.parse(candidate)
            return fm, body, candidate

    raise TargetNotFound(
        f"target entity {target_id!r} not found under any of "
        f"{list(_TARGET_SEARCH_DIRS)}"
    )


def _target_linked_field(target_fm: dict) -> str | None:
    """Return the ``linked_<kind>`` field name for a target's entity
    type, or ``None`` if the type isn't in the v1 cross-link table.

    A None return is NOT an error — the Review still carries
    ``target_entity_id`` as the explicit reference (charter §2.1);
    the forward link is the redundant-by-construction discoverability
    layer for cross_links.py traversal.
    """
    target_type = target_fm.get("type")
    if not isinstance(target_type, str):
        return None
    return _TYPE_TO_LINKED_FIELD.get(target_type)


# ---------------------------------------------------------------------------
# Prompt assembly (charter AXIS-6 — deterministic concat)
# ---------------------------------------------------------------------------


# Human-readable scaffolding lines per dimension value (issue
# 2026-06-10-05). These are STRUCTURAL hints folded into the prompt;
# they are NOT a fidelity guarantee — a dims-scaffolded persona's
# behavioral faithfulness needs an eval corpus (HR-7) before
# design-acceptance. Kept terse + imperative so the model reads them as
# behavioral directives, not prose.
_PERSONA_DIMENSION_SCAFFOLD = {
    "reasoning": {
        "deductive": "Reason deductively: argue from stated rules and "
                     "first principles to specific conclusions.",
        "empirical": "Reason empirically: ground every claim in observable "
                     "evidence from the target and context.",
        "analogical": "Reason analogically: surface parallels to known "
                      "patterns and prior cases to illuminate the target.",
    },
    "register": {
        "terse": "Register: terse. Be maximally concise; no preamble, no "
                 "filler.",
        "expansive": "Register: expansive. Develop your points fully with "
                     "supporting detail.",
        "socratic": "Register: socratic. Lead with probing questions that "
                    "expose assumptions before asserting.",
    },
    "conflict": {
        "adversarial": "Stance: adversarial. Actively seek flaws, "
                       "counter-examples, and failure modes.",
        "collaborative": "Stance: collaborative. Build on the work's intent "
                         "and propose constructive improvements.",
        "neutral": "Stance: neutral. Assess even-handedly without bias "
                   "toward approval or rejection.",
    },
}

# Stable render order (matches dimension declaration order).
_PERSONA_DIMENSION_ORDER = ("reasoning", "register", "conflict")


def _render_persona_dimensions_block(dims: dict | None) -> str:
    """Render the optional ``## Persona dimensions`` prompt section.

    Returns ``""`` when no dims are present, so the prompt layout is
    byte-identical to the pre-dims path for back-compat (un-dimensioned
    personas). When dims are present, emits one imperative scaffold line
    per known dim in :data:`_PERSONA_DIMENSION_ORDER`.
    """
    if not dims:
        return ""
    lines: list[str] = []
    for dim in _PERSONA_DIMENSION_ORDER:
        val = dims.get(dim)
        scaffold = _PERSONA_DIMENSION_SCAFFOLD.get(dim, {}).get(val) if val else None
        if scaffold:
            lines.append(f"- {scaffold}")
    if not lines:
        return ""
    body = "\n".join(lines)
    return f"## Persona dimensions\n\n{body}\n\n"


def assemble_prompt(
    *,
    persona_body: str,
    target_id: str,
    target_fm: dict,
    target_body: str,
    context_bundle: str = "",
    output_schema: dict | None = None,
    persona_dimensions: dict | None = None,
) -> str:
    """Assemble the prompt sent to gemini -p.

    Layout (deterministic — AXIS-6):

        <persona body>

        ## Target

        Target id: <target_id>
        Target type: <target_fm.type>
        Target title: <target_fm.title>

        ### Target body

        <target_body>

        ## Cross-linked context

        <context_bundle or "(none)">

        ## Output format

        Respond with valid JSON matching this schema. Do not include
        any prose outside the JSON object.

        <output_schema or default-schema>

    The ``Output format`` block carries the PG-4 double-parse contract:
    the persona's frontmatter ``output_schema`` (or a default) is
    inlined so the model knows the exact shape to emit; the consult
    skill parses ``response`` field as JSON against this schema.
    """
    target_type = target_fm.get("type") or "?"
    target_title = target_fm.get("title") or "(no title)"
    context = context_bundle.strip() or "(none)"
    schema_text = (
        json.dumps(output_schema, indent=2)
        if output_schema is not None
        else _DEFAULT_OUTPUT_SCHEMA_TEXT
    )
    dims_block = _render_persona_dimensions_block(persona_dimensions)
    return (
        f"{persona_body.rstrip()}\n\n"
        f"{dims_block}"
        f"## Target\n\n"
        f"Target id: {target_id}\n"
        f"Target type: {target_type}\n"
        f"Target title: {target_title}\n\n"
        f"### Target body\n\n"
        f"{target_body.rstrip()}\n\n"
        f"## Cross-linked context\n\n"
        f"{context}\n\n"
        f"## Output format\n\n"
        f"Respond with valid JSON matching this schema. Do not include "
        f"any prose outside the JSON object.\n\n"
        f"```json\n{schema_text}\n```\n"
    )


_DEFAULT_OUTPUT_SCHEMA_TEXT = """{
  "decision": "PROCEED | AMEND | RETHINK | N/A",
  "findings": [
    {"severity": "high | medium | low", "summary": "..."}
  ],
  "insights": [
    {"category": "...", "summary": "..."}
  ],
  "notes": "free-form supplementary notes (optional)"
}

Evaluative-mode personas: emit `decision` + `findings` (omit `insights`).
Generative-mode personas: emit `decision: \"N/A\"` + `insights` (omit `findings`)."""


# ---------------------------------------------------------------------------
# Gemini shell-out (charter AXIS-8 + PG-4 double-parse)
# ---------------------------------------------------------------------------


def invoke_gemini(
    *,
    prompt: str,
    model: str = DEFAULT_GEMINI_MODEL,
    include_dirs: list[str] | None = None,
    timeout_s: int = DEFAULT_TIMEOUT_S,
    gemini_bin: str = "gemini",
) -> dict:
    """Shell-out to ``gemini -p`` and return the parsed inner response.

    Invocation (charter §2.2):

        gemini --approval-mode plan -m <model> -o json \\
            [--include-directories <dirs>] -p <prompt>

    Returns the **inner-parsed JSON** (the persona's structured
    response after the PG-4 double-parse): (1) parse the gemini -o
    json envelope ``{session_id, response, stats}``, (2) extract the
    ``response`` string, (3) parse ``response`` as JSON.

    Raises:
    - :class:`GeminiUnavailable` if the binary is missing, subprocess
      exits non-zero, or timeout elapses. The exception carries the
      assembled prompt for the skill-layer Y/n fallback.
    - :class:`GeminiResponseParseError` if either parse step fails.
      Caller routes this through the same Y/n fallback path
      (degradation-class).

    HR-#3 never-silent: every failure path raises a typed exception
    with a clear ``reason``; the caller never gets a silent partial
    success.

    HR-#5 assume-auth: this function does not detect or repair
    ``gemini auth`` state; an auth failure surfaces as a non-zero
    exit + clear stderr (which we include in the GeminiUnavailable
    reason).
    """
    if not shutil.which(gemini_bin):
        raise GeminiUnavailable(
            reason=f"gemini binary {gemini_bin!r} not on PATH (HR-#5 "
                   f"assume-auth — install gemini-cli + run `gemini "
                   f"auth login` first)",
            assembled_prompt=prompt,
        )

    cmd: list[str] = [
        gemini_bin,
        "--approval-mode", "plan",
        "-m", model,
        "-o", "json",
    ]
    if include_dirs:
        cmd += ["--include-directories", ",".join(include_dirs)]
    cmd += ["-p", prompt]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired:
        raise GeminiUnavailable(
            reason=f"gemini subprocess timed out after {timeout_s}s",
            assembled_prompt=prompt,
        )
    except OSError as e:
        raise GeminiUnavailable(
            reason=f"gemini subprocess failed to launch: {e}",
            assembled_prompt=prompt,
        )

    if proc.returncode != 0:
        stderr_excerpt = (proc.stderr or "").strip()[:500]
        raise GeminiUnavailable(
            reason=(
                f"gemini exited {proc.returncode}; "
                f"stderr: {stderr_excerpt!r}"
            ),
            assembled_prompt=prompt,
        )

    try:
        envelope = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise GeminiResponseParseError(
            f"gemini -o json envelope did not parse: {e}; "
            f"stdout excerpt: {proc.stdout[:200]!r}"
        )

    if not isinstance(envelope, dict) or "response" not in envelope:
        raise GeminiResponseParseError(
            f"gemini -o json envelope missing 'response' field; "
            f"keys: {sorted(envelope.keys()) if isinstance(envelope, dict) else type(envelope).__name__}"
        )

    response_text = envelope.get("response")
    if not isinstance(response_text, str):
        raise GeminiResponseParseError(
            f"gemini envelope 'response' field is not a string, "
            f"got: {type(response_text).__name__}"
        )

    return parse_gemini_response_text(response_text)


def parse_persona_response_text(response_text: str) -> dict:
    """Parse a persona response as JSON per PG-4 — backend-agnostic.

    The persona prompt instructs the model to emit JSON. Models often
    wrap it in a fenced code block (``` ```json ... ``` ```); we
    strip that wrapper before parsing. If the result is not a JSON
    object, raises a plain :class:`ValueError`; the per-backend
    caller wraps it as :class:`GeminiResponseParseError` or
    :class:`AgyResponseParseError`.

    Cohort R factoring: the shared logic moved here from
    :func:`parse_gemini_response_text` (which is now a thin back-compat
    shim). Used directly by :func:`invoke_agy` (skips the outer
    envelope unwrap since agy emits plain text, not the gemini -o json
    envelope).
    """
    text = response_text.strip()
    fence_match = re.match(
        r"^```(?:json)?\s*\n(.*)\n```\s*$", text, re.DOTALL,
    )
    if fence_match:
        text = fence_match.group(1).strip()

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"persona response did not parse as JSON: {e}; "
            f"excerpt: {text[:200]!r}"
        )
    if not isinstance(parsed, dict):
        raise ValueError(
            f"persona response parsed but is not a JSON object "
            f"(got {type(parsed).__name__}); persona prompt should "
            f"instruct a single top-level object."
        )
    return parsed


def parse_gemini_response_text(response_text: str) -> dict:
    """Back-compat wrapper around :func:`parse_persona_response_text`.

    Preserves the existing gemini-path API contract: raises
    :class:`GeminiResponseParseError` on parse failure. Internal
    callers added by cohort R (e.g. :func:`invoke_agy`) use the
    factored :func:`parse_persona_response_text` directly + wrap
    parse errors as their backend-specific exception.
    """
    try:
        return parse_persona_response_text(response_text)
    except ValueError as e:
        raise GeminiResponseParseError(str(e))


# ---------------------------------------------------------------------------
# Antigravity (agy) shell-out (cohort R / wl:2026-06-05-06)
#
# Two-clean-backends pattern per charter §2 constraint 6: agy invocation is
# its own concrete function + helpers, NOT a unified abstraction over gemini.
# Shared surfaces (prompt assembly, response parse, Review write) are
# factored above; backend-specific surfaces (version-pin, auth-fail detect,
# argv shape) live here.
# ---------------------------------------------------------------------------


def _detect_agy_auth_failure(stdout: str) -> str | None:
    """Return the matched auth-fail prefix (or None) for the F2 quirk.

    agy 1.0.5 exits 0 even when OAuth auth times out (chunk-0 probe A
    confirmed: fresh-HOME triggers 30s OAuth wait, then exits with
    code 0 — auth-failure is NOT surfaced via returncode). Prefix-
    anchored detect on stdout is the local workaround; tracking-LOW
    filed post-LAND for the upstream agy fix.

    Matching rules (per chunk-1 devil-advocate review 2026-06-05-12
    HIGH-1 finding mitigation):
      1. Pattern must match at stdout PREFIX (``startswith``), not anywhere
         inside — a model response that discusses auth-error text would
         otherwise misfire.
      2. Total stdout length must be ≤ :data:`_AGY_PRINT_ERROR_LENGTH_CAP`
         (2KB). The agy error preamble is short; a long stdout starting
         with one of these phrases is almost certainly a real response.

    Made a top-level helper (not inline) so the cert harness can
    exercise it directly via Test #2 sub-axis A8 (mutation: drop the
    prefix-anchor + length cap + assert RED).
    """
    if len(stdout) > _AGY_PRINT_ERROR_LENGTH_CAP:
        return None
    stripped = stdout.lstrip()
    for pattern in _AGY_PRINT_ERROR_PREFIXES:
        if stripped.startswith(pattern):
            return pattern
    return None


def _check_agy_version_or_raise(
    agy_bin: str, *, assembled_prompt: str,
) -> None:
    """Probe ``<agy_bin> --version``; raise :class:`AgyUnavailable` if the
    installed version is below :data:`_AGY_MIN_VERSION` AND
    :data:`AGY_VERSION_OVERRIDE_ENV` is not set in the environment.

    Mirrors :func:`parley.adapters.antigravity.check_version_or_raise`
    semantics (canonical seam). Returns None on success; the version
    is also embedded in any raised exception's reason for diagnostics.

    Asymmetry with the gemini path is deliberate: agy 1.0.5 is a new
    binary with version-pin discipline; gemini is stable and we don't
    probe its version.
    """
    if os.environ.get(AGY_VERSION_OVERRIDE_ENV):
        return
    try:
        result = subprocess.run(
            [agy_bin, "--version"],
            capture_output=True,
            text=True,
            timeout=10.0,
        )
    except (OSError, subprocess.SubprocessError) as e:
        raise AgyUnavailable(
            reason=f"agy --version probe failed: {e}",
            assembled_prompt=assembled_prompt,
        )
    if result.returncode != 0:
        stderr_excerpt = (result.stderr or "").strip()[:200]
        raise AgyUnavailable(
            reason=(
                f"agy --version exited {result.returncode}; "
                f"stderr: {stderr_excerpt!r}"
            ),
            assembled_prompt=assembled_prompt,
        )
    m = _AGY_VERSION_RE.match(result.stdout.strip())
    if m is None:
        raise AgyUnavailable(
            reason=(
                f"agy --version stdout did not parse as plain semver "
                f"matching {_AGY_VERSION_RE.pattern}; "
                f"got: {result.stdout[:200]!r}. Set "
                f"{AGY_VERSION_OVERRIDE_ENV} to bypass."
            ),
            assembled_prompt=assembled_prompt,
        )
    version = (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    if version < _AGY_MIN_VERSION:
        min_str = ".".join(str(p) for p in _AGY_MIN_VERSION)
        cur_str = ".".join(str(p) for p in version)
        raise AgyUnavailable(
            reason=(
                f"version-unsupported: agy {cur_str} < min {min_str}. "
                f"Set {AGY_VERSION_OVERRIDE_ENV} to bypass."
            ),
            assembled_prompt=assembled_prompt,
        )


# ---------------------------------------------------------------------------
# Cohort GG fix #1 + fix #2 helpers (charter §2.1 + §2.2)
# ---------------------------------------------------------------------------


def _semantic_split_target_body(body: str, max_bytes: int) -> list[str]:
    """Split ``body`` into chunks each ≤ ``max_bytes`` (utf-8 byte length).

    Prefers paragraph-boundary splits (``\\n\\n``); falls back to byte-cut
    on any paragraph that on its own exceeds ``max_bytes``. Greedy: packs
    as many paragraphs as fit per chunk to minimize total part count.
    """
    chunks: list[str] = []
    current = ""
    for para in body.split("\n\n"):
        candidate = (current + "\n\n" + para) if current else para
        if current and len(candidate.encode("utf-8")) > max_bytes:
            chunks.append(current)
            current = para
        else:
            current = candidate
    if current:
        chunks.append(current)

    final: list[str] = []
    for c in chunks:
        if len(c.encode("utf-8")) <= max_bytes:
            final.append(c)
            continue
        b = c.encode("utf-8")
        for i in range(0, len(b), max_bytes):
            final.append(b[i : i + max_bytes].decode("utf-8", errors="ignore"))
    return final


def _chunk_agy_target_body_if_oversize(prompt: str) -> str:
    """Rewrite ``prompt``'s target_body section with ``(part X of Y)`` headers
    + synthesize-across-parts closing instruction if oversize.

    Pass-through (returns ``prompt`` unchanged) when:
    - The deterministic ``### Target body\\n\\n<body>\\n\\n## Cross-linked
      context`` boundary doesn't match (malformed assembly).
    - The target_body byte length is ≤ ``_AGY_TARGET_CHUNK_THRESHOLD_BYTES``.

    Charter §2.1 secondary safeguard. Threshold derived empirically from
    cohort Y trial row-3-vs-row-6 narration boundary.
    """
    m = _AGY_TARGET_BODY_BOUNDARY_RE.search(prompt)
    if m is None:
        return prompt
    body = m.group(1)
    if len(body.encode("utf-8")) <= _AGY_TARGET_CHUNK_THRESHOLD_BYTES:
        return prompt
    parts = _semantic_split_target_body(
        body, _AGY_TARGET_CHUNK_THRESHOLD_BYTES,
    )
    total = len(parts)
    chunked = "\n\n".join(
        f"### Target body (part {i + 1} of {total})\n\n{p.strip()}"
        for i, p in enumerate(parts)
    )
    rebuilt = (
        prompt[: m.start()]
        + chunked
        + "\n\n## Cross-linked context"
        + prompt[m.end() :]
    )
    return rebuilt.rstrip() + "\n\n" + _AGY_SYNTHESIZE_INSTRUCTION + "\n"


def _validate_agy_schema_or_raise(
    parsed: dict, schema: dict | None,
) -> None:
    """Lightweight structural validation of ``parsed`` against the persona's
    ``output_schema`` dict (from frontmatter).

    Rules:
    - ``schema is None`` → no validation (back-compat for callers that
      don't supply one).
    - Each required schema key must be present in ``parsed``.
    - The ``notes`` key is canonically optional (matches existing persona
      conventions; some emit it, some don't).
    - Value-shape match by JSON category: list/dict/str → list/dict/str.
      No recursion into nested shapes (schema dicts are short + the
      persona prompt instructs the model on field semantics).

    Raises :class:`ValueError` on first violation. Caller wraps as
    :class:`AgyResponseParseError` after the one-retry policy in
    :func:`invoke_agy`.
    """
    if schema is None:
        return
    for key, schema_val in schema.items():
        if key == "notes":
            continue
        if key not in parsed:
            raise ValueError(
                f"schema validation: missing required key {key!r} "
                f"(persona schema requires it)"
            )
        actual = parsed[key]
        if isinstance(schema_val, list) and not isinstance(actual, list):
            raise ValueError(
                f"schema validation: key {key!r} expected list, got "
                f"{type(actual).__name__}"
            )
        if isinstance(schema_val, dict) and not isinstance(actual, dict):
            raise ValueError(
                f"schema validation: key {key!r} expected object, got "
                f"{type(actual).__name__}"
            )
        if isinstance(schema_val, str) and not isinstance(actual, str):
            raise ValueError(
                f"schema validation: key {key!r} expected string, got "
                f"{type(actual).__name__}"
            )


def get_backend_version(backend: str, *, bin_name: str | None = None) -> str:
    """Return a short version string for the named backend, for the
    cohort GG fix #4 provenance marker.

    Per @wsl-plan S3 ratify (msg-0c385ce99cc7) Option A: a helper called
    at Review-write time, NOT a return-shape change to ``invoke_agy`` /
    ``invoke_gemini``. Keeps caller-side blast radius near-zero.

    Mapping:
    - ``"agy"``: probes ``<bin_name or 'agy'> --version`` via subprocess
      (10s ceiling); parses ``_AGY_VERSION_RE``; returns the dotted
      semver string (e.g. ``"1.0.5"``). On any probe failure returns
      ``"unknown"`` — provenance marker is durable info, never blocks
      a Review write (HR-#3 applies to backend invocation paths, not
      this metadata helper).
    - ``"gemini"``: returns ``"cli"`` — gemini CLI has no stable
      ``--version`` probe and we don't probe it per cohort R precedent
      (charter §3 chunk-0 PG-3 — gemini stable, no version-pin
      discipline).
    - ``"claude-code"``: returns ``"fallback"`` — surfaces in marker
      when operator chose Y/n fallback branch at the skill layer.
    - ``"codex"``: returns ``"stub"`` — wl:2026-06-04-03 placeholder.
    - other: returns ``"unknown"``.
    """
    if backend == "agy":
        bin_resolved = bin_name or "agy"
        try:
            result = subprocess.run(
                [bin_resolved, "--version"],
                capture_output=True, text=True, timeout=10.0,
            )
        except (OSError, subprocess.SubprocessError):
            return "unknown"
        if result.returncode != 0:
            return "unknown"
        m = _AGY_VERSION_RE.match(result.stdout.strip())
        if m is None:
            return "unknown"
        return ".".join((m.group(1), m.group(2), m.group(3)))
    if backend == "gemini":
        return "cli"
    if backend == "claude-code":
        return "fallback"
    if backend == "codex":
        return "stub"
    return "unknown"


def format_provenance_marker(
    *, backend: str, version: str, model: str, ts: datetime,
) -> str:
    """Build the cohort GG fix #4 provenance HTML-comment marker.

    Shape (charter §2.4):
        ``<!-- backend=<name>-<version> model=<model-id> ts=<iso-8601> -->``

    HTML-comment form keeps the marker invisible in rendered markdown
    while durably committing backend / version / model / timestamp to
    the Review entity body. Closes wl:2026-06-05-15 — future A/B trials
    don't need a /tmp MAPPING.json reconstruction; attribution lives in
    the Review file itself.
    """
    return (
        f"<!-- backend={backend}-{version} model={model} ts={_iso(ts)} -->"
    )


def _agy_run_once(
    cmd: list[str], prompt: str, timeout_s: int,
) -> dict:
    """Single subprocess.run + parse for agy. Internal helper used by
    :func:`invoke_agy` for both the primary attempt and the
    schema-malformed retry.

    Raises :class:`AgyUnavailable` on subprocess-class failures
    (timeout / nonzero / auth-fail / empty stdout); raises
    :class:`ValueError` on JSON parse failure (caller wraps).
    """
    try:
        proc = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired:
        raise AgyUnavailable(
            reason=f"agy subprocess timed out after {timeout_s}s",
            assembled_prompt=prompt,
        )
    except OSError as e:
        raise AgyUnavailable(
            reason=f"agy subprocess failed to launch: {e}",
            assembled_prompt=prompt,
        )

    if proc.returncode != 0:
        stderr_excerpt = (proc.stderr or "").strip()[:500]
        raise AgyUnavailable(
            reason=(
                f"agy exited {proc.returncode}; "
                f"stderr: {stderr_excerpt!r}"
            ),
            assembled_prompt=prompt,
        )

    auth_fail = _detect_agy_auth_failure(proc.stdout)
    if auth_fail is not None:
        raise AgyUnavailable(
            reason=(
                f"agy-print-mode-error: stdout starts with "
                f"{auth_fail!r}. agy 1.0.5 emits its error preamble "
                f"(auth-required / timed-out) to stdout while still "
                f"exiting 0; tracking-LOW filed post-LAND for the "
                f"upstream fix. If this was unexpected, run `agy` "
                f"interactively to verify auth, then retry."
            ),
            assembled_prompt=prompt,
        )

    if not proc.stdout.strip():
        stderr_excerpt = (proc.stderr or "").strip()[:200]
        raise AgyUnavailable(
            reason=(
                f"agy returned empty stdout (no model response). "
                f"stderr: {stderr_excerpt!r}"
            ),
            assembled_prompt=prompt,
        )

    return parse_persona_response_text(proc.stdout)


def invoke_agy(
    *,
    prompt: str,
    model: str | None = None,
    include_dirs: list[str] | None = None,
    timeout_s: int = DEFAULT_TIMEOUT_S,
    agy_bin: str = "agy",
    output_schema: dict | None = None,
) -> dict:
    """Shell-out to ``agy --print -`` via stdin and return the parsed inner
    response.

    Invocation (per chunk-0 forensic — charter §4 chunk-1 item 2):

        agy --print - [--model <m>] [--add-dir <d1> --add-dir <d2> ...]

    The prompt is fed via STDIN (F1 mitigation: avoids OS ``ARG_MAX``
    on large /consult prompts). The dash sentinel (``--print -``) is
    Unix-convention for "read prompt from stdin".

    Returns the parsed JSON dict (persona's structured response).
    agy emits plain-text stdout (no envelope like gemini's
    ``-o json``); the persona prompt instructs JSON output
    (optionally fenced), which :func:`parse_persona_response_text`
    extracts.

    ``model=None`` (the default) omits ``--model`` from argv entirely
    so agy uses its built-in tenant-adapted default (F4 amendment).
    Specify a string only to override.

    **Cohort GG fix #1** (charter §2.1): prepends
    :data:`_AGY_PROMPT_GUARD_BLOCK` to mitigate the row-6 shell-narration
    failure mode; if the target_body section exceeds
    :data:`_AGY_TARGET_CHUNK_THRESHOLD_BYTES`, the prompt is rewritten
    with ``### Target body (part X of Y)`` headers + closing synthesize
    instruction.

    **Cohort GG fix #2** (charter §2.2): if ``output_schema`` is
    supplied, the parsed response is validated against it via
    :func:`_validate_agy_schema_or_raise`. On schema-malformed first
    attempt, ONE retry runs with the schema appended a second time to
    the prompt; on second-malformed raises
    :class:`AgyResponseParseError`. ``output_schema=None`` (the default)
    disables validation entirely (back-compat).

    Raises:
    - :class:`AgyUnavailable` if binary missing, version unsupported,
      subprocess non-zero exit, timeout, auth-fail substring detected
      (F2 workaround), or empty stdout. Carries ``assembled_prompt``
      for the skill-layer Y/n fallback.
    - :class:`AgyResponseParseError` if stdout doesn't parse per the
      persona schema, OR (cohort GG fix #2) the parsed response fails
      schema validation after one retry.

    HR-#3 never-silent: every failure path raises a typed exception.
    HR-#5 assume-auth: this function does not detect or repair
    ``agy`` auth state; auth failures surface as AgyUnavailable.
    """
    if not shutil.which(agy_bin):
        raise AgyUnavailable(
            reason=(
                f"agy binary {agy_bin!r} not on PATH (HR-#5 assume-auth "
                f"— install antigravity-cli + run `agy` interactively to "
                f"complete OAuth first)"
            ),
            assembled_prompt=prompt,
        )

    _check_agy_version_or_raise(agy_bin, assembled_prompt=prompt)

    # Fix #1: secondary chunking safeguard (no-op if under threshold) +
    # primary guardrail block prepend. assemble_prompt() stays pure;
    # the agy-side transformations live here (cert axis A2: gemini path
    # byte-identical regression).
    prompt = _chunk_agy_target_body_if_oversize(prompt)
    prompt = _AGY_PROMPT_GUARD_BLOCK + "\n\n" + prompt

    cmd: list[str] = [agy_bin, "--print", "-"]
    if model:
        cmd += ["--model", model]
    for d in include_dirs or []:
        cmd += ["--add-dir", d]

    try:
        parsed = _agy_run_once(cmd, prompt, timeout_s)
    except ValueError as e:
        raise AgyResponseParseError(str(e))

    if output_schema is None:
        return parsed

    # Fix #2: per-persona schema validation + one-retry-on-malformed.
    try:
        _validate_agy_schema_or_raise(parsed, output_schema)
        return parsed
    except ValueError as first_err:
        sys.stderr.write(
            f"[consult] backend agy returned malformed JSON; retrying "
            f"once with explicit schema repeat: {first_err}\n"
        )
        retry_prompt = (
            prompt.rstrip()
            + "\n\nREPEAT — emit JSON matching this schema EXACTLY:\n\n"
            + "```json\n"
            + json.dumps(output_schema, indent=2)
            + "\n```\n"
        )
        try:
            parsed_retry = _agy_run_once(cmd, retry_prompt, timeout_s)
        except ValueError as parse_err:
            raise AgyResponseParseError(
                f"schema validation failed after one retry: first "
                f"{first_err}; retry produced unparseable JSON: "
                f"{parse_err}"
            )
        try:
            _validate_agy_schema_or_raise(parsed_retry, output_schema)
            return parsed_retry
        except ValueError as second_err:
            raise AgyResponseParseError(
                f"schema validation failed after one retry: first "
                f"{first_err}; second {second_err}"
            )


# ---------------------------------------------------------------------------
# Top-level backend dispatch (cohort R / wl:2026-06-05-06)
# ---------------------------------------------------------------------------


def invoke_backend(
    backend: str,
    *,
    prompt: str,
    model: str | None = None,
    include_dirs: list[str] | None = None,
    timeout_s: int = DEFAULT_TIMEOUT_S,
    gemini_bin: str = "gemini",
    agy_bin: str = "agy",
    output_schema: dict | None = None,
) -> dict:
    """Top-level dispatch: route to :func:`invoke_gemini` /
    :func:`invoke_agy` / :class:`NotImplementedError` (codex stub).

    Per charter §2 constraint 6 (two-clean-backends pattern): shallow
    string-dispatch over backend-specific invoke functions — no
    unified abstraction layer.

    - ``backend="gemini"``: model defaults to :data:`DEFAULT_GEMINI_MODEL`
      when ``model is None``; routes to :func:`invoke_gemini`. Byte-
      identical regression with the pre-cohort-R direct-call path
      (charter §2 constraint 1 additive-only). ``output_schema`` is NOT
      threaded — gemini path stays unchanged (cert axis A2).
    - ``backend="agy"``: ``model=None`` is passed through to
      :func:`invoke_agy`, which omits ``--model`` and lets agy use its
      built-in default (F4 amendment first preference). Cohort GG fix #2:
      ``output_schema`` is threaded to enable per-persona schema
      validation + retry-once-on-malformed.
    - ``backend="codex"``: raises :class:`NotImplementedError`
      referencing ``wl:2026-06-04-03`` (codex backend scope).
    - other: raises :class:`ValueError` with the offending value.
    """
    if backend == "gemini":
        return invoke_gemini(
            prompt=prompt,
            model=model or DEFAULT_GEMINI_MODEL,
            include_dirs=include_dirs,
            timeout_s=timeout_s,
            gemini_bin=gemini_bin,
        )
    if backend == "agy":
        return invoke_agy(
            prompt=prompt,
            model=model,
            include_dirs=include_dirs,
            timeout_s=timeout_s,
            agy_bin=agy_bin,
            output_schema=output_schema,
        )
    if backend == "codex":
        raise NotImplementedError(
            "codex backend not yet implemented; see wl:2026-06-04-03"
        )
    raise ValueError(
        f"unknown backend: {backend!r}; expected one of "
        f"'gemini' / 'agy' / 'codex'"
    )


# ---------------------------------------------------------------------------
# Review entity write (charter §2.1 — persona-mediated sub-schema)
# ---------------------------------------------------------------------------


def record_consult_review(
    *,
    repo_root: Path,
    persona_slug: str,
    persona_meta: dict,
    target_id: str,
    target_fm: dict,
    parsed_response: dict,
    model: str = DEFAULT_GEMINI_MODEL,
    title: str | None = None,
    scope: str | None = None,
    author: str = "@unknown",
    owner_user: str = DEFAULT_OWNER_USER,
    linked_msg_ids: list[str] | None = None,
    linked_decisions: list[str] | None = None,
    supersedes: str | None = None,
    created_at: datetime | None = None,
    backend: str = "gemini",
    agy_bin: str = "agy",
) -> Path:
    """Write a persona-mediated Review entity; return the file path.

    Per charter §2.1 + chunk-0 PG-1(a) ratify, this lands the
    "persona_used"-discriminator sub-schema (see
    :func:`validators._validate_review_persona_path`). The OLD path
    (existing 5-enum + status={in_progress, completed}) is unchanged
    and still owned by :func:`entities.record_review`.

    Maps ``parsed_response`` (PG-4 double-parsed inner JSON) onto
    the Review frontmatter:
    - evaluative-mode persona → ``findings`` from response.findings
    - generative-mode persona → ``insights`` from response.insights
    - both modes → ``decision`` from response.decision

    Forward cross-link (PG-9 ratify): writes
    ``linked_<target-kind>: [<target_id>]`` matching the target's type;
    the target file is NEVER mutated.

    Supersede chain (HR-#7): if ``supersedes`` is set, the NEW review
    carries the back-pointer; the OLD review must already have been
    transitioned via :func:`supersede_review` (independent call,
    keeps each write atomic).
    """
    if not isinstance(persona_meta, dict):
        raise ValueError("persona_meta must be a dict")
    mode = persona_meta.get("mode")
    if mode not in _PERSONA_MODES:
        raise ValueError(
            f"persona mode must be one of {sorted(_PERSONA_MODES)}, "
            f"got: {mode!r}"
        )

    repo = Path(repo_root)
    reviews_dir = ledger_paths.compat_kind_dir(repo, "reviews")

    if created_at is None:
        created_at = _utc_now()

    title_resolved = (
        title
        or f"/consult {persona_slug} {target_id}"
    )
    slug_clean = _slugify(f"{persona_slug}-{target_id}")
    date_str = created_at.strftime("%Y-%m-%d")
    counter = _next_counter(reviews_dir, date_str)
    review_id = _format_id(
        created_at=created_at, counter=counter, slug=slug_clean,
    )

    decision = parsed_response.get("decision")
    if mode == "evaluative" and decision in (None, ""):
        decision = "PROCEED"  # safe default if persona omits; validator allows
    if mode == "generative":
        decision = "N/A"  # enforced per validator

    scope_resolved = scope or _derive_scope_from_target(target_fm)

    fm = {
        "id": review_id,
        "type": "review",
        "review_type": persona_slug,
        "title": title_resolved,
        "status": "landed",
        "scope": scope_resolved,
        "created_at": _iso(created_at),
        "author": author,
        "owner_user": owner_user,
        "mode": mode,
        "decision": decision,
        "persona_used": persona_slug,
        "target_entity_id": target_id,
        "model": model,
        "linked_decisions": list(linked_decisions or []),
        "linked_reviews": [],
        "linked_msg_ids": list(linked_msg_ids or []),
    }

    if mode == "evaluative":
        fm["findings"] = list(parsed_response.get("findings") or [])
    else:
        fm["insights"] = list(parsed_response.get("insights") or [])

    linked_field = _target_linked_field(target_fm)
    if linked_field is not None:
        fm[linked_field] = [target_id]

    if supersedes:
        fm["supersedes"] = supersedes

    validators.validate_review(fm)

    body = _initial_consult_body(
        persona_slug=persona_slug,
        persona_meta=persona_meta,
        target_id=target_id,
        target_fm=target_fm,
        model=model,
        decision=decision,
        parsed_response=parsed_response,
        mode=mode,
    )

    # Cohort GG fix #4: prepend the provenance marker to the body.
    # HTML-comment form is invisible in rendered markdown but durable
    # in the Review file — closes wl:2026-06-05-15 by carrying
    # backend / version / model / ts attribution into the entity itself.
    provenance = format_provenance_marker(
        backend=backend,
        version=get_backend_version(backend, bin_name=agy_bin),
        model=model,
        ts=created_at,
    )
    body = provenance + "\n\n" + body

    reviews_dir.mkdir(parents=True, exist_ok=True)
    target_path = reviews_dir / f"{review_id}.md"
    _fm.write(target_path, fm, body)

    _render_reviews_index(reviews_dir)
    return target_path


# wl:2026-06-05-03 PRIMARY auto-narrow heuristic — mappings used by
# :func:`_auto_narrow_include_dirs` to derive a narrowed scope from
# target frontmatter (charter §4.1).

# Target ``type`` → canonical home directory. Mirrors the
# :data:`_TARGET_SEARCH_DIRS` tuple but keyed by entity type for
# direct lookup. "charter" → docs/inbox covers the QUATERNARY case.
_TYPE_TO_DIR: dict[str, str] = {
    "decision":     "docs/decisions",
    "issue":        "docs/issues",
    "review":       "docs/reviews",
    "handoff":      "docs/handoffs",
    "conversation": "docs/conversations",
    "dispatch":     "docs/dispatches",
    "wip":          "docs/wip",
    "prd":          "docs/prds",
    "charter":      "docs/inbox",
}

# ``linked_<kind>`` field → canonical home directory. Direct mapping
# avoids inverting :data:`_TYPE_TO_LINKED_FIELD` (which omits dispatch
# / wip / charter that have no symmetric reverse-link from a Review).
_LINKED_FIELD_TO_DIR: dict[str, str] = {
    "linked_decisions":     "docs/decisions",
    "linked_issues":        "docs/issues",
    "linked_reviews":       "docs/reviews",
    "linked_handoffs":      "docs/handoffs",
    "linked_conversations": "docs/conversations",
    "linked_dispatches":    "docs/dispatches",
    "linked_wip":           "docs/wip",
    "linked_prds":          "docs/prds",
}

# When the target's ``scope`` suffix (the part after the ``<prefix>:``)
# contains one of these substrings, include the corresponding code
# dirs. Data-driven so adding a new scope keyword is a one-line table
# bump rather than a function-body change.
_SCOPE_SUBSTR_TO_CODE_DIRS: dict[str, tuple[str, ...]] = {
    "consult":  (".claude/skills/consult", ".claude/scripts/dev-mgmt"),
    "dev-mgmt": (".claude/scripts/dev-mgmt", ".claude/skills"),
    "parley":   (".claude/skills/parley",),
}


def auto_narrow_threshold_multiplier() -> int:
    """Read the auto-narrow trigger multiplier (default 2; env-overridable).

    Per wl:2026-06-05-03 charter §4.1: auto-narrow fires when the
    token-budget estimate exceeds ``M × budget`` where ``M`` defaults
    to 2. Operators tune via :data:`AUTO_NARROW_THRESHOLD_MULTIPLIER_ENV`;
    invalid / non-positive env values silently fall back to the default
    (HR-#3 never-silent applies to backend invoke failures, not config
    parse; bad env value is a logged WARNING at usage site).
    """
    env_val = os.environ.get(AUTO_NARROW_THRESHOLD_MULTIPLIER_ENV)
    if env_val:
        try:
            mult = int(env_val)
            if mult >= 1:
                return mult
        except ValueError:
            pass
    return AUTO_NARROW_THRESHOLD_MULTIPLIER_DEFAULT


def _auto_narrow_include_dirs(target_fm: dict) -> list[str]:
    """Derive a narrowed ``include_dirs`` list from the target's frontmatter.

    Per wl:2026-06-05-03 charter §4.1: triggered (by the cli.py wire-in)
    when ``--include-dirs`` is unset AND the token-budget estimate
    exceeds :func:`auto_narrow_threshold_multiplier` × the configured
    budget. Operator-passed ``--include-dirs`` always wins — this helper
    is never called when the operator scoped explicitly.

    Derivation (charter §4.1):

    1. Always include canonical entity homes (``docs/decisions``,
       ``docs/issues``, ``docs/reviews``) — cheap to scan + the most
       common cross-link targets.
    2. Target's own home dir, mapped from ``type`` via
       :data:`_TYPE_TO_DIR`. Handles the QUATERNARY case
       (``type: charter`` → ``docs/inbox``).
    3. Sibling ``linked_*`` entity dirs — each populated
       ``linked_<kind>`` field's canonical home via
       :data:`_LINKED_FIELD_TO_DIR`.
    4. Scope-substring hint — if the target's ``scope`` suffix (the
       part after ``<prefix>:``) contains a substring in
       :data:`_SCOPE_SUBSTR_TO_CODE_DIRS`, include the mapped code
       dirs (e.g., scope ``code:consult-skill`` → ``.claude/skills/
       consult`` + ``.claude/scripts/dev-mgmt``).

    Returns repo-relative forward-slash paths (de-duplicated, insertion
    order preserved). The caller is responsible for:

      - filtering the existing ``visible_files`` to those under any
        derived prefix (cheap; no re-scan needed)
      - re-estimating ``files_bytes`` from the narrowed list
      - converting to absolute paths for the gemini ``--include-
        directories`` CSV / agy ``--add-dir`` invocations.
    """
    derived: list[str] = []
    seen: set[str] = set()

    def _add(d: str) -> None:
        if d and d not in seen:
            seen.add(d)
            derived.append(d)

    for d in ("docs/decisions", "docs/issues", "docs/reviews"):
        _add(d)

    target_type = target_fm.get("type")
    if isinstance(target_type, str):
        home = _TYPE_TO_DIR.get(target_type)
        if home:
            _add(home)

    for field, home in _LINKED_FIELD_TO_DIR.items():
        if target_fm.get(field):
            _add(home)

    scope = target_fm.get("scope")
    if isinstance(scope, str) and ":" in scope:
        scope_suffix = scope.split(":", 1)[1]
        for substr, code_dirs in _SCOPE_SUBSTR_TO_CODE_DIRS.items():
            if substr in scope_suffix:
                for d in code_dirs:
                    _add(d)

    return derived


def _derive_scope_from_target(target_fm: dict) -> str:
    """Choose a scope string for the Review from the target's metadata.

    Preference order:
    1. Target's own ``scope`` field if set + scope-prefix-valid.
    2. ``repo:<target-type>`` as a safe default (passes
       :func:`validators._check_scope`).
    """
    target_scope = target_fm.get("scope")
    if isinstance(target_scope, str) and target_scope.startswith(
        ("sprint:", "repo:", "design:", "arc:", "decision:")
    ):
        return target_scope
    target_type = target_fm.get("type") or "unknown"
    return f"repo:{target_type}"


def _initial_consult_body(
    *,
    persona_slug: str,
    persona_meta: dict,
    target_id: str,
    target_fm: dict,
    model: str,
    decision: str | None,
    parsed_response: dict,
    mode: str,
) -> str:
    """Compose the Review markdown body for a consult-mediated write.

    Sections:
      - ``# <title>``
      - ``## Summary`` — the persona's free-form notes from response
      - ``## Findings`` (evaluative) — bulleted from frontmatter
        ``findings`` for human-readability (frontmatter is SoT)
      - ``## Insights`` (generative) — bulleted from frontmatter
        ``insights`` for human-readability
      - ``## Provenance`` — persona / model / target / decision
    """
    lines: list[str] = []
    lines.append(f"# /consult {persona_slug} {target_id}")
    lines.append("")
    notes = parsed_response.get("notes") or parsed_response.get("summary")
    if notes:
        lines.append("## Summary")
        lines.append("")
        lines.append(str(notes).rstrip())
        lines.append("")
    if mode == "evaluative":
        lines.append("## Findings")
        lines.append("")
        findings = parsed_response.get("findings") or []
        if not findings:
            lines.append("(no findings)")
        else:
            for f in findings:
                if not isinstance(f, dict):
                    continue
                sev = f.get("severity", "?")
                summary = f.get("summary", "")
                lines.append(f"- **{sev}** — {summary}")
        lines.append("")
    else:
        lines.append("## Insights")
        lines.append("")
        insights = parsed_response.get("insights") or []
        if not insights:
            lines.append("(no insights)")
        else:
            for ins in insights:
                if not isinstance(ins, dict):
                    continue
                category = ins.get("category", "?")
                summary = ins.get("summary", "")
                lines.append(f"- **{category}** — {summary}")
        lines.append("")
    lines.append("## Provenance")
    lines.append("")
    lines.append(f"- **Persona:** `{persona_slug}` ({mode})")
    lines.append(f"- **Model:** `{model}`")
    lines.append(f"- **Target:** `{target_id}` ({target_fm.get('type', '?')})")
    if decision:
        lines.append(f"- **Decision:** `{decision}`")
    lines.append("")
    return "\n".join(lines)


def _render_reviews_index(reviews_dir: Path) -> None:
    """Re-render ``docs/reviews/INDEX.md`` after a Review write.

    Delegates to :mod:`index` ``render`` with the REVIEW_COLUMNS shape
    (matches what :func:`entities.record_review` already does for the
    existing-path writes). This keeps INDEX rendering consistent
    across the union: a single INDEX surfaces both sub-schemas.
    """
    try:
        import index
        index.render(reviews_dir, title="Reviews", columns=index.REVIEW_COLUMNS)
    except Exception:
        # Hard Rule 5 / D33: INDEX render failures are advisory; never
        # block the entity write. Caller already has the path back.
        pass


# ---------------------------------------------------------------------------
# Supersede transition (HR-#7)
# ---------------------------------------------------------------------------


def supersede_review(
    *,
    repo_root: Path,
    old_id: str,
    new_id: str,
    rationale: str | None = None,
    by_seat: str | None = None,
    transition_at: datetime | None = None,
) -> Path:
    """Mark the OLD persona-mediated Review as superseded by the NEW one.

    HR-#7 supersede pattern (mirrors dispatch). Updates the OLD
    review's frontmatter: ``status='superseded'`` + ``superseded_by=
    <new_id>``. Appends a lifecycle log entry to the body. The NEW
    review is written separately by :func:`record_consult_review`
    with ``supersedes=<old_id>``.

    Idempotent: if ``status`` is already ``superseded``, the call is
    a no-op returning the existing path.

    Forward-only: this function does NOT roll back a supersede; if
    the operator picked the wrong target, write a fresh review and
    supersede the wrong one.

    Only valid on the persona-mediated path. Calling this on an
    existing-path Review (no ``persona_used``) raises ``ValueError``
    — the existing path's terminal state is ``completed``, not
    ``superseded``; HR-#7 applies to the new union sub-schema only.
    """
    repo = Path(repo_root)
    reviews_dir = ledger_paths.compat_kind_dir(repo, "reviews")
    target = reviews_dir / f"{old_id}.md"
    if not target.exists():
        raise FileNotFoundError(
            f"Review {old_id!r} not found at {target}"
        )

    fm, body = _fm.parse(target)
    if not isinstance(fm, dict):
        raise ValueError(f"{target}: frontmatter not a mapping")

    if "persona_used" not in fm:
        raise ValueError(
            f"Review {old_id!r} is the existing closed-enum path "
            f"(no persona_used field); supersede transition is the "
            f"persona-mediated sub-schema only (HR-#7 + PG-1(a))"
        )

    if fm.get("status") == "superseded":
        # Idempotent no-op; consistent with dispatch-satisfy
        return target

    if not new_id or not isinstance(new_id, str):
        raise ValueError("new_id must be a non-empty string")

    if transition_at is None:
        transition_at = _utc_now()
    when_iso = _iso(transition_at)

    fm["status"] = "superseded"
    fm["superseded_by"] = new_id

    validators.validate_review(fm)

    detail_parts: list[str] = [f"superseded_by={new_id}"]
    if by_seat:
        detail_parts.append(f"by {by_seat}")
    if rationale:
        detail_parts.append(rationale)
    detail = " — ".join(detail_parts)
    body = _append_lifecycle(body, kind="superseded", when=when_iso, detail=detail)

    _fm.write(target, fm, body)
    _render_reviews_index(reviews_dir)
    return target


def _append_lifecycle(
    body: str, *, kind: str, when: str, detail: str | None,
) -> str:
    """Append a lifecycle log entry — mirror of prd._append_transition.

    If the body doesn't yet have a ``## Lifecycle`` section, append
    one. Otherwise insert the new line at the end of the file.
    """
    line = f"- **{kind}** at {when}"
    if detail:
        line += f" — {detail}"
    body = body.rstrip()
    if not body:
        body = "## Lifecycle\n"
    if "## Lifecycle" not in body:
        body += "\n\n## Lifecycle\n"
    return body + "\n" + line + "\n"


# ---------------------------------------------------------------------------
# Graceful degradation helper for the skill layer
# ---------------------------------------------------------------------------


def write_fallback_response_template(
    *,
    persona_slug: str,
    persona_meta: dict,
    target_id: str,
    assembled_prompt: str,
    tmp_dir: Path | None = None,
) -> Path:
    """Stage the assembled prompt to a temp file for the Y-branch fallback.

    Returns a Path the operator-CC can read + respond to. The skill
    layer:
    1. catches :class:`GeminiUnavailable`
    2. calls this helper to write a temp prompt file
    3. surfaces a Y/n prompt + the path to the operator
    4. on Y, the operator-CC reads the prompt + generates a JSON
       response, writes it back to a sibling file, then invokes
       ``consult-finalize`` (CLI verb) with --response-from-file
    5. on n, exits clean with no Review write (charter §2.4 n branch)

    Default tmp_dir: ``$TMPDIR`` if set else system tmp via
    :func:`tempfile.gettempdir`. The file is NOT auto-cleaned —
    leave it for the operator to inspect post-mortem.
    """
    import tempfile
    if tmp_dir is None:
        tmp_dir = Path(os.environ.get("TMPDIR") or tempfile.gettempdir())
    tmp_dir = Path(tmp_dir)
    tmp_dir.mkdir(parents=True, exist_ok=True)

    stamp = _utc_now().strftime("%Y%m%dT%H%M%SZ")
    filename = (
        f"consult-fallback-{persona_slug}-{_slugify(target_id)}-{stamp}.md"
    )
    target_path = tmp_dir / filename

    header = (
        f"<!-- consult-skill fallback (gemini unavailable) -->\n"
        f"<!-- persona: {persona_slug} ({persona_meta.get('mode', '?')}) -->\n"
        f"<!-- target: {target_id} -->\n\n"
    )
    target_path.write_text(header + assembled_prompt, encoding="utf-8")
    return target_path
