"""Orchestration: detect → idempotency-ledger → record_decision_dual.

Skill-layer module. Parley coupling is permitted HERE (and in the funnel
it imports) only; never in the dev-mgmt lib. Hard Rule 2: writes only
member's own cwd (`repo_root` defaults to Path.cwd()).

v1-MANUAL scope (per @plan ratification msg-1c6f11784c82): caller supplies
the body + msg_id + scope + author. Hook auto-trigger deferred until the
manual surface proves out.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import detect as _detect_mod  # type: ignore  # adjacent file (sys.path-augmented)

# Idempotency ledger file (per-repo). One JSONL record per filed msg-id.
LEDGER_NAME = ".auto-filed-msgs.jsonl"


def _load_funnel():
    """Import the record-decision dual-recording funnel.

    The funnel lives at `.claude/skills/record-decision/funnel.py`; we
    spec-load it because it sits in a sibling skill dir (not on the
    pytest sys.path by default).
    """
    skill_dir = Path(__file__).resolve().parent  # auto-decision-doc/
    funnel_path = skill_dir.parent / "record-decision" / "funnel.py"
    spec = importlib.util.spec_from_file_location(
        "auto_decision_doc_funnel", funnel_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["auto_decision_doc_funnel"] = mod
    spec.loader.exec_module(mod)
    return mod


def _ledger_path(repo_root: Path) -> Path:
    return repo_root / "docs" / "decisions" / LEDGER_NAME


def _ledger_lookup(repo_root: Path, msg_id: str) -> dict | None:
    """Return the prior-filed record for msg_id, or None."""
    ledger = _ledger_path(repo_root)
    if not ledger.exists():
        return None
    with ledger.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("msg_id") == msg_id:
                return rec
    return None


def _ledger_append(repo_root: Path, record: dict) -> None:
    ledger = _ledger_path(repo_root)
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\n")


def auto_file_from_msg(
    *,
    msg_id: str,
    body: str,
    scope: str,
    author: str,
    authored_with: list[str] | None = None,
    title_override: str | None = None,
    rationale_override: str | None = None,
    decision_shape_override: str | None = None,
    repo_root: str | Path | None = None,
    dry_run: bool = False,
    min_confidence: str = "medium",
    _funnel=None,
    _detect=None,
    _parley_probe=None,
    _parley_emitter=None,
) -> dict:
    """End-to-end: detect → ledger-check → funnel-call → ledger-append.

    Returns a dict with one of these `status` values:
      - `no_trigger`     : no CTO-RATIFY pattern in body; nothing to do
      - `low_confidence` : trigger but shape too thin; needs manual file
      - `already_filed`  : msg_id present in ledger; skipped (idempotent)
      - `dry_run`        : detection succeeded; would file (not written)
      - `filed`          : §6 entity + canonical-projection (+ parley
                           Kind.DECISION if present) written; ledger
                           appended

    Other keys (present when relevant):
      detection, decision_id, entity_path, canonical_path, parley_msg_id,
      mode (from the funnel).

    Hard Rule 2: writes only `repo_root` (defaults to cwd); never touches
    another member's cwd.
    """
    repo = Path(repo_root) if repo_root else Path.cwd()
    detect_fn = _detect or _detect_mod.detect
    detection = detect_fn(body)

    if not detection.has_trigger:
        return {
            "status": "no_trigger",
            "msg_id": msg_id,
            "detection": _detection_to_dict(detection),
        }

    # Confidence gate.
    confidence_ladder = {"none": 0, "low": 1, "medium": 2, "high": 3}
    have = confidence_ladder.get(detection.confidence, 0)
    need = confidence_ladder.get(min_confidence, 2)
    if have < need:
        return {
            "status": "low_confidence",
            "msg_id": msg_id,
            "detection": _detection_to_dict(detection),
            "confidence": detection.confidence,
            "required": min_confidence,
        }

    # Idempotency check.
    prior = _ledger_lookup(repo, msg_id)
    if prior is not None:
        return {
            "status": "already_filed",
            "msg_id": msg_id,
            "decision_id": prior.get("decision_id"),
            "entity_path": prior.get("entity_path"),
            "filed_at": prior.get("filed_at"),
        }

    # Resolve title + rationale (overrides win).
    title = (title_override or detection.title or "").strip()
    if not title:
        return {
            "status": "low_confidence",
            "msg_id": msg_id,
            "detection": _detection_to_dict(detection),
            "confidence": detection.confidence,
            "required": min_confidence,
            "reason": "title could not be resolved; pass --title-override",
        }
    rationale = (rationale_override or detection.rationale
                 or "(no rationale extracted — see linked msg for context)").strip()

    # Cohort C D2 v1-AUTO — decision_shape resolution. Operator override
    # wins (--decision-shape-override at the CLI); otherwise use the
    # detector's classification (the SHAPE_AMBIGUOUS fallback fires when
    # the body has a trigger but the shape is not resolvable, so an
    # entity always gets a non-None shape when filing — never the absent
    # / null case that signifies "filed pre-D2 OR by /record-decision
    # direct"). The override is validated against the 5-enum to avoid
    # writing a §6-invalid value through to the entity.
    if decision_shape_override is not None:
        if decision_shape_override not in _detect_mod.DECISION_SHAPES:
            return {
                "status": "invalid_shape_override",
                "msg_id": msg_id,
                "detection": _detection_to_dict(detection),
                "decision_shape_override": decision_shape_override,
                "valid_shapes": sorted(_detect_mod.DECISION_SHAPES),
            }
        decision_shape = decision_shape_override
    else:
        decision_shape = detection.decision_shape

    if dry_run:
        return {
            "status": "dry_run",
            "msg_id": msg_id,
            "detection": _detection_to_dict(detection),
            "would_file": {
                "title": title,
                "rationale": rationale,
                "options": detection.options,
                "scope": scope,
                "author": author,
                "authored_with": list(authored_with or []),
                "linked_msg_ids": [msg_id],
                "decision_shape": decision_shape,
                "repo_root": str(repo),
            },
        }

    funnel = _funnel or _load_funnel()
    funnel_kwargs = dict(
        title=title,
        rationale=rationale,
        options=detection.options,
        scope=scope,
        author=author,
        repo_root=repo,
        authored_with=list(authored_with or []),
        linked_msg_ids=[msg_id],
        decision_shape=decision_shape,
    )
    if _parley_probe is not None:
        funnel_kwargs["_parley_probe"] = _parley_probe
    if _parley_emitter is not None:
        funnel_kwargs["_parley_emitter"] = _parley_emitter
    out = funnel.record_decision_dual(**funnel_kwargs)

    entity_path = Path(out["entity_path"])
    decision_id = entity_path.stem
    filed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    ledger_record = {
        "msg_id": msg_id,
        "decision_id": decision_id,
        "entity_path": str(entity_path.relative_to(repo)),
        "filed_at": filed_at,
        "confidence": detection.confidence,
        "mode": out.get("mode"),
    }
    _ledger_append(repo, ledger_record)

    return {
        "status": "filed",
        "msg_id": msg_id,
        "decision_id": decision_id,
        "entity_path": out["entity_path"],
        "canonical_path": out.get("canonical_path"),
        "parley_msg_id": out.get("parley_msg_id"),
        "mode": out.get("mode"),
        "detection": _detection_to_dict(detection),
    }


def _detection_to_dict(d) -> dict:
    out = asdict(d)
    return out
