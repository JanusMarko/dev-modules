"""WL2 negative-space detector registry + per-gate realizations (spec §10; BC4).

Spec §10 normative rule (§10.3): every cooperative (advisory-only) gate ships a
companion **negative-space detector** — the check for its silent-failure *tell*,
the observable trace that the convention was skipped (DOC1 §6.2 / Covenant C6
"no pretend guards"). An advisory gate **without** a registered detector is
**non-conformant** (§10.3). This module is that registry (KA-20) plus the
concrete tell-and-check for each of the six advisory gates WL2 ships (§10.2).

Every detector is **read-only and neighborhood-bounded** (§10.1): it scans the
touched neighborhood / event window, never whole history. It never blocks — it
**surfaces** the bypass at the ``warn`` / ``injected-reminder`` rung so a
merely-advised convention still has a way to show it was skipped (C6-c).

The detectors SS-pair with the BC2/BC3 gate mechanics already landed; this module
*wires* those mechanics into the §10.1 detector schema rather than re-defining
them:

  * **BC4.1 continuity-at-the-moment** — JUDGMENT UNIT (RE=yes). Composes the
    BC2.6 ``continuity`` coverage mechanics with an injected
    :class:`ContinuityNeedJudge` (the eval surface — "did this arc-close *need* a
    continuity record?"). Same injected-judgment pattern as BC2.5's ``StuckJudge``.
  * **BC4.2 durable-at-creation** — deterministic. Wraps the BC0.4 ``cross_links``
    dangling-reference resolver (a referenced artifact with no file on disk).
  * **BC4.3 decision-recording** — JUDGMENT UNIT (RE=yes). Reconciles the existing
    v1 decision-shape detector (the ``auto-decision-doc`` skill's ``detect`` +
    ``canonical_decision``) to the §10.2 contract via an injected
    :class:`DecisionShapeJudge`; it is NOT rewritten here.
  * **BC4.4 wait_for deadline** — deterministic. Wraps the BC2.5 ``block_signal``
    on-read deadline inference (a ``wait_for`` past its deadline still ``raised``).
  * **BC4.5 coverage-gate** — deterministic. Wraps the BC3.1 ``coverage_gate`` Q1
    (a build-plan marked ready-to-execute while ``UNDERCOVERED ≠ ∅``).
  * **BC4.6 INDEX-coherence** — deterministic. Wraps the D43 ``validate`` INDEX
    coherence pass (an entity folder's ``INDEX.md`` out of sync with the
    filesystem; ``--strict`` promotes the warn to a hard gate).

For the two JUDGMENT UNITS (BC4.1, BC4.3) this module ships the CODE contract
(the injected-judgment Protocol + a default code-contract judge) — the TRUSTED
behavior ships only behind a FRESH-INDEPENDENT-supplied, @cto-ratified,
cold-graded eval corpus (evals-first, C4/§5; OQ-2 decision
2026-06-27-05-oq-2-resolved-kris-wl2-judgment-unit-eval-corpora-independent-ai-seats-supply-cto-ratifies).
This module does not self-certify either judgment.

Parley-agnostic at base (Hard Rule #1): pure library, no parley import / shell.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Mapping, Protocol, Sequence, runtime_checkable

import block_signal
import continuity
import coverage_gate
import cross_links
from continuity import NegativeSpaceDetector  # the §10.1 detector schema
from validate import WarningRecord as ValidateWarning
from validate import _check_index_coherence

# ---------------------------------------------------------------------------
# §10.2 — the per-gate detector descriptors. Each mirrors a row of the spec
# table EXACTLY (gate_id, silent_failure_tell, check_id, surface, run_on).
# ---------------------------------------------------------------------------

# BC4.1 — re-exported from the BC2.6 mechanics home (single source of truth).
CONTINUITY_AT_THE_MOMENT_DETECTOR = continuity.CONTINUITY_AT_THE_MOMENT_DETECTOR

DURABLE_AT_CREATION_DETECTOR = NegativeSpaceDetector(
    gate_id="durable-at-creation",
    silent_failure_tell=(
        "a referenced artifact (e.g. a decision cited in chat/record) with no "
        "file on disk — a dangling linked_* / citation"
    ),
    check_id="durable_at_creation_violations",
    surface="warn",
    run_on="on-read",
)

DECISION_RECORDING_DETECTOR = NegativeSpaceDetector(
    gate_id="decision-recording",
    silent_failure_tell=(
        "a decision/ratification-shaped event with no decision record linked"
    ),
    check_id="unrecorded_decisions",
    surface="injected-reminder",
    run_on="on-event",
)

WAIT_FOR_DEADLINE_DETECTOR = NegativeSpaceDetector(
    gate_id="wait_for-deadline",
    silent_failure_tell=(
        "a wait_for past its deadline still in raised "
        "(not released / expired)"
    ),
    check_id="expired_unreleased_wait_fors",
    surface="warn",
    run_on="on-read",
)

COVERAGE_GATE_DETECTOR = NegativeSpaceDetector(
    gate_id="coverage-gate",
    silent_failure_tell=(
        "a build-plan marked ready-to-execute while UNDERCOVERED ≠ ∅"
    ),
    check_id="coverage_gate_violations",
    surface="warn",
    run_on="on-read",
)

INDEX_COHERENCE_DETECTOR = NegativeSpaceDetector(
    gate_id="index-coherence",
    silent_failure_tell=(
        "an entity folder's INDEX.md out of sync with the filesystem"
    ),
    check_id="index_coherence_violations",
    surface="warn",  # hard under `cli.py validate --strict` (D43)
    run_on="on-read",
)


# ---------------------------------------------------------------------------
# KA-20 — the per-gate detector registry + conformance (§10.3).
# ---------------------------------------------------------------------------

# The advisory gates WL2 ships (§10.2). This set is the conformance domain: a
# gate_id here with no registered detector is non-conformant (§10.3 / C6).
ADVISORY_GATES: frozenset[str] = frozenset({
    "continuity-at-the-moment",
    "durable-at-creation",
    "decision-recording",
    "wait_for-deadline",
    "coverage-gate",
    "index-coherence",
})

# gate_id → its registered negative-space detector. KA-20 mutation-kill axis:
# an advisory gate that ships with NO detector yet passes conformance must die.
DETECTORS: dict[str, NegativeSpaceDetector] = {
    d.gate_id: d
    for d in (
        CONTINUITY_AT_THE_MOMENT_DETECTOR,
        DURABLE_AT_CREATION_DETECTOR,
        DECISION_RECORDING_DETECTOR,
        WAIT_FOR_DEADLINE_DETECTOR,
        COVERAGE_GATE_DETECTOR,
        INDEX_COHERENCE_DETECTOR,
    )
}


def conformance_violations() -> list[str]:
    """The advisory gates with NO registered negative-space detector (§10.3).

    Empty list ⇒ §10 conformance holds (every advisory gate ships a detector).
    A non-empty result is a **non-conformant** substrate: a cooperative gate
    with no skip-tell is a pretend guard (C6). KA-20's mutation-kill target.
    """
    return sorted(g for g in ADVISORY_GATES if g not in DETECTORS)


def is_conformant() -> bool:
    """True iff every advisory gate (§10.2) ships a registered detector (§10.3)."""
    return not conformance_violations()


# ---------------------------------------------------------------------------
# BC4.1 — continuity-at-the-moment (JUDGMENT UNIT, RE=yes).
#
# Composes the BC2.6 deterministic coverage mechanics (continuity.covers_arc_
# close) with the judgment "did this arc-close event *need* a continuity
# record?" The judgment is injected (the eval surface), mirroring BC2.5's
# StuckJudge: this module ships the Protocol + a fail-closed code-contract
# default; the TRUSTED judge ships behind the independent eval corpus.
# ---------------------------------------------------------------------------


@runtime_checkable
class ContinuityNeedJudge(Protocol):
    """The injected judgment the continuity detector consumes (the eval surface).

    Abstraction-first (BC2.5 ``StuckJudge`` precedent): the detector depends ONLY
    on this protocol. ``needs_continuity_record`` answers the §10.2 event-shape
    classification — an arc-close that *needed* a continuity record vs one that
    did not (a trivial close with nothing in-flight). The TRUSTED implementation
    is supplied behind a fresh-independent, @cto-ratified, cold-graded corpus.
    """

    def needs_continuity_record(self, event: Mapping[str, object]) -> bool:
        """True iff this arc-close ``event`` needed a continuity record written."""
        ...


@dataclass(frozen=True)
class DefaultContinuityNeedJudge:
    """Fail-closed code-contract default (NOT certified judgment).

    An arc-close event is assumed to need a continuity record UNLESS it
    explicitly declares nothing was in-flight (``in_flight is False``) or marks
    itself trivial (``trivial is True``). Ambiguity → needs (fail-closed, C6-c:
    never silently pass). The behavioral nuance is the eval corpus's to grade;
    this default exists so the detector is exercisable before the corpus lands.
    """

    def needs_continuity_record(self, event: Mapping[str, object]) -> bool:
        if event.get("in_flight") is False:
            return False
        if event.get("trivial") is True:
            return False
        return True


def flag_uncovered_arc_closes(
    events: Sequence[Mapping[str, object]],
    records: Sequence[Mapping[str, object]],
    judge: ContinuityNeedJudge,
) -> list[Mapping[str, object]]:
    """§10.2 continuity-at-the-moment detector — judgment-gated.

    Flags arc-close events that (a) the ``judge`` says *needed* a continuity
    record AND (b) have NO covering continuity record in their window. These are
    the silent-failure tells — surfaced as injected-reminder, NEVER silently
    passed (C6-c). Read-only + neighborhood-bounded (scans the supplied window
    only). The deterministic coverage half is delegated to the BC2.6 mechanics
    (``continuity.covers_arc_close``); the needed-vs-not half is the judgment.
    """
    flagged: list[Mapping[str, object]] = []
    for event in events:
        if event.get("kind") not in continuity.ARC_CLOSE_EVENT_KINDS:
            continue
        if not judge.needs_continuity_record(event):
            continue
        if not any(continuity.covers_arc_close(r, event) for r in records):
            flagged.append(event)
    return flagged


# ---------------------------------------------------------------------------
# BC4.2 — durable-at-creation (deterministic).
#
# Wraps the BC0.4 cross-link resolver: a referenced artifact (a cited decision,
# a linked_* target) with no file on disk is a "treated-as-real-before-written"
# tell. Read-only over the entity neighborhood.
# ---------------------------------------------------------------------------


def durable_at_creation_violations(
    repo_root: str | Path,
) -> list[cross_links.WarningRecord]:
    """§10.2 durable-at-creation detector — dangling reference scan (warn).

    Returns the ``cross_link_unresolved`` subset of the BC0.4 cross-link checks:
    each is a ``linked_*`` / citation whose target file is absent on disk (the
    artifact was treated as real before it was durably written, C3). Advisory:
    never raises. Read-only — ``cross_links`` only parses markdown frontmatter.
    """
    return [
        w
        for w in cross_links.run_cross_link_checks(repo_root)
        if w.category == "cross_link_unresolved"
    ]


# ---------------------------------------------------------------------------
# BC4.3 — decision-recording (JUDGMENT UNIT, RE=yes; RECONCILE not rewrite).
#
# §10.2: a decision/ratification-shaped event with no decision record linked.
# The decision-shape classification is the JUDGMENT — already realized by the
# existing v1 detector (the auto-decision-doc skill's `detect` + the
# canonical_decision embedding). This module RECONCILES that to the §10.2
# contract via an injected DecisionShapeJudge (the skill wires its `detect` in);
# it does NOT re-implement the trigger/shape parser here.
# ---------------------------------------------------------------------------


@runtime_checkable
class DecisionShapeJudge(Protocol):
    """The injected judgment the decision-recording detector consumes.

    ``is_decision_shaped`` answers the §10.2 classification — a decision /
    ratification-shaped event vs ordinary discussion. The TRUSTED implementation
    is the existing v1 decision-shape detector (the ``auto-decision-doc`` skill's
    ``detect``), wired in at the skill layer (D27) and graded by the independent
    BC4.3 eval corpus. The library depends ONLY on this protocol — it never
    imports the skill (correct layering).
    """

    def is_decision_shaped(self, event: Mapping[str, object]) -> bool:
        """True iff this ``event`` is decision/ratification-shaped."""
        ...


# §10.2 decision-shape judges **SETTLEMENT**, not a trigger keyword. The v1
# detect.detect ratify-trigger regex (CTO-RATIFY|RATIFY|GREEN-LIGHT|APPROVED) is
# necessary-but-insufficient: it UNDER-FIRES on genuine decisions that settle a
# direction without a ratify keyword. The BC4.3 behavioral eval caught this.
#
# Settlement is recognized as a SEMANTIC CLASS — "a choice has been committed /
# the deliberation is closed" — NOT a per-verb allow-list (an allow-list
# over-fits to the visible cases and fails the next novel construction at the
# same edge). The generalizable signals are:
#
#   (1) CLOSURE / finality state — the matter is now fixed ("settled", "final
#       call", "locked in", "done deal", "it's a go", "that's the plan",
#       "closing this out", "moving on", "signed off").
#   (2) SELECTION among alternatives — "go with X", "we're choosing X", and the
#       "<choice> it is" idiom.
#   (3) APPROVAL / EXECUTION go-ahead — "approved", "ship it", "make it so",
#       "do it", "go ahead", "let's ship/build/roll".
#   (4) COMMITMENT-TO-ADOPT frame — a commitment operator ("we'll", "we're going
#       to", "let's", "I'll") + a SUBSTANTIVE verb + an adoption preposition
#       ("on/onto/to/with/upon"), e.g. "we'll standardize on X", "we'll cut over
#       to X". This generalizes across novel committed-direction verbs by
#       EXCLUDING the deliberation/communication/motion verb CLASS (the
#       complement is "committing to a substantive direction") — not by listing
#       the substantive verbs.
#
# A clause counts only if it is NOT hedged / interrogative / negated / a
# proposal-frame / a past-reference / a deferral (those guards keep the
# over-surface axes passing — ordinary discussion must not surface).

# (1) closure / finality state
_CLOSURE = [
    r"\bdecision\b\s*:",                                  # "Decision: ..."
    r"\bdecided\b",                                        # decided (guarded below)
    r"\bfinal\s+(?:call|decision|answer|word|verdict|say)\b",
    r"\bfinali[sz]ed\b",
    r"\bsettled\b", r"\bthat\s+settles\s+it\b", r"\bsettled\s+then\b",
    r"\bconsider\s+it\s+(?:settled|done|final)\b",
    r"\b(?:lock(?:ed|ing)?|nail(?:ed|ing)?)\s+(?:in|down)\b",
    r"\bset\s+in\s+stone\b",
    r"\bdone\s+deal\b", r"\bit'?s\s+a\s+go\b",
    r"\b(?:good|all)\s+to\s+go\b", r"\bwe'?re\s+(?:set|good\s+to\s+go)\b",
    r"\bthat'?s\s+(?:the|our)\s+(?:plan|call|decision|direction|move|one)\b",
    r"\bclosing\s+(?:this|it)\s+out\b", r"\bcase\s+closed\b",
    r"\bthat'?s\s+(?:that|settled)\b",
    r"\bmoving\s+on\b", r"\blet'?s\s+move\s+(?:forward|ahead)\b",
    r"\bsign(?:ed)?[\s-]?off\b", r"\bsign\s+off\b", r"\blgtm\b",
    r"\bgreen[\s_-]?light(?:ed)?\b",
]
# (2) selection among alternatives — incl. the past-tense "a choice was made"
# class (a bare-object selection that carries no adoption preposition).
_SELECTION = [
    r"\b(?:go|going|gone)\s+with\b",
    r"\bwe'?re\s+(?:going\s+with|choosing|picking|opting\s+for)\b",
    r"\bwe\s+(?:picked|chose|selected|opted\s+for|settled\s+on|landed\s+on|"
    r"went\s+with|agreed\s+on)\b",
    r"\bthe\s+winner\s+is\b",
]
# (3) approval / execution go-ahead
_APPROVAL = [
    r"\bapproved\b", r"\bratif\w+\b",
    r"\bship\s+(?:it|the|that|this|out|option|a\b)",
    r"\bmake\s+it\s+(?:so|happen)\b",
    r"\bdo\s+it\b", r"\bgo\s+ahead\b",
    r"\blet'?s\s+(?:ship|build|roll|do\s+it|do\s+this)\b",
]
_SETTLEMENT_RE = re.compile("|".join(_CLOSURE + _SELECTION + _APPROVAL),
                            re.IGNORECASE)

# The "<choice> it is" finality idiom at a clause tail ("Postgres it is.",
# "gRPC it is!").
_IT_IS_IDIOM_RE = re.compile(r"\b[\w./+-]+\s+it\s+is\b\s*[.!]?\s*$", re.IGNORECASE)

# (4) COMMITMENT-TO-ADOPT — the generalizing frame. A commitment operator + a
# verb that is NOT in the deliberation/communication/motion CLASS + an adoption
# preposition. Excluding the verb class (rather than allow-listing substantive
# verbs) is what lets novel committed-direction constructions generalize.
_COMMIT_OP = (
    r"(?:we'?ll|we\s+will|we'?re\s+going\s+to|we\s+are\s+going\s+to|"
    r"we'?ve\s+(?:decided|agreed)\s+to|let'?s|i'?ll)"
)
# verbs that mean "still deliberating / just talking / moving" — a commitment
# operator + one of these is NOT a settled direction.
_FILLER_VERB = (
    r"(?:see|think|discuss|talk|chat|wait|hold|revisit|reconsider|table|defer|"
    r"postpone|park|decide|figure|circle|loop|look|explore|consider|sleep|"
    r"debate|weigh|evaluate|assess|review|check|investigate|get|reach|move|"
    r"come|sync|meet|wonder|mull|ponder|sit|go|keep|stay|wait)"
)
_COMMIT_ADOPT_RE = re.compile(
    rf"\b{_COMMIT_OP}\s+(?!{_FILLER_VERB}\b)\w+(?:\s+\w+){{0,4}}?\s+"
    r"(?:on|onto|upon|to|with)\b",
    re.IGNORECASE,
)

# Hedge / question / negation / proposal / past-reference / deferral cues that
# NEGATE settlement in a clause.
_NONSETTLE_RE = re.compile(
    r"\?"
    r"|\b\w+['’]t\b"                                       # any n't contraction
    r"|\b(?:maybe|might|perhaps|possibly|probably|could|can\s+we|"
    r"should\s+we|shall\s+we|what\s+if|what\s+about|how\s+about|"
    r"not\s+sure|unsure|wondering|thinking\s+about|leaning|tempted|"
    r"considering|i\s+think|i\s+feel|i['’]d\s+(?:say|lean|prefer)|open\s+to|"
    r"undecided|deciding|to\s+decide|need\s+to\s+decide|still\s+deciding|"
    r"let['’]s\s+decide|not\s+decided|nothing|never|none|"
    r"no\s+(?:decision|consensus|agreement)|"
    # proposal frame — a recommendation/suggestion awaits ratification.
    r"(?:strongly\s+)?(?:recommend\w*|suggest\w*|propos\w*)|"
    r"we\s+should\s+consider|"
    # past-reference frame — a clause that QUOTES a prior decision.
    r"(?:since|as)\s+we\s+(?:already\s+)?(?:decided|agreed|settled|chose|picked)|"
    r"we\s+(?:decided|agreed)\s+(?:last|earlier|previously|before|back|yesterday|already)|"
    r"per\s+(?:the|our|that|a)\s+(?:decision|call|ruling)|"
    # deferral frame — the choice is explicitly POSTPONED, not settled.
    r"tabled?|parked?|postpone\w*|defer\w*|revisit|reconsider|"
    r"circle\s+back|sleep\s+on\s+it|hold\s+off|for\s+now|"
    r"decide\s+(?:later|next|tomorrow|after|this)|next\s+sprint|"
    r"we'?ll\s+see|let['’]s\s+(?:wait|hold|table|revisit|discuss|talk|sleep|sync|meet|circle))\b",
    re.IGNORECASE,
)

_CLAUSE_SPLIT_RE = re.compile(r"[.!?\n]+")


def is_settlement(text: str) -> bool:
    """True iff ``text`` SETTLES a choice / ratifies a direction (§10.2).

    Recognizes settlement as a semantic CLASS (closure / selection / approval /
    commitment-to-adopt) at clause granularity, so a hedge in one sentence does
    not mask a settled decision in another (and vice-versa). A clause counts
    only if it carries a settlement signal AND is not hedged / interrogative /
    negated / a proposal / a past-reference / a deferral. Pure text (no I/O); the
    settlement *semantics* — not a keyword allow-list — are what the BC4.3 eval
    corpus grades (incl. its sealed holdout: the generalization test).
    """
    if not text or not isinstance(text, str):
        return False
    for raw in _CLAUSE_SPLIT_RE.split(text):
        clause = raw.strip()
        if not clause or _NONSETTLE_RE.search(clause):
            continue
        if _SETTLEMENT_RE.search(clause) or _COMMIT_ADOPT_RE.search(clause):
            return True
        # The splitter strips the clause terminator; re-add one so the tail-
        # anchored "X it is" idiom can match.
        if _IT_IS_IDIOM_RE.search(clause + "."):
            return True
    return False


@dataclass(frozen=True)
class DefaultDecisionShapeJudge:
    """Code-contract default that ADAPTS the existing v1 detector (reconcile).

    The skill layer constructs this with ``detect_fn=detect.detect`` (the v1
    decision-shape parser — reused, not rewritten). ``is_decision_shaped`` reads
    the event body (``text`` / ``body``) and classifies it decision-shaped iff
    EITHER the v1 detector finds a ratify trigger OR :func:`is_settlement` finds
    a settled choice (the §10.2 SETTLEMENT bar — not a mere ratify keyword; the
    BC4.3 eval rework added this). With no ``detect_fn`` injected the settlement
    classifier still runs and the structural flag (``event["decision_shaped"]``)
    is the final fallback, so the library stays skill-independent and
    exercisable on its own. NOT certified judgment — the BC4.3 eval corpus
    grades the wired classification.
    """

    detect_fn: Callable[[str], object] | None = None

    @staticmethod
    def _body(event: Mapping[str, object]) -> str:
        for key in ("text", "body"):
            val = event.get(key)
            if isinstance(val, str) and val:
                return val
        return ""

    def is_decision_shaped(self, event: Mapping[str, object]) -> bool:
        # Wired path (the eval-graded classification): a ratify trigger OR a
        # settled choice (§10.2 SETTLEMENT bar). The no-detect_fn fallback shape
        # is left byte-identical to the structural contract — the structural
        # flag — so the BC4.3 structural cert stays green without a refresh.
        if self.detect_fn is not None:
            body = self._body(event)
            if getattr(self.detect_fn(body), "has_trigger", False):
                return True
            return is_settlement(body)
        return event.get("decision_shaped") is True


def _event_ref(event: Mapping[str, object]) -> str | None:
    """The identity an event uses to claim a decision record was linked.

    A decision record links back to the originating event via its ``msg_id`` /
    ``event_id`` / ``id`` (the §6 ``linked_msg_ids`` carrier). Returns the first
    present identity, or None when the event names none.
    """
    for key in ("msg_id", "event_id", "id"):
        val = event.get(key)
        if val:
            return str(val)
    return None


def unrecorded_decisions(
    events: Sequence[Mapping[str, object]],
    recorded_refs: Sequence[str],
    judge: DecisionShapeJudge,
) -> list[Mapping[str, object]]:
    """§10.2 decision-recording detector — event stream ∖ recorded decisions.

    Flags decision/ratification-shaped events (per the ``judge``) whose identity
    is NOT among ``recorded_refs`` (the set of event refs already carried by a
    recorded ``decision`` entity). These are decisions that happened in the
    stream but were never durably recorded — surfaced as injected-reminder,
    never silently passed (C6). Read-only + bounded (the supplied event window).
    An event the judge marks decision-shaped but that names no identity
    (``_event_ref`` is None) is flagged (it cannot be matched to a record, so it
    fails closed). Mirrors the BC2.6 ``uncovered_arc_closes`` events∖records shape.
    """
    recorded = {str(r) for r in recorded_refs}
    flagged: list[Mapping[str, object]] = []
    for event in events:
        if not judge.is_decision_shaped(event):
            continue
        ref = _event_ref(event)
        if ref is None or ref not in recorded:
            flagged.append(event)
    return flagged


# ---------------------------------------------------------------------------
# BC4.4 — wait_for deadline (deterministic).
#
# Wraps the BC2.5 on-read deadline inference: a wait_for past its deadline still
# in `raised` (not released/expired) is the tell. HALT never expires (indefinite
# by declaration) so it is never flagged.
# ---------------------------------------------------------------------------


def expired_unreleased_wait_fors(
    signals: Sequence[Mapping[str, object]],
    *,
    now: datetime | None = None,
) -> list[Mapping[str, object]]:
    """§10.2 wait_for-deadline detector — expired-but-unreleased scan (warn).

    Flags ``wait_for`` block-signals that are past their deadline (BC2.5
    ``block_signal.is_expired``) yet still ``raised`` — the on-read inference
    says they *should* read ``expired`` but no firer released/expired them. A
    ``HALT`` is never flagged (it may wait indefinitely, §11.5). Read-only +
    bounded (the supplied signal set); advisory — never raises.
    """
    flagged: list[Mapping[str, object]] = []
    for signal in signals:
        if signal.get("class") != block_signal.WAIT_FOR:
            continue
        if signal.get("status") != "raised":
            continue
        if block_signal.is_expired(signal, now=now):
            flagged.append(signal)
    return flagged


# ---------------------------------------------------------------------------
# BC4.5 — coverage-gate (deterministic).
#
# Wraps the BC3.1 coverage Q1: a build-plan node asserted ready-to-execute while
# its UNDERCOVERED set is non-empty is the tell (an advisory ready-claim with no
# hard mechanism behind it). Also surfaces Q2-rogue as the §10.2 companion.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CoverageGateFinding:
    """A coverage-gate detector finding (§10.2). Advisory surface, not a block."""

    node: str
    undercovered: frozenset[str]
    rogue: frozenset[str]


def coverage_gate_violations(
    graph: coverage_gate.CoverageGraph,
    node: str,
    *,
    declared_ready: bool,
) -> list[CoverageGateFinding]:
    """§10.2 coverage-gate detector — re-run Q1 on read (warn).

    When a build-plan ``node`` is ``declared_ready`` (marked ready-to-execute)
    yet Q1 ``UNDERCOVERED ≠ ∅`` (or Q2 ``ROGUE ≠ ∅``), the ready-claim bypassed
    the §4.2 gate — surfaced advisory. Returns a single finding listing the
    offending sets (empty list ⇒ the ready-claim is honest, or the node was not
    declared ready). Neighborhood-bounded by construction (the BC3.1 queries are
    set operations over local adjacency, §4.6).
    """
    if not declared_ready:
        return []
    undercovered = coverage_gate.q1_undercovered(graph, node)
    rogue = coverage_gate.q2_rogue(graph, node)
    if not undercovered and not rogue:
        return []
    return [CoverageGateFinding(node=node, undercovered=undercovered, rogue=rogue)]


# ---------------------------------------------------------------------------
# BC4.6 — INDEX coherence (deterministic).
#
# Wraps the D43 validator INDEX-coherence pass: an entity folder's INDEX.md out
# of sync with the filesystem. Advisory (warn) by default; `cli.py validate
# --strict` promotes it to a hard gate (the §10.3 "reach hard-block via a local
# mechanism" rung — the detector is the redundant-but-honest backstop).
# ---------------------------------------------------------------------------


def index_coherence_violations(
    repo_root: str | Path,
) -> list[ValidateWarning]:
    """§10.2 INDEX-coherence detector — INDEX.md ↔ filesystem drift (warn).

    Returns the D43 validator's ``index_coherence`` warnings: entity files
    missing an INDEX row (or vice-versa). Advisory by default; ``cli.py validate
    --strict`` is the hard-gate rung. Read-only — directory listing + INDEX
    parse only (the cheap §10.1-bounded check, not a whole-history scan).
    """
    return _check_index_coherence(Path(repo_root))
