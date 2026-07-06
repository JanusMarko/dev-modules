"""WL2 certification bars CERT-1/2/3 + the built-artifact predicate
(spec §6 / §6.4 / §6.5; BC3.4 + BC3.5).

The three cert bars are the ``verified → done`` guard for any built artifact
(§6.4), each with a **named check** and each **failing closed** — a bar lacking
its named check is a FAIL, never a silent skip/pass. Plus the §6.5
``produces_built_artifact`` predicate that scopes *whether* the cert conjunct
applies at all.

Kill-axes this module targets:
  * **KA-16** — a cert bar lacking its named check is treated as pass (silent
    skip) → die. Every ``cert{1,2,3}_evaluate`` fails closed on a
    missing/empty named check; :func:`cert_gate` requires all three present
    AND passing.
  * **KA-17** — the cert conjunct is silently skipped for a
    ``produces_built_artifact=true`` task → die. :func:`produces_built_artifact`
    is a deterministic *declared-boolean* read (§6.5: set, not inferred); a
    missing/ambiguous flag is a CP4 declaration-completeness error (raises),
    never a silent ``False`` that would drop the cert conjunct.

Parley-agnostic at base (Hard Rule #1): pure library, no parley import / shell.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence

CERT_BARS: tuple[str, ...] = ("CERT-1", "CERT-2", "CERT-3")


class CertDeclarationError(ValueError):
    """Raised for a CP4 declaration-completeness error (e.g. missing PBA flag)."""


@dataclass(frozen=True)
class CertResult:
    """The outcome of one cert bar (or the conjoined gate).

    ``has_named_check`` is the fails-closed discriminator (KA-16): a bar whose
    named check is absent/empty is **not certifiable** — ``passed`` is forced
    ``False`` regardless of any measured outcome.
    """

    bar: str
    passed: bool
    has_named_check: bool
    reason: str
    detail: tuple[str, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# §6.1 CERT-1 — perf/behavior (Standard S1)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Cert1Row:
    """One NFR row (§6.1). ``threshold_value`` MUST be a number — *no prose
    aspiration is admissible* ("fast" is not certifiable). ``named_check`` is
    ≥1 test/check id; empty ⇒ the row (and CERT-1) fails closed.
    """

    nfr_id: str
    threshold_value: float | int | None
    threshold_unit: str
    condition: str
    named_check: str
    measured_value: float | int | None
    verdict: str  # 'pass' | 'fail'


def cert1_row_violations(row: Cert1Row) -> list[str]:
    """Structural violations of a single CERT-1 row (§6.1, fails closed)."""
    v: list[str] = []
    if not row.named_check:
        v.append(f"{row.nfr_id}: no named_check (a bar with no named check does not certify)")
    if not isinstance(row.threshold_value, (int, float)) or isinstance(row.threshold_value, bool):
        v.append(f"{row.nfr_id}: threshold not a number (prose aspiration inadmissible)")
    if row.verdict not in ("pass", "fail"):
        v.append(f"{row.nfr_id}: verdict must be 'pass'|'fail', got {row.verdict!r}")
    return v


def cert1_evaluate(rows: Sequence[Cert1Row]) -> CertResult:
    """Evaluate CERT-1 (§6.1).

    Pass rule: **every** row has a named check + numeric threshold, and every
    row's ``verdict == 'pass'``. Any row missing a named check → CERT-1 fails
    closed. A no-row CERT-1 is vacuously satisfied but carries
    ``has_named_check=True`` only if it is genuinely empty (nothing to certify).
    """
    all_violations: list[str] = []
    for row in rows:
        all_violations.extend(cert1_row_violations(row))
    has_named_check = all(bool(row.named_check) for row in rows)
    if all_violations:
        return CertResult("CERT-1", False, has_named_check,
                          "CERT-1 fails closed", tuple(all_violations))
    failing = [row.nfr_id for row in rows if row.verdict != "pass"]
    if failing:
        return CertResult("CERT-1", False, True,
                          f"CERT-1 rows did not meet threshold: {failing}",
                          tuple(failing))
    return CertResult("CERT-1", True, True, "all NFR rows pass with named checks")


# ---------------------------------------------------------------------------
# §6.2 CERT-2 — normative-clause coverage matrix (Standard S2)
# ---------------------------------------------------------------------------


def cert2_evaluate(
    clause_to_verifications: Mapping[str, Sequence[str]],
) -> CertResult:
    """Evaluate CERT-2 (§6.2): 100% normative-clause → verification coverage.

    The gate **fails if any clause maps to ∅** (no verification). Completeness
    is the named check (the coverage-matrix completeness linter
    ``clauses ∖ mapped = ∅``). An empty matrix means there is *no* completeness
    check → fails closed (``has_named_check=False``).
    """
    if not clause_to_verifications:
        return CertResult("CERT-2", False, False,
                          "CERT-2 has no coverage matrix (no named check) — fails closed")
    unmapped = sorted(
        clause for clause, verifs in clause_to_verifications.items()
        if not verifs
    )
    if unmapped:
        return CertResult("CERT-2", False, True,
                          f"{len(unmapped)} normative clause(s) unmapped",
                          tuple(unmapped))
    return CertResult("CERT-2", True, True, "100% normative-clause coverage")


# ---------------------------------------------------------------------------
# §6.3 CERT-3 — cert-isolation (Standard S3)
# ---------------------------------------------------------------------------


def cert3_evaluate(regression_delta: int | None) -> CertResult:
    """Evaluate CERT-3 (§6.3): regression-delta = 0 under hard isolation.

    The isolated run must add **zero** new failures vs the recorded baseline.
    A ``None`` delta means the isolation harness clean-run report is absent (no
    named check) → fails closed.
    """
    if regression_delta is None:
        return CertResult("CERT-3", False, False,
                          "CERT-3 has no isolation clean-run report (no named check) — fails closed")
    if regression_delta != 0:
        return CertResult("CERT-3", False, True,
                          f"regression-delta = {regression_delta} (must be 0)")
    return CertResult("CERT-3", True, True, "regression-delta = 0 under isolation")


# ---------------------------------------------------------------------------
# §6.4 cert wiring — CERT-1 ∧ CERT-2 ∧ CERT-3, fails closed
# ---------------------------------------------------------------------------


def cert_gate(
    cert1: CertResult | None,
    cert2: CertResult | None,
    cert3: CertResult | None,
) -> CertResult:
    """Conjoin the three bars (§6.4): **CERT-1 ∧ CERT-2 ∧ CERT-3 must all pass**.

    Fails closed if any bar is **absent** (``None``) or **lacks its named
    check** (KA-16) — a missing bar is never a silent pass. The conjoined
    ``has_named_check`` is the AND of the three.
    """
    bars = {"CERT-1": cert1, "CERT-2": cert2, "CERT-3": cert3}
    missing_bar = [name for name, r in bars.items() if r is None]
    if missing_bar:
        return CertResult("CERT", False, False,
                          f"cert bar(s) absent (fails closed): {missing_bar}",
                          tuple(missing_bar))
    results = [cert1, cert2, cert3]
    no_check = [r.bar for r in results if not r.has_named_check]  # type: ignore[union-attr]
    if no_check:
        return CertResult("CERT", False, False,
                          f"cert bar(s) lacking named check (fails closed): {no_check}",
                          tuple(no_check))
    failed = [r.bar for r in results if not r.passed]  # type: ignore[union-attr]
    if failed:
        return CertResult("CERT", False, True,
                          f"cert bar(s) failed: {failed}", tuple(failed))
    return CertResult("CERT", True, True, "CERT-1 ∧ CERT-2 ∧ CERT-3 all pass")


# ---------------------------------------------------------------------------
# §6.5 built-artifact predicate — cert-scope
# ---------------------------------------------------------------------------

PBA_FIELD = "produces_built_artifact"


def produces_built_artifact(task: Mapping[str, object]) -> bool:
    """Deterministic §6.5 ``produces_built_artifact`` decision.

    The flag is **declared** at task/kind declaration (set, not auto-inferred) —
    exactly like ``requires_eval``. ``true`` ⇔ a constructed/executable
    deliverable (code, binary, package, schema, generated config, deployable);
    ``false`` ⇔ a pure-judgment/prose/decision/review artifact nothing executes.

    A **missing or non-boolean** flag is a CP4 declaration-completeness error
    (raises :class:`CertDeclarationError`) — never a silent ``False`` that would
    drop the cert conjunct (KA-17). Per §6.5 this is caught **before
    ``picked-up``**, not judged at acceptance.
    """
    if PBA_FIELD not in task:
        raise CertDeclarationError(
            f"{PBA_FIELD} not declared (CP4 declaration-completeness error; "
            f"§6.5 requires it set at declaration, caught before picked-up)"
        )
    val = task[PBA_FIELD]
    if not isinstance(val, bool):
        raise CertDeclarationError(
            f"{PBA_FIELD} must be a declared boolean, got {val!r} "
            f"(ambiguous flag is a CP4 error, not a gate-time judgment)"
        )
    return val


def cert_conjunct_applies(task: Mapping[str, object]) -> bool:
    """Whether the §11.4 cert conjunct is **present** for this task (§6.5).

    Present IFF ``produces_built_artifact == true`` — a clerk-checkable ``when:``
    predicate, no semantic interpretation at the gate. ``false`` ⇒ the cert
    conjunct is simply absent (review ∧ SoD still bind); it is **never** silently
    skipped for a ``true`` task (KA-17 / fails-closed).
    """
    return produces_built_artifact(task)
