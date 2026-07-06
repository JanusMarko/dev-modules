"""BC4.3 — wire the decision-shape judge into the spec §10.2 decision-recording
negative-space contract.

This is the **skill-layer wiring** (D27: skill-layer / external-model coupling
lives here; the dev-mgmt library never imports the skill and stays pure). The
§10.1 detector descriptor + the events∖records check live in the library
(``negative_space.DECISION_RECORDING_DETECTOR`` /
``negative_space.unrecorded_decisions``); this adapter supplies the JUDGE that
the library's ``DecisionShapeJudge`` Protocol consumes.

**Architecture: cto Option 2 (ruling v3-2142)** — the eval-graded judge is the
LLM-backed :class:`LLMDecisionShapeJudge`, NOT the v1 ``detect`` lexical parser.
Settlement-detection from open prose is a semantic/NLU judgment; the lexical
lineage was the wrong architecture for a judgment unit (it over-fit to visible
cases and failed novel committed-direction constructions at the same edge). The
LLM judge realizes the SAME runtime_checkable Protocol with the SAME signature,
so the structural cert stays valid — only the wired impl swaps lexical→LLM.

The lexical ``DefaultDecisionShapeJudge`` (the library's no-detect_fn fallback +
the v1-reconcile baseline) is retained and exposed via
:func:`lexical_baseline_judge` for reference/comparison; it is no longer the
graded judge.

The decision-shape classification is a JUDGMENT UNIT (RE=yes / OQ-2): the TRUSTED
judge is graded by a FRESH-INDEPENDENT-supplied, @cto-ratified, cold-graded eval
corpus (incl. a sealed holdout = the generalization test). This adapter exposes
the wired judge; it does not author or self-grade the corpus.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Mapping, Sequence

# Make the adjacent skill modules + the dev-mgmt lib importable when this module
# is loaded standalone (tests / direct import), mirroring the skill cli.py guard.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
_LIB = _HERE.parent.parent / "scripts" / "dev-mgmt"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

import detect  # noqa: E402  (path-mutate first by design; lexical baseline only)
import negative_space  # noqa: E402
from llm_decision_judge import LLMDecisionShapeJudge  # noqa: E402

# Re-export the §10.1 descriptor (single source of truth in the library).
DECISION_RECORDING_DETECTOR = negative_space.DECISION_RECORDING_DETECTOR


def decision_shape_judge() -> LLMDecisionShapeJudge:
    """The §10.2 decision-shape judge — the cto-Option-2 LLM-backed judge.

    Returns :class:`LLMDecisionShapeJudge` (temperature=0 + pinned model slug;
    see its ``judge_consistency_protocol``), which classifies settlement
    semantically from the event text. This is the judge the BC4.3 eval corpus
    grades. Its default completer is the Anthropic SDK (the reproducible grade
    backend); inject ``complete`` for offline tests / keyless self-check.
    """
    return LLMDecisionShapeJudge()


def lexical_baseline_judge() -> negative_space.DefaultDecisionShapeJudge:
    """The SUPERSEDED lexical judge (v1 ``detect`` reconcile) — kept for
    reference/comparison only; no longer the eval-graded path (cto Option 2).
    """
    return negative_space.DefaultDecisionShapeJudge(detect_fn=detect.detect)


def unrecorded_decisions(
    events: Sequence[Mapping[str, object]],
    recorded_refs: Sequence[str],
) -> list[Mapping[str, object]]:
    """§10.2 decision-recording detector with the Option-2 LLM judge wired in.

    Convenience over :func:`negative_space.unrecorded_decisions` that supplies
    the LLM-backed judge — flags decision/ratification-shaped events (per the
    semantic classification) with no recorded ``decision`` linked.
    """
    return negative_space.unrecorded_decisions(
        events, recorded_refs, decision_shape_judge()
    )
