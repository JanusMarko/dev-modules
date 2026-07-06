"""WL2 verified→done acceptance composition (spec §11.4; BC3.7).

The ``verified → done`` edge fires IFF **review ∧ SoD ∧ eval ∧ cert** all hold,
most-restrictive-binds, and **a missing conjunct fails closed** (§11.4). The
pure conjunction engine lives in :mod:`lifecycle` (BC2 — ``attempt_transition``
+ ``acceptance_missing_conjuncts``); this module is the BC3 **composing layer**
that feeds it the *real* conjunct signals:

  * **SoD** — the C7 immovable floor (§12 / :mod:`acceptance_class`): on a
    SHIP/EXTERNAL/IRREVERSIBLE-tagged acceptance the opt-out is rejected.
  * **eval** — the §5 eval gate (:mod:`eval_corpus`), self-scoped by
    ``requires_eval``: a required-but-absent/failing corpus ⇒ conjunct unmet.
  * **cert** — the §6 cert bars (:mod:`cert`), self-scoped by the §6.5
    ``produces_built_artifact`` predicate (KA-17 teeth: the predicate RAISES on
    a missing/ambiguous flag rather than silently dropping the conjunct).

Kill-axis: **KA-21** — ``verified → done`` firing with a missing conjunct
(review/SoD/eval/cert) → die. The conjunction fails closed because an applicable
conjunct whose signal is ``None``/``False`` counts as UNMET (no silent pass, C6).

Parley-agnostic at base (Hard Rule #1): pure library, no parley import / shell.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence

import acceptance_class
import cert_bars as cert
import eval_corpus
import lifecycle


@dataclass(frozen=True)
class AcceptanceSignals:
    """The raw acceptance inputs the BC3 gates evaluate into the conjunction.

    * ``review_signed`` — the review conjunct (always applies).
    * ``sod_signed`` / ``sod_opt_out`` — SoD signed, and whether an
      override-authority opted out (rejected on a tagged acceptance, §12).
    * ``eval_corpus`` / ``eval_builder_role`` / ``eval_case_results`` — fed to
      the §5 eval gate when ``requires_eval``.
    * ``cert1`` / ``cert2`` / ``cert3`` — the three §6 cert-bar results, conjoined
      when ``produces_built_artifact``.
    * ``acceptance_handler`` — recorded on a ``gate-refused`` denial.
    """

    review_signed: bool
    sod_signed: bool
    sod_opt_out: bool = False
    eval_corpus: Mapping[str, object] | None = None
    eval_builder_role: str | None = None
    eval_case_results: Sequence["eval_corpus.CaseResult"] = field(default_factory=tuple)
    cert1: "cert.CertResult | None" = None
    cert2: "cert.CertResult | None" = None
    cert3: "cert.CertResult | None" = None
    acceptance_handler: str | None = None


def _eval_pass(task: Mapping[str, object], s: AcceptanceSignals) -> bool | None:
    """Resolve the eval conjunct signal (self-scoped by ``requires_eval``).

    Returns ``None`` when the conjunct does not apply. When it applies, returns
    the eval-gate verdict; a **required-but-absent** corpus ⇒ ``False`` (the
    conjunct is unmet — fails closed, never a silent pass).
    """
    if not bool(task.get("requires_eval")):
        return None
    if s.eval_corpus is None:
        return False
    return eval_corpus.eval_gate(
        s.eval_corpus,
        builder_role=s.eval_builder_role,
        case_results=s.eval_case_results,
    ).ok


def _cert_pass(task: Mapping[str, object], s: AcceptanceSignals) -> bool | None:
    """Resolve the cert conjunct signal (self-scoped by §6.5 PBA predicate).

    Uses :func:`cert.cert_conjunct_applies` — the deterministic declared-boolean
    read that **raises** on a missing/ambiguous flag (KA-17: never a silent skip
    for a ``true`` task). Returns ``None`` when the conjunct does not apply; else
    the conjoined CERT-1 ∧ CERT-2 ∧ CERT-3 verdict (a missing bar fails closed).
    """
    if not cert.cert_conjunct_applies(task):
        return None
    return cert.cert_gate(s.cert1, s.cert2, s.cert3).passed


def evaluate_acceptance(
    task: Mapping[str, object],
    signals: AcceptanceSignals,
) -> lifecycle.TransitionResult:
    """Evaluate the §11.4 ``verified → done`` acceptance, composing the BC3 gates.

    Resolves each conjunct's signal from the real gates (C7-SoD / eval / cert),
    then delegates to :func:`lifecycle.attempt_transition` — the canonical
    conjunction engine. On any unmet applicable conjunct the result is a
    ``gate-refused`` denial that leaves the task ``verified`` (§11.4 / §9.3
    stays-put); only an all-conjuncts-hold result fires the edge to ``done``.
    """
    effective_sod = acceptance_class.effective_sod_holds(
        sod_signed=signals.sod_signed,
        sod_opt_out=signals.sod_opt_out,
        acceptance_classes=acceptance_class.read_acceptance_classes(task),
    )
    return lifecycle.attempt_transition(
        task,
        "done",
        review=signals.review_signed,
        sod=effective_sod,
        eval_pass=_eval_pass(task, signals),
        cert_pass=_cert_pass(task, signals),
        acceptance_handler=signals.acceptance_handler,
    )
