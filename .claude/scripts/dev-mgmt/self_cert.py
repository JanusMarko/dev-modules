"""WL2 self-certification over its OWN spec (spec §6 / §6.2 / §6.4; BC6.2 + BC6.4).

BC6 is the TERMINAL acceptance of build-wave-1: it self-certifies the whole
shipped WL2 product against its own field-level spec. This module is the
**CERT-2 normative-clause coverage matrix** (§6.2 / build-plan App B) plus the
**full self-cert run** (§6.4: CERT-1 ∧ CERT-2 ∧ CERT-3), composed on the BC3
``cert_bars`` primitives.

Kill-axes (build-plan App B):
  * **KA-matrix** (§6.2) — a normative spec clause with NO kill-axis passes
    CERT-2 (coverage < 100%) → die. :data:`CERT2_AXES` is the spec-declared
    enumeration of WL2's normative-clause obligations (App B's clause×axis
    rows); :func:`evaluate_cert2` runs the completeness linter
    (``obligations ∖ mapped = ∅``) and **fails closed** on any obligation with
    no named check.
  * **KA-16** (§6/§6.4) — a cert bar lacking its named check is treated as pass
    (silent skip) → die. :func:`self_cert` conjoins the three bars via
    :func:`cert_bars.cert_gate`, which fails closed on an absent bar or a bar
    with no named check.

This is a **structural / deterministic** check (RE=no): the normative-clause set
is the spec author's OWN exhaustive enumeration (§A.1's clause classes + App B's
clause×axis matrix), transcribed here as data. CERT-2 checks **presence** — every
declared obligation maps to ≥1 named verification id — and **fails closed**. It
does NOT *grade* whether a verification is adequate (that would be a judgment /
RE=yes call); it checks the mapping is complete. Per §6.2 the named check is the
"coverage-matrix completeness linter (clauses ∖ mapped = ∅)" — completeness, not
execution (execution is CERT-1's green-suite + CERT-3's regression-delta).

Parley-agnostic at base (Hard Rule #1): pure library, no parley import / shell.
"""
from __future__ import annotations

from dataclasses import dataclass

import cert_bars
from cert_bars import CertResult


# ---------------------------------------------------------------------------
# §6.2 CERT-2 — the clause×axis coverage matrix (build-plan App B, transcribed).
# Each row = one in-scope normative-clause obligation, its mutation-kill axis,
# the cohort that lands it, and ≥1 named check. An obligation with no named
# check is a dirty matrix → CERT-2 fails closed (KA-matrix).
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ClauseAxis:
    """One normative-clause obligation (App B row): a clause anchored in the
    spec, its mutation-kill axis, and the named check(s) that verify it."""

    ka_id: str
    clause_ref: str
    axis: str          # the mutation-kill statement ("mutant: X → die")
    cohort: str
    named_checks: tuple[str, ...]

    @property
    def obligation_id(self) -> str:
        """The unique normative-clause-obligation key (``KA-n §x``)."""
        return f"{self.ka_id} {self.clause_ref}"


CERT2_AXES: tuple[ClauseAxis, ...] = (
    ClauseAxis("KA-1", "§1.3", "catalog declares ≠20 kinds → die", "BC0",
               ("test_catalog.py::test_kind_set_closed_20",)),
    ClauseAxis("KA-2", "§1.4", "a kind missing a state/transition/path/schema validates → die", "BC0",
               ("test_catalog.py::test_per_kind_declaration_complete",)),
    ClauseAxis("KA-3", "§1.4/§5.3/§6.5", "requires_eval/produces_built_artifact inferred at gate, or missing-flag passes → die", "BC0",
               ("test_eval_scope.py::test_requires_eval_declared",)),
    ClauseAxis("KA-4", "§2.3", "a required field absent yet record validates → die", "BC1",
               ("test_schemas.py::test_<kind>_required_fields",)),
    ClauseAxis("KA-5", "§2.3", "owner_user on a non-carry kind or absent on a carry kind passes → die", "BC1",
               ("test_schemas.py::test_owner_user_carry_set",)),
    ClauseAxis("KA-6", "§2.4", "a binding points at the wrong parley kind/field → die", "BC5",
               ("inherited(N3 25115f0)", "test_consumed_shapes.py::test_binding_targets")),
    ClauseAxis("KA-7", "§2.4/§11.3", "completed maps to anything but done (or superseded/abandoned remapped) → die", "BC2/BC5",
               ("test_consumed_shapes.py::test_disposition_outcome_map",)),
    ClauseAxis("KA-8", "§3.1", "an 8th verb accepted / emit w/o idempotency_key passes / unknown op ≠ unknown_verb → die", "BC5",
               ("inherited(N1 979f8e6)", "test_interface_conformance.py")),
    ClauseAxis("KA-9", "§3.1", "WL2 overrides a present platform value → die", "BC5",
               ("test_interface_conformance.py::test_provide_when_absent",)),
    ClauseAxis("KA-10", "§4.2", "build-plan reaches ready-to-execute with an uncovered requirement → die", "BC3",
               ("test_coverage_gate.py::test_q1_undercovered",)),
    ClauseAxis("KA-11", "§4.2", "an authorizing record tracing to no requirement passes → die", "BC3",
               ("test_coverage_gate.py::test_q2_rogue",)),
    ClauseAxis("KA-fulfill", "§4.3", "a spec/epic reports fully_built while a contained requirement is uncovered → die", "BC3",
               ("test_coverage_gate.py::test_fulfillment_rollup",)),
    ClauseAxis("KA-12", "§4.5", "an untyped edge defaults to non-FS, or a lag/lead qualifier is ignored → die", "BC3",
               ("test_dependencies.py::test_ordering_edge_types",)),
    ClauseAxis("KA-13", "§5.1", "an eval-corpus whose independent_supplier == builder validates → die", "BC3",
               ("test_eval_corpus.py::test_independent_supplier",)),
    ClauseAxis("KA-14", "§5.1", "a disqualifying-axis fail averaged into the aggregate yields a pass → die", "BC3",
               ("test_eval_corpus.py::test_disqualifying_not_averaged",)),
    ClauseAxis("KA-15", "§5.1", "a corpus w/ no red-proof, unsealed holdout, or null ratification satisfies verified→done → die", "BC3",
               ("test_eval_corpus.py::test_red_without",
                "test_eval_corpus.py::test_holdout_sealed",
                "test_eval_corpus.py::test_human_ratified")),
    ClauseAxis("KA-16", "§6/§6.4", "a cert bar lacking its named check is treated as pass (silent skip) → die", "BC3/BC6",
               ("test_self_cert.py::test_cert_fails_closed",
                "test_cert_builder_cert.py")),
    ClauseAxis("KA-17", "§6.5", "the cert conjunct is silently skipped for a produces_built_artifact=true task → die", "BC0/BC3",
               ("test_self_cert.py::test_built_artifact_predicate",
                "test_cert_builder_cert.py")),
    ClauseAxis("KA-18", "§7", "a kind_registration reaches active with either gate failing → die", "BC5",
               ("inherited(N2 b932c6a)", "test_registry.py::test_cp4_composes")),
    ClauseAxis("KA-19", "§9", "a denial transitions its subject, or raised_by==handler validates → die", "BC2",
               ("test_denial.py::test_envelope",
                "test_denial.py::test_raised_by_handler",
                "test_denial.py::test_stays_put")),
    ClauseAxis("KA-20", "§10", "an advisory gate ships with no negative-space detector yet passes conformance → die", "BC4",
               ("test_negative_space.py::test_per_gate_detector",)),
    ClauseAxis("KA-21", "§11.1/§11.4", "verified→done fires with a missing conjunct (review/SoD/eval/cert) → die", "BC2/BC3",
               ("test_lifecycle.py::test_r6_edges",
                "test_lifecycle.py::test_acceptance_conjunction")),
    ClauseAxis("KA-22", "§11.2", "created→picked-up fires with an unmet prerequisite → die", "BC2",
               ("test_lifecycle.py::test_work_readiness",)),
    ClauseAxis("KA-23", "§11.5", "a wait_for with no TTL validates, or a blocked+claimed role reads working → die", "BC2",
               ("test_block_signal.py::test_classes",
                "test_block_signal.py::test_ttl",
                "test_block_signal.py::test_attention_precedence")),
    ClauseAxis("KA-24", "§12", "a SoD opt-out is accepted on a SHIP/EXTERNAL/IRREVERSIBLE acceptance, or assigner==builder validates → die", "BC3",
               ("test_sod.py::test_c7_immovable",
                "test_sod.py::test_assigner_not_builder")),
    ClauseAxis("KA-25", "§2.3", "a same-layer peer-tie is silently merged or resolved positionally (not conflicts-with) → die", "BC1",
               ("test_library.py::test_collision_resolver",)),
    ClauseAxis("KA-26", "§13", "a field with no Workshop destination (orphan) passes the importability check → die", "BC6",
               ("test_importability.py::test_maps_to_complete",
                "test_importability.py::test_no_orphan_field")),
    ClauseAxis("KA-keepgreen", "§C.6", "a relocation commit drops the suite below the recorded baseline → die", "BC0",
               ("the recorded-baseline suite run at each relocation commit",)),
    ClauseAxis("KA-continuity", "§10.2/§11.6", "an arc-close event with no continuity record passes silently → die", "BC2/BC4",
               ("test_negative_space.py::test_continuity_detector",)),
    ClauseAxis("KA-fence", "§0.1/§C.7", "a fenced wire is frozen/built against an un-published parley surface → die", "BC7",
               ("the pre-bind publish-state check (no-freeze-before-publish)",)),
)

# The spec-declared normative-clause obligation set (§6.2 universe). Derived from
# the App B matrix — the spec author's OWN exhaustive enumeration (§A.1 classes +
# keep-green/continuity/fence disciplines). CERT-2 must cover 100% of these.
NORMATIVE_OBLIGATIONS: frozenset[str] = frozenset(ax.obligation_id for ax in CERT2_AXES)


def cert2_matrix() -> dict[str, tuple[str, ...]]:
    """The CERT-2 coverage map: ``obligation_id → named_check[]`` over every
    declared normative-clause obligation."""
    return {ax.obligation_id: ax.named_checks for ax in CERT2_AXES}


def evaluate_cert2(
    matrix: dict[str, tuple[str, ...]] | None = None,
) -> CertResult:
    """Run CERT-2 (§6.2): the coverage-matrix completeness linter over the
    spec-declared normative-clause obligation set.

    Fails closed (via :func:`cert_bars.cert2_evaluate`) if any declared
    obligation maps to ∅ (no named check), i.e. coverage < 100%.
    """
    matrix = cert2_matrix() if matrix is None else matrix
    # Evaluate over the DECLARED obligation universe: an obligation absent from
    # the matrix surfaces as an empty mapping (∅), caught as unmapped.
    full = {ob: matrix.get(ob, ()) for ob in NORMATIVE_OBLIGATIONS}
    return cert_bars.cert2_evaluate(full)


@dataclass(frozen=True)
class Cert2MatrixReport:
    """The §6.2 CERT-2 completeness verdict + traceability counts."""

    passed: bool
    n_obligations: int
    n_named_checks: int
    unmapped: tuple[str, ...]
    reason: str


def cert2_matrix_report() -> Cert2MatrixReport:
    """Run CERT-2 and report obligation/named-check counts + any unmapped
    obligations (fail-closed on a non-empty unmapped set)."""
    matrix = cert2_matrix()
    result = evaluate_cert2(matrix)
    unmapped = tuple(sorted(ob for ob, checks in matrix.items() if not checks))
    # also any DECLARED obligation missing from the matrix entirely
    unmapped = tuple(sorted(set(unmapped) | (NORMATIVE_OBLIGATIONS - set(matrix))))
    n_checks = sum(len(c) for c in matrix.values())
    reason = (
        f"100% coverage — {len(NORMATIVE_OBLIGATIONS)} normative obligations, "
        f"{n_checks} named checks, zero unmapped"
        if result.passed
        else f"{len(unmapped)} unmapped normative obligation(s): {unmapped}"
    )
    return Cert2MatrixReport(
        passed=result.passed,
        n_obligations=len(NORMATIVE_OBLIGATIONS),
        n_named_checks=n_checks,
        unmapped=unmapped,
        reason=reason,
    )


# ---------------------------------------------------------------------------
# BC6.4 — full self-cert run: CERT-1 ∧ CERT-2 ∧ CERT-3 (§6 / §6.4)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class SelfCertMeasurement:
    """The measured inputs for one full self-cert run (the operational layer
    measures these; the runner conjoins them deterministically).

    The self-cert certifies the WL2 **product** (code + spec + tests). The
    validator-pass-bar (§6.1) is therefore measured at **product scope** —
    warnings in a consuming project's own ``.workshop-lite/ledger/`` operational
    records are host-substrate state, not the WL2 product (dogfooding artifact).
    Both scopes are recorded for transparency; the bar reads the product scope.
    """

    validator_product_warnings: int      # strict warnings in WL2 product files (code/spec/tests)
    validator_repo_warnings: int         # strict warnings repo-wide (incl. host operational ledger)
    new_test_failures: int               # suite failures BEYOND the recorded baseline (issue 2026-06-27-01)
    recorded_baseline_failures: int      # the recorded env-drift quarantine size (14)
    regression_delta: int                # CERT-3: new failures under isolation vs recorded baseline
    staleness_detector_present: bool = True


# the recorded env-drift quarantine baseline (issue 2026-06-27-01: parley-v3
# migration breaks 14 parley-coupled tests). The CERT-1 test-baseline + CERT-3
# bars read against THIS, not a frozen green-literal (§6.1 "current recorded
# baseline, not a frozen literal").
RECORDED_BASELINE_FAILURES = 14


def framework_cert1_rows(m: SelfCertMeasurement) -> tuple[cert_bars.Cert1Row, ...]:
    """The three pinned WL2-framework NFR rows (§6.1)."""
    return (
        cert_bars.Cert1Row(
            nfr_id="validator-pass-bar",
            threshold_value=0,
            threshold_unit="warnings (product scope)",
            condition="cli.py validate --strict over the WL2 product (code/spec/tests)",
            named_check="the strict validator run (product scope)",
            measured_value=m.validator_product_warnings,
            verdict="pass" if m.validator_product_warnings == 0 else "fail",
        ),
        cert_bars.Cert1Row(
            nfr_id="test-baseline",
            threshold_value=0,
            threshold_unit="new failures beyond recorded baseline",
            condition="full suite under isolation vs the recorded baseline (issue 2026-06-27-01)",
            named_check="the baseline suite run",
            measured_value=m.new_test_failures,
            verdict="pass" if m.new_test_failures == 0 else "fail",
        ),
        cert_bars.Cert1Row(
            nfr_id="staleness-detector",
            threshold_value=1,
            threshold_unit="on-read staleness/deadline detector present",
            condition="per time-sensitive kind; deployment pins max_age (§6.1)",
            named_check="the on-read deadline/staleness detector (DOC1 §6.3)",
            measured_value=1 if m.staleness_detector_present else 0,
            verdict="pass" if m.staleness_detector_present else "fail",
        ),
    )


@dataclass(frozen=True)
class SelfCertResult:
    """The full self-cert verdict (§6.4: CERT-1 ∧ CERT-2 ∧ CERT-3)."""

    cert1: CertResult
    cert2: CertResult
    cert3: CertResult
    gate: CertResult

    @property
    def passed(self) -> bool:
        return self.gate.passed


def run_self_cert(m: SelfCertMeasurement) -> SelfCertResult:
    """Run the full self-cert (§6.4) over measured inputs: conjoin CERT-1 ∧
    CERT-2 ∧ CERT-3 via :func:`cert_bars.cert_gate` (fails closed on any absent
    or no-named-check bar — KA-16)."""
    cert1 = cert_bars.cert1_evaluate(framework_cert1_rows(m))
    cert2 = evaluate_cert2()
    cert3 = cert_bars.cert3_evaluate(m.regression_delta)
    gate = cert_bars.cert_gate(cert1, cert2, cert3)
    return SelfCertResult(cert1=cert1, cert2=cert2, cert3=cert3, gate=gate)
