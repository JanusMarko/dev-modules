"""4.6i wsl-skill-half — the dual-recording FUNNEL (skill layer, D27).

This is the SKILL/hook layer, NOT the parley-agnostic lib: parley
coupling is permitted HERE and ONLY here (CLAUDE.md Hard Rule 1). The
pure pieces (canonical record-shape, byte-identical projection, the one
deterministic §6->canonical embedding) live in the lib
(`canonical_decision.py`) and are imported; this module adds the
presence-aware parley funnel around them.

Per @plan ruling msg-90ebfe008c87 + Kris's eliminate-by-construction +
presence-aware/independently-degrading clauses:

  Single canonical record; two deterministic projections.

  - The rich §6 WL decision entity (WL-native SUPERSET) is written by
    the lib (`entities.record_decision`) UNCHANGED.
  - The canonical record is the ONE deterministic embedding within it
    (`canonical_decision.extract_canonical`).
  - The wl canonical-projection artifact (`<id>.canonical.md`) is the
    wl-side dual-recording store: ALWAYS written, via the lib's
    byte-identical `project_decision_markdown` (conformance-locked to
    parley's projection at the pinned rev).
  - parley Kind.DECISION store is emitted IFF parley is present
    (presence-gated); its absence silently degrades — the wl artifacts
    are never gated on it, and vice-versa.

  Presence matrix (the wl funnel handles the dev-mgmt-present cells;
  the standalone-parley/no-wl cell is the parley side by construction):
    (i)  both        -> §6 entity + canonical-projection artifact
                        + parley Kind.DECISION store; §6 linked_msg_ids
                        carries the parley msg-id (the §6 provenance
                        backref); parley side carries
                        external_decision_refs dev-mgmt://<slug>.
    (iii) standalone-wl (no parley) -> §6 entity + canonical-projection
                        artifact; no parley store; NO error.

Hard Rule 2: parley NEVER writes wl-cwd; the wl funnel NEVER writes
parley-cwd. The funnel only *calls* the parley decision verb (skill
layer) and materialises wl artifacts in wl-cwd itself.
"""

from __future__ import annotations

import importlib.util
import re
import shutil
import subprocess
import sys
from pathlib import Path

_LIB = Path(__file__).resolve().parents[2] / "scripts" / "dev-mgmt"


def _load(mod_name: str):
    # The dev-mgmt lib dir must be importable: entities.py imports its
    # siblings as top-level modules (`import frontmatter`, `validators`,
    # `templates`, `index`). On the ambient/production path nothing
    # pre-registers them, so put _LIB on sys.path (idempotent) — the
    # same importability the cli.py entrypoint relies on.
    lib = str(_LIB)
    if lib not in sys.path:
        sys.path.insert(0, lib)
    spec = importlib.util.spec_from_file_location(
        mod_name, _LIB / f"{mod_name}.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Presence probe + parley emission (skill layer — parley coupling allowed)
# ---------------------------------------------------------------------------


def parley_present(_probe=None) -> bool:
    """True iff a usable parley session context exists. Skill-layer
    probe (NEVER in the lib). Injectable (`_probe`) for the presence
    matrix test. Any failure => treated as ABSENT (independently
    degrading: the wl artifacts never depend on parley being up).
    """
    if _probe is not None:
        return bool(_probe())
    if shutil.which("parley") is None:
        return False
    try:
        r = subprocess.run(["parley", "whoami"], capture_output=True,
                            timeout=10)
        return r.returncode == 0
    except Exception:
        return False


def emit_parley_decision(canonical, dev_mgmt_slug: str,
                         _emitter=None, *, parley_env=None,
                         parley_session=None) -> dict | None:
    """Emit the parley Kind.DECISION store via the parley decision verb
    (skill layer). Returns the parley response dict (incl `msg_id`) or
    None on absence/any failure (degrade silently — never raise into the
    wl path). Injectable (`_emitter`) for the presence matrix test.

    `parley_env` / `parley_session` (skill-layer, default None = the
    ambient session): when set, the real `parley decision log` is
    invoked with `env=parley_env` and `--session <parley_session>` so
    the funnel emits into a SPECIFIC parley session (the e2e
    both-present cell wires these to @Par's isolated-session harness —
    REAL funnel -> REAL parley, zero ambient/live-session coupling).

    Passes the dev-mgmt slug so the parley side records
    `external_decision_refs: ['dev-mgmt://<slug>']` (the §6
    bidirection); the wl side records the returned parley msg-id into
    the §6 entity's `linked_msg_ids` (the reciprocal backref).
    """
    if _emitter is not None:
        try:
            return _emitter(canonical, dev_mgmt_slug)
        except Exception:
            return None
    # REAL `parley decision log` CLI contract (ground-truthed from
    # parley/cli.py:3062 @ a2bb36d, NOT assumed): positional KIND +
    # flags; stdout is a HUMAN line
    #   "recorded <kind>: '<title>' (by @<by>, chat-injected as msg-XXXX)"
    # (no JSON, no decision_markdown on stdout — the funnel does NOT
    # need parley's projection: it materialises the wl canonical
    # artifact via the lib's conformance-locked re-impl. It needs ONLY
    # the minted msg_id, parsed from the echo.)
    argv = ["parley", "decision", "log", canonical.kind,
            "--title", canonical.title or canonical.text or "(untitled)",
            "--rationale", canonical.rationale,
            "--external-ref", f"dev-mgmt://{dev_mgmt_slug}"]
    for o in canonical.options_considered:
        argv += ["--option", o]
    for l in canonical.links_to:
        argv += ["--links-to", l]
    if canonical.supersedes_id:
        argv += ["--supersedes-id", canonical.supersedes_id]
    if canonical.ref:
        argv += ["--ref", canonical.ref]
    if parley_session:
        argv += ["--session", parley_session]
    try:
        r = subprocess.run(argv, capture_output=True, text=True,
                            timeout=30, env=parley_env)
        if r.returncode != 0:
            return None
        m = re.search(r"chat-injected as (msg-[0-9a-fA-F]+)",
                      r.stdout or "")
        return {"msg_id": m.group(1)} if m else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# The funnel
# ---------------------------------------------------------------------------


def canonical_artifact_path(entity_path: Path) -> Path:
    """Deterministic sibling of the §6 entity: `<id>.canonical.md`."""
    return entity_path.with_suffix(".canonical.md")


def record_decision_dual(
    *,
    title: str,
    rationale: str,
    options: list[dict],
    scope: str,
    author: str,
    repo_root: str | Path | None = None,
    authored_with: list[str] | None = None,
    linked_decisions: list[str] | None = None,
    linked_reviews: list[str] | None = None,
    linked_msg_ids: list[str] | None = None,
    sprint_id: str | None = None,
    stage: str | None = None,
    supersedes: str | None = None,
    status: str = "accepted",
    affects: str | None = None,
    decision_shape: str | None = None,
    _parley_probe=None,
    _parley_emitter=None,
    parley_env=None,
    parley_session=None,
) -> dict:
    """Dual-record: §6 entity (lib, unchanged) + canonical-projection
    artifact (always) + parley Kind.DECISION store (presence-gated).
    Returns {mode, entity_path, canonical_path, parley_msg_id}.
    """
    entities = _load("entities")
    cd = _load("canonical_decision")
    fm = _load("frontmatter")

    linked_msg_ids = list(linked_msg_ids or [])

    # 1. §6 entity — the WL-native superset, written by the lib.
    # Cohort C D2: decision_shape is the OPTIONAL v1-AUTO categorization
    # threaded from the auto-decision-doc skill; None on /record-decision
    # direct (no shape detection layer); validated against the 5-enum at
    # the validator boundary.
    entity_path = entities.record_decision(
        title=title, rationale=rationale, options=options, scope=scope,
        author=author, repo_root=repo_root, authored_with=authored_with,
        linked_decisions=linked_decisions, linked_reviews=linked_reviews,
        linked_msg_ids=linked_msg_ids, sprint_id=sprint_id, stage=stage,
        supersedes=supersedes, status=status, affects=affects,
        decision_shape=decision_shape,
    )
    entity_path = Path(entity_path)
    slug = entity_path.stem  # the §6 id/slug

    # 2. The one deterministic §6 -> canonical embedding (lib, pure).
    created_at = fm.parse(entity_path)[0].get("created_at", "")

    parley_msg_id: str | None = None
    mode = "standalone-wl"

    # 3. parley Kind.DECISION store — presence-gated, independently
    #    degrading. Build the canonical record WITHOUT msg_id first to
    #    feed parley; parley mints the id.
    if parley_present(_parley_probe):
        canon_for_parley = cd.extract_canonical(
            title=title, rationale=rationale, options=options,
            author=author, created_at=created_at, supersedes=supersedes,
            linked_msg_ids=linked_msg_ids, msg_id=None,
        )
        resp = emit_parley_decision(
            canon_for_parley, slug, _parley_emitter,
            parley_env=parley_env, parley_session=parley_session)
        if resp and resp.get("msg_id"):
            parley_msg_id = str(resp["msg_id"])
            mode = "both"
            # §6 reciprocal backref: add the parley msg-id to
            # linked_msg_ids (the §6 provenance-bidirection rule).
            meta, body = fm.parse(entity_path)
            lm = list(meta.get("linked_msg_ids") or [])
            if parley_msg_id not in lm:
                lm.append(parley_msg_id)
                meta["linked_msg_ids"] = lm
                fm.write(entity_path, meta, body)

    # 4. The wl canonical-projection artifact — ALWAYS written, via the
    #    conformance-locked lib re-impl on the ONE canonical record
    #    (msg_id reflects presence: parley-minted in `both`, None in
    #    `standalone-wl` — same record in => same bytes out, the pinned
    #    invariant).
    canonical = cd.extract_canonical(
        title=title, rationale=rationale, options=options, author=author,
        created_at=created_at, supersedes=supersedes,
        linked_msg_ids=linked_msg_ids, msg_id=parley_msg_id,
    )
    canonical_path = canonical_artifact_path(entity_path)
    canonical_path.write_text(
        cd.project_decision_markdown(canonical), encoding="utf-8")

    return {
        "mode": mode,
        "entity_path": str(entity_path),
        "canonical_path": str(canonical_path),
        "parley_msg_id": parley_msg_id,
    }
