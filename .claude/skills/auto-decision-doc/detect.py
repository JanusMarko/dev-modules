"""Pure detection: scan a parley message body for CTO-RATIFY + decision-shape.

Zero I/O. Pure parsers + regex. The skill layer (auto_file.py) imports this
and combines with the record-decision dual-recording funnel.

v1-AUTO scope (cohort C D2 maturation of the prior v1-MANUAL state; @plan
ratify of par-plan PG-2 disposition msg-6a1d48fbe0a7 + D2 substrate-fit
fork Shape (β) msg-35dfa0551a29): the detector adds a `decision_shape`
classifier that auto-populates the §6 entity frontmatter. The 5-enum
shape values + the deferral-keyword markers below are the v1-AUTO
addition; the trigger + option + chosen + rationale + title surface
remained as built. Hook auto-trigger still deferred — the SKILL.md flow
is still operator-invoked manually; "v1-AUTO" names the shape-categorization
maturation, NOT a hook.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


# -----------------------------------------------------------------------------
# Trigger patterns (case-insensitive). Listed broadest-last so high-precision
# signals can be distinguished from low-precision ones if a future variant
# wants per-pattern confidence weighting. v1 treats any match as a trigger.
# -----------------------------------------------------------------------------

TRIGGER_PATTERNS = [
    r"\bCTO[\s_-]RATIFY\b",
    r"\bCTO[\s_-]RATIFIED\b",
    r"\bCTO[\s_-]RATIFICATION\b",
    r"\bRATIFY\b",
    r"\bRATIFIED\b",
    r"\bGREEN[\s_-]?LIGHT(?:ED)?\b",
    r"\bAPPROVED\b",
]
_TRIGGER_RE = re.compile("|".join(TRIGGER_PATTERNS), re.IGNORECASE)


# -----------------------------------------------------------------------------
# Option-line patterns. Each captures (label_marker, rest_of_line).
# Matched in order; first match for a line wins.
# -----------------------------------------------------------------------------

_OPTION_PATTERNS = [
    # "Option 1: foo" / "Option A - foo"
    re.compile(r"^\s*Option\s+(?P<marker>[A-Za-z0-9]+)\s*[:.\-—]\s*(?P<rest>.+)$",
               re.IGNORECASE),
    # "1. foo" / "1) foo"
    re.compile(r"^\s*(?P<marker>\d+)[.)\]]\s+(?P<rest>.+)$"),
    # "(a) foo" / "a) foo" — lowercase letter
    re.compile(r"^\s*\(?(?P<marker>[a-z])\)\s+(?P<rest>.+)$"),
]

# Chosen markers within an option line OR a separate "Chosen:" / "RATIFY: <N>"
# directive elsewhere in the body.
_CHOSEN_INLINE_RE = re.compile(
    r"\(chosen\)|\[chosen\]|\bchosen\b|\bselected\b|"
    r"→\s*chosen|=>\s*chosen|\*+chosen\*+",
    re.IGNORECASE,
)
_CHOSEN_DIRECTIVE_RE = re.compile(
    r"(?:^|\n)\s*(?:RATIFY|Chosen|Selected|Go with|Pick)\s*"
    r"(?:option|opt\.?)?\s*[:\-]?\s*"
    r"(?P<marker>[A-Za-z0-9]+)\b",
    re.IGNORECASE,
)

# Rationale markers — paragraph following "Rationale:" / "Reasoning:" / etc.
_RATIONALE_RE = re.compile(
    r"(?:^|\n)\s*(?:Rationale|Reasoning|Why|Because|Justification)\s*[:\-]\s*"
    r"(?P<rationale>.+?)(?=\n\n|\n#|\Z)",
    re.IGNORECASE | re.DOTALL,
)

# Title markers — explicit "RATIFY: <title>" / "Title:" / "Decision:".
_TITLE_DIRECTIVE_RE = re.compile(
    r"(?:^|\n)\s*(?:RATIFY|Decision|Title)\s*[:\-]\s*(?P<title>[^\n]+)",
    re.IGNORECASE,
)

# Cohort C D2 — deferral keyword markers (word-anchored, not loose
# substring). Used by classify_decision_shape() to recognize the deferral
# class (trigger present + the ratification's PURPOSE is to defer / park /
# postpone the decision rather than choose among options). Tight to avoid
# suppressing valid select-from-n / go-no-go decisions that merely mention
# deferring as one option among several — those still resolve via their
# options + chosen marker, not the deferral keyword. The classifier
# resolves deferral PRECEDENCE-AFTER chosen-marker resolution: if a body
# has options + chosen + a defer keyword, the options-shape wins (the
# operator made a concrete pick among options that happened to mention
# deferral in prose); only WITHOUT a resolvable chosen marker does the
# defer keyword tip the classifier into SHAPE_DEFERRAL.
_DEFERRAL_KEYWORDS = (
    "DEFER", "DEFERRED", "DEFERRAL",
    "POSTPONE", "POSTPONED", "POSTPONING",
    "PARK", "PARKED",
    "TABLED", "TABLE",
)
_DEFERRAL_RE = re.compile(
    r"\b(" + "|".join(_DEFERRAL_KEYWORDS) + r")\b",
    re.IGNORECASE,
)

# Cohort C D2 — the 5-enum decision_shape values (§6 schema). Surface as
# module-level constants so callers can reference the canonical names
# rather than string-literal them. DECISION_SHAPES mirrors the validator
# membership set in `.claude/scripts/dev-mgmt/validators.py:_DECISION_SHAPES`.
SHAPE_GO_NO_GO = "go-no-go"
SHAPE_SELECT_FROM_N = "select-from-n"
SHAPE_RATIFY_DIRECTION = "ratify-direction"
SHAPE_DEFERRAL = "deferral"
SHAPE_AMBIGUOUS = "ambiguous"
DECISION_SHAPES: frozenset[str] = frozenset({
    SHAPE_GO_NO_GO, SHAPE_SELECT_FROM_N, SHAPE_RATIFY_DIRECTION,
    SHAPE_DEFERRAL, SHAPE_AMBIGUOUS,
})


# -----------------------------------------------------------------------------
# Result dataclass
# -----------------------------------------------------------------------------


@dataclass
class DetectedDecision:
    """Outcome of detect(). All fields nullable; check `confidence`."""

    has_trigger: bool = False
    trigger_match: str | None = None       # the substring that matched
    title: str | None = None
    rationale: str | None = None
    options: list[dict] = field(default_factory=list)
    chosen_marker: str | None = None       # which marker was tagged chosen
    confidence: str = "none"               # none | low | medium | high
    # Cohort C D2 v1-AUTO categorization. None when no trigger (the body
    # carries no ratification at all → nothing to shape); otherwise one of
    # DECISION_SHAPES. Auto-populated into the §6 entity's frontmatter by
    # auto_file.auto_file_from_msg unless the caller passes an override.
    decision_shape: str | None = None
    notes: list[str] = field(default_factory=list)


# -----------------------------------------------------------------------------
# detect()
# -----------------------------------------------------------------------------


def detect(body: str) -> DetectedDecision:
    """Parse `body` for a CTO-RATIFY trigger + decision-shape.

    Returns a DetectedDecision dataclass. Always returns; never raises.
    Pure (no I/O, no globals mutated).

    Confidence ladder:
      - `none`   : no trigger pattern matched
      - `low`    : trigger only (no parseable options)
      - `medium` : trigger + >= 1 option + identifiable chosen
      - `high`   : trigger + >= 2 options + chosen + rationale
    """
    result = DetectedDecision()

    if not body or not isinstance(body, str):
        return result

    trig = _TRIGGER_RE.search(body)
    if not trig:
        return result
    result.has_trigger = True
    result.trigger_match = trig.group(0)
    result.confidence = "low"

    # ---- Options pass ----
    options = _parse_options(body)
    if options:
        # Try to mark a chosen option via either (a) inline marker on the
        # option line itself, or (b) a "Chosen: N" / "RATIFY option N"
        # directive elsewhere in the body.
        chosen_marker = _detect_chosen_marker(body, options)
        if chosen_marker is None:
            # Fallback: if exactly one option carries an inline `(chosen)`,
            # use that. If zero, leave unset.
            inline_hits = [o for o in options if o["_inline_chosen"]]
            if len(inline_hits) == 1:
                chosen_marker = inline_hits[0]["marker"]
        for o in options:
            o["chosen"] = (o["marker"] == chosen_marker)
        result.options = [
            {"label": o["label"], "chosen": o["chosen"],
             "reasoning": o.get("reasoning", "")}
            for o in options
        ]
        result.chosen_marker = chosen_marker

    # ---- Title pass ----
    m_title = _TITLE_DIRECTIVE_RE.search(body)
    if m_title:
        result.title = m_title.group("title").strip().rstrip(".")
    else:
        result.title = _infer_title(body)

    # ---- Rationale pass ----
    m_rat = _RATIONALE_RE.search(body)
    if m_rat:
        result.rationale = m_rat.group("rationale").strip()
    else:
        result.rationale = _infer_rationale(body)

    # ---- Confidence ----
    has_chosen = bool(result.chosen_marker)
    n_options = len(result.options)
    has_rationale = bool(result.rationale and result.rationale.strip())
    if n_options >= 2 and has_chosen and has_rationale:
        result.confidence = "high"
    elif n_options >= 1 and has_chosen:
        result.confidence = "medium"
    else:
        result.confidence = "low"
        if n_options > 0 and not has_chosen:
            result.notes.append(
                f"options parsed ({n_options}) but no chosen marker resolvable"
            )
        if n_options == 0:
            result.notes.append("no option-shape lines matched")

    # ---- Cohort C D2 — decision_shape classification ----
    # Resolves only after the option + chosen passes complete. Trigger
    # being present is the prerequisite (no trigger → no shape).
    result.decision_shape = classify_decision_shape(
        body, n_options=n_options, has_chosen=has_chosen,
    )

    return result


def classify_decision_shape(
    body: str, *, n_options: int, has_chosen: bool,
) -> str:
    """Cohort C D2 — v1-AUTO categorization. Return one of the 5 shape
    values defined in ``DECISION_SHAPES``. Pure function (zero I/O).

    Precedence (specific → general):

    1. ``go-no-go``         — exactly 2 options with a chosen marker.
    2. ``select-from-n``    — ≥3 options with a chosen marker.
    3. ``deferral``         — chosen marker NOT resolvable AND the body
                              contains a defer/postpone/park keyword
                              (segment-anchored, never loose substring).
                              Precedence-after the options+chosen path so
                              a concrete select-from-n that merely
                              mentions deferral in prose still wins
                              go-no-go / select-from-n.
    4. ``ratify-direction`` — 0 or 1 options (no fork; just ratify a
                              direction). Hits when shape is below the
                              N-options threshold for go-no-go but the
                              trigger and (optionally) one option are
                              present.
    5. ``ambiguous``        — fallback. Trigger present but the above
                              criteria didn't fire (e.g. ≥2 options
                              without a resolvable chosen marker).
    """
    # Clear options + chosen path — concrete N-option ratification.
    if has_chosen and n_options == 2:
        return SHAPE_GO_NO_GO
    if has_chosen and n_options >= 3:
        return SHAPE_SELECT_FROM_N

    # No resolvable chosen marker → look at deferral keyword first, then
    # ratify-direction shape, then ambiguous.
    if _DEFERRAL_RE.search(body or ""):
        return SHAPE_DEFERRAL

    if n_options <= 1:
        return SHAPE_RATIFY_DIRECTION

    # Trigger + ≥2 options but no chosen marker resolvable → ambiguous.
    return SHAPE_AMBIGUOUS


# -----------------------------------------------------------------------------
# Internals
# -----------------------------------------------------------------------------


def _parse_options(body: str) -> list[dict]:
    """Return list of dicts: {marker, label, _inline_chosen, reasoning}.

    Groups consecutive option lines into one run; isolated single-letter
    lines without surrounding option-context are skipped to avoid
    false-positive sentence-starters ("a few people said yes").
    """
    runs: list[list[dict]] = []
    current: list[dict] = []

    for raw_line in body.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            if current:
                runs.append(current)
                current = []
            continue

        parsed = None
        for pat in _OPTION_PATTERNS:
            m = pat.match(line)
            if m:
                parsed = m
                break
        if parsed is None:
            if current:
                runs.append(current)
                current = []
            continue

        marker = parsed.group("marker")
        rest = parsed.group("rest").strip()
        inline_chosen = bool(_CHOSEN_INLINE_RE.search(rest))
        # Strip the inline "(chosen)" marker out of the label for tidiness.
        label = _CHOSEN_INLINE_RE.sub("", rest).strip(" -—:")
        current.append({
            "marker": marker,
            "label": label,
            "_inline_chosen": inline_chosen,
            "reasoning": "",
        })

    if current:
        runs.append(current)

    # Take the longest run (the actual options list — short isolated
    # numeric runs of length 1 are usually sentence starts, not options).
    if not runs:
        return []
    best = max(runs, key=len)
    if len(best) < 1:
        return []
    if len(best) == 1 and not best[0]["_inline_chosen"]:
        # A single "1. foo" line with no chosen marker and no directive
        # is more likely prose. Defer to caller — return it but it will
        # likely yield confidence=low.
        pass
    return best


def _detect_chosen_marker(body: str, options: list[dict]) -> str | None:
    """Locate a "Chosen: N" / "RATIFY option N" / "Go with N" directive.
    Cross-reference against the option markers; returns the matched marker
    or None.
    """
    markers = {str(o["marker"]).lower() for o in options}
    for m in _CHOSEN_DIRECTIVE_RE.finditer(body):
        raw = m.group("marker").lower()
        if raw in markers:
            for o in options:
                if str(o["marker"]).lower() == raw:
                    return o["marker"]
    return None


def _infer_title(body: str) -> str | None:
    """Fallback title inference: first non-trigger, non-option meaningful
    line. Heuristic-only; caller should override when filing if wrong.
    """
    for raw in body.splitlines():
        line = raw.strip()
        if not line:
            continue
        if _TRIGGER_RE.search(line) and len(line) < 80:
            # If the trigger line is itself short, use it (often
            # "CTO RATIFY: <topic>" or similar).
            return line.rstrip(".")
        if any(p.match(line) for p in _OPTION_PATTERNS):
            continue
        if line.startswith("#"):
            return line.lstrip("#").strip()
        # First plain-prose line.
        return (line[:120].rstrip(".") if len(line) > 120
                else line.rstrip("."))
    return None


def _infer_rationale(body: str) -> str | None:
    """Fallback rationale: the first prose paragraph that is NOT an
    options block and NOT a trigger-only line. Returns None if nothing
    suitable.
    """
    paragraphs = re.split(r"\n\s*\n", body)
    for para in paragraphs:
        text = para.strip()
        if not text:
            continue
        # Skip option-only paragraphs.
        non_opt = [ln for ln in text.splitlines()
                   if not any(p.match(ln) for p in _OPTION_PATTERNS)]
        if not non_opt:
            continue
        joined = " ".join(ln.strip() for ln in non_opt if ln.strip())
        if not joined:
            continue
        # Skip paragraphs that are only the trigger keyword.
        if _TRIGGER_RE.fullmatch(joined.strip()):
            continue
        if len(joined) < 12:
            continue
        return joined
    return None
