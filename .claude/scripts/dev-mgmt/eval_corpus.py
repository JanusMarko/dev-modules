"""WL2 eval-corpus / eval-case structural gate (spec §5; BC3.3).

The behavioral acceptance bar for a judgment component, plus the **gate** that
enforces — structurally — what makes a corpus a *real* acceptance bar rather
than a self-graded test. This is the BC3 HARD PART. Two invariants the cohort's
kill-axes target:

  * **KA-13 — `independent_supplier ≠ builder(target_component)`** (§5.1 / SoD,
    DOC1 §12). A corpus authored by the component's own builder is not an
    independent bar; it is rejected.
  * **KA-14 — disqualifying axes are NEVER averaged into the aggregate** (§5.1 /
    evals-first §2.6 / Hard Rule 7). Each disqualifying axis is **hard-fail**:
    failing any one fails the corpus *regardless of the aggregate score*, and a
    disqualifying-axis result is never folded into the aggregate mean. A scorer
    that averages a disqualifying fail into a passing aggregate is the mutant
    that must die.
  * **KA-15 — red-proof present ∧ holdout sealed ∧ human-ratification non-null**
    (§5.1). A corpus missing any of these does NOT satisfy the §11.4
    `verified → done` eval conjunct (fails closed, C6).

The gate result feeds the §11.4 acceptance conjunction (``eval_pass``): a corpus
satisfies the eval conjunct IFF it is structurally valid **and** its scoring
passes. Both legs must hold — neither is a silent pass.

Parley-agnostic at base (Hard Rule #1): pure library, no parley import / shell.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence

# §5.2 eval-case categories — a conformant corpus carries cases across all four.
CASE_CATEGORIES: frozenset[str] = frozenset(
    {"happy", "edge", "adversarial", "off-topic-decline"}
)
SCORING_MODES: frozenset[str] = frozenset(
    {"deterministic-key", "rubric", "model-judge"}
)


class EvalGateError(ValueError):
    """Raised for a structurally-malformed scoring request (programming error)."""


# ---------------------------------------------------------------------------
# Structural validation of the corpus record (§5.1)
# ---------------------------------------------------------------------------


def corpus_structure_violations(
    corpus: Mapping[str, object],
    *,
    builder_role: str | None,
) -> list[str]:
    """Return the list of §5.1 structural violations for an eval-corpus record.

    Empty list ⇒ the corpus is a structurally-valid acceptance bar. Each check
    fails closed: a missing/empty field is a violation, never a silent pass (C6).

    Checks:
      * **KA-13** ``independent_supplier`` present AND ``≠ builder_role`` (the
        component's builder). A null/empty supplier, or a supplier equal to the
        builder, is a violation.
      * **KA-14** ``pass_bar.disqualifying_axes`` is a present list, kept
        **separate** from ``pass_bar.aggregate`` (the data shape that makes
        never-averaging enforceable — the scorer reads them as distinct).
      * **KA-15a** ``red_without_proof`` present with ``recorded_result == 'fail'``.
      * **KA-15b** ``holdout`` present with ``sealed == True``.
      * **KA-15c** ``human_ratification`` non-null (both ``ratified_by`` and
        ``ratified_at`` present + non-empty).
    """
    v: list[str] = []

    supplier = corpus.get("independent_supplier")
    if not supplier:
        v.append("independent_supplier missing/empty")
    elif builder_role is not None and supplier == builder_role:
        v.append(
            f"independent_supplier == builder ({supplier!r}); must be distinct "
            f"(KA-13 / SoD §5.1)"
        )

    pass_bar = corpus.get("pass_bar")
    if not isinstance(pass_bar, Mapping):
        v.append("pass_bar missing or not a mapping")
    else:
        if "aggregate" not in pass_bar or pass_bar.get("aggregate") in (None, ""):
            v.append("pass_bar.aggregate missing/empty")
        axes = pass_bar.get("disqualifying_axes")
        if not isinstance(axes, (list, tuple)):
            v.append("pass_bar.disqualifying_axes missing or not a list")

    red = corpus.get("red_without_proof")
    if not isinstance(red, Mapping):
        v.append("red_without_proof missing or not a mapping")
    elif red.get("recorded_result") != "fail":
        v.append(
            "red_without_proof.recorded_result must be 'fail' (a pass against a "
            "stubbed/absent component means the corpus proves nothing; KA-15)"
        )

    holdout = corpus.get("holdout")
    if not isinstance(holdout, Mapping):
        v.append("holdout missing or not a mapping")
    elif holdout.get("sealed") is not True:
        v.append("holdout.sealed must be True (KA-15)")

    ratification = corpus.get("human_ratification")
    if not isinstance(ratification, Mapping):
        v.append("human_ratification missing or not a mapping")
    else:
        if not ratification.get("ratified_by"):
            v.append("human_ratification.ratified_by missing/empty (KA-15)")
        if not ratification.get("ratified_at"):
            v.append("human_ratification.ratified_at missing/empty (KA-15)")

    return v


# ---------------------------------------------------------------------------
# Structural validation of an eval-case record (§5.2)
# ---------------------------------------------------------------------------


def case_structure_violations(case: Mapping[str, object]) -> list[str]:
    """Return the list of §5.2 structural violations for an eval-case record.

    Empty list ⇒ the case is structurally valid. Checks (fail closed):
      * ``corpus_ref`` present (the parent eval-corpus).
      * ``category`` ∈ {happy, edge, adversarial, off-topic-decline}.
      * ``observable_inputs`` present (a mapping; **observable-only, no label
        leakage** — the gate enforces presence + shape, the no-leakage guarantee
        is an authoring discipline this records the slot for).
      * ``scoring_key`` present (a mapping; **held-out** — not visible to the
        component under test).
      * ``in_holdout`` if present must be a bool.
    """
    v: list[str] = []
    if not case.get("corpus_ref"):
        v.append("corpus_ref missing/empty")
    category = case.get("category")
    if category not in CASE_CATEGORIES:
        v.append(
            f"category must be one of {sorted(CASE_CATEGORIES)}, got {category!r}"
        )
    if not isinstance(case.get("observable_inputs"), Mapping):
        v.append("observable_inputs missing or not a mapping")
    if not isinstance(case.get("scoring_key"), Mapping):
        v.append("scoring_key missing or not a mapping (held-out)")
    if "in_holdout" in case and not isinstance(case.get("in_holdout"), bool):
        v.append("in_holdout must be a bool")
    return v


def missing_case_categories(cases: Sequence[Mapping[str, object]]) -> frozenset[str]:
    """Return the §5.2 categories NOT represented across ``cases``.

    A conformant corpus carries cases across **all four** categories — in
    particular ``off-topic-decline`` proves the component declines out-of-scope
    inputs rather than over-answering (§5.2). ∅ ⇒ all four present.
    """
    present = {c.get("category") for c in cases}
    return frozenset(CASE_CATEGORIES - present)


# ---------------------------------------------------------------------------
# Scoring — disqualifying axes NEVER averaged (§5.1 / KA-14)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CaseResult:
    """One scored eval-case outcome.

    * ``case_id`` — the eval-case id.
    * ``passed`` — whether the component took the right action on this case.
    * ``disqualifying_axis`` — if set, this case exercises a named
      **disqualifying axis** (§5.1). Such a case is **never** counted in the
      aggregate, and a fail on it **hard-fails** the corpus.
    """

    case_id: str
    passed: bool
    disqualifying_axis: str | None = None


@dataclass(frozen=True)
class ScoreResult:
    passed: bool
    reason: str
    aggregate_score: float | None  # fraction of non-disqualifying cases passing
    disqualifying_failures: tuple[str, ...] = field(default_factory=tuple)


def score_corpus(
    *,
    aggregate_threshold: float,
    disqualifying_axes: Sequence[str],
    case_results: Sequence[CaseResult],
) -> ScoreResult:
    """Score a corpus run, **never averaging a disqualifying axis** (§5.1/KA-14).

    Algorithm (most-restrictive-binds):
      1. **Disqualifying gate first.** Any ``CaseResult`` whose
         ``disqualifying_axis`` is one of ``disqualifying_axes`` and which
         ``passed == False`` HARD-FAILS the corpus — *regardless of the
         aggregate*. These cases are reported in ``disqualifying_failures``.
      2. **Aggregate over non-disqualifying cases only.** The aggregate score is
         ``passing / total`` over cases that are **not** on a disqualifying axis.
         A disqualifying-axis result is never in the numerator or denominator —
         it cannot be averaged into a pass.
      3. Corpus passes IFF no disqualifying failure AND
         ``aggregate_score >= aggregate_threshold``.

    With no non-disqualifying cases the aggregate is vacuously satisfied (the
    disqualifying gate alone decides) — ``aggregate_score`` is ``None``.
    """
    if not (0.0 <= aggregate_threshold <= 1.0):
        raise EvalGateError(
            f"aggregate_threshold must be in [0,1], got {aggregate_threshold!r}"
        )
    dq_set = set(disqualifying_axes)

    disqualifying_failures = tuple(
        cr.disqualifying_axis  # type: ignore[misc]
        for cr in case_results
        if cr.disqualifying_axis in dq_set and not cr.passed
    )

    non_dq = [cr for cr in case_results if cr.disqualifying_axis not in dq_set]
    if non_dq:
        aggregate_score: float | None = sum(1 for cr in non_dq if cr.passed) / len(non_dq)
    else:
        aggregate_score = None

    if disqualifying_failures:
        return ScoreResult(
            passed=False,
            reason=(
                "disqualifying-axis fail hard-fails the corpus regardless of "
                f"aggregate: {sorted(set(disqualifying_failures))}"
            ),
            aggregate_score=aggregate_score,
            disqualifying_failures=disqualifying_failures,
        )

    if aggregate_score is not None and aggregate_score < aggregate_threshold:
        return ScoreResult(
            passed=False,
            reason=(
                f"aggregate {aggregate_score:.3f} < threshold "
                f"{aggregate_threshold:.3f} over non-disqualifying cases"
            ),
            aggregate_score=aggregate_score,
        )

    return ScoreResult(
        passed=True,
        reason="no disqualifying failure; aggregate meets threshold",
        aggregate_score=aggregate_score,
    )


# ---------------------------------------------------------------------------
# The gate — structural validity ∧ scoring pass (feeds §11.4 eval conjunct)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EvalGateResult:
    ok: bool
    structure_violations: tuple[str, ...]
    score: ScoreResult | None
    reason: str


def eval_gate(
    corpus: Mapping[str, object],
    *,
    builder_role: str | None,
    case_results: Sequence[CaseResult],
) -> EvalGateResult:
    """The eval conjunct of the §11.4 ``verified → done`` gate.

    A corpus satisfies the eval conjunct IFF **both**: (1) it is structurally
    valid (:func:`corpus_structure_violations` returns ∅ — supplier-independence,
    red-proof, sealed holdout, human-ratification) AND (2) its scoring passes
    (:func:`score_corpus` — no disqualifying-axis fail, aggregate meets
    threshold). Structural violations short-circuit (a malformed bar cannot be
    "passed"); the result feeds ``eval_pass`` into ``lifecycle.attempt_transition``.
    """
    violations = corpus_structure_violations(corpus, builder_role=builder_role)
    if violations:
        return EvalGateResult(
            ok=False,
            structure_violations=tuple(violations),
            score=None,
            reason="corpus structurally invalid: " + "; ".join(violations),
        )

    pass_bar = corpus["pass_bar"]
    assert isinstance(pass_bar, Mapping)  # guaranteed by passing structure check
    threshold = _coerce_threshold(pass_bar.get("aggregate"))
    axes = [str(a) for a in (pass_bar.get("disqualifying_axes") or [])]

    score = score_corpus(
        aggregate_threshold=threshold,
        disqualifying_axes=axes,
        case_results=case_results,
    )
    return EvalGateResult(
        ok=score.passed,
        structure_violations=(),
        score=score,
        reason=score.reason,
    )


def _coerce_threshold(aggregate: object) -> float:
    """Coerce a ``pass_bar.aggregate`` value to a [0,1] fraction.

    Accepts a bare fraction (``0.9``), a percentage number (``90`` ⇒ ``0.9``),
    or a mapping carrying ``{threshold | value | fraction | percent}``. The
    aggregate's *condition* prose ("of non-disqualifying cases") is honoured by
    :func:`score_corpus`'s denominator, not parsed from text here.
    """
    if isinstance(aggregate, Mapping):
        for key in ("fraction", "threshold", "value"):
            if key in aggregate:
                return _coerce_threshold(aggregate[key])
        if "percent" in aggregate:
            return float(aggregate["percent"]) / 100.0  # type: ignore[arg-type]
        raise EvalGateError(f"pass_bar.aggregate mapping lacks a threshold key: {aggregate!r}")
    if isinstance(aggregate, bool):
        raise EvalGateError("pass_bar.aggregate must be a number, got bool")
    if isinstance(aggregate, (int, float)):
        val = float(aggregate)
        return val / 100.0 if val > 1.0 else val
    raise EvalGateError(
        f"pass_bar.aggregate must be a number or threshold mapping, got {aggregate!r}"
    )
