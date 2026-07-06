"""BC4.3 Option-2 — LLM-backed DecisionShapeJudge (cto ruling v3-2142).

Settlement-detection from open prose is a semantic/NLU judgment, not a lexical
one: the v1 ``detect.detect`` regex lineage was the wrong ARCHITECTURE for a
judgment unit (it over-fit to whatever cases were visible and failed novel
committed-direction constructions at the same edge). This module realizes the
SAME ``negative_space.DecisionShapeJudge`` Protocol with an LLM backend that
classifies "a choice has been committed / the deliberation is closed"
semantically — the principled path to genuine generalization.

Skill-layer module (D27): external-model coupling lives HERE, never in the
dev-mgmt library (Hard Rule #1 keeps the lib pure). The library's Protocol +
``DefaultDecisionShapeJudge`` (the lexical baseline) are unchanged — only the
wired, eval-graded judge swaps lexical→LLM.

Deterministic-for-grade (cto-required, so cold-grade + verifier-reproduce are
reproducible): ``judge_consistency_protocol`` = **temperature=0 + a PINNED model
slug + deterministic decode**. The Claude Messages API exposes no ``seed``
parameter (unlike some providers), so temperature=0 is the determinism lever;
this is documented, not silently defaulted. The canonical grade backend is the
Anthropic Messages API at temperature=0 with the pinned slug.

The judge depends only on an injected ``complete(system, user) -> str``
callable (abstraction-first) so it is unit-testable offline and backend-
swappable; the default backend is the Anthropic SDK.
"""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from typing import Callable, Mapping

# Explicit pinned model slug — NO silent default (cto-required). This is the
# slug the cold-grade + verifier-reproduce bind to; changing it is a coordinated
# eval re-grade, never an implicit bump.
PINNED_MODEL = "claude-opus-4-8"

# One-line determinism contract recorded in module metadata (addendum only — not
# a corpus/bar change). Claude has no seed param ⇒ temperature=0 is the lever.
JUDGE_CONSISTENCY_PROTOCOL = (
    "temperature=0 + pinned model slug (PINNED_MODEL) + deterministic decode; "
    "Claude Messages API has no seed param so temperature=0 is the determinism "
    "lever; max_tokens small, no top_p/top_k sampling overrides."
)

# Semantic classification contract (§10.2). Defines the SETTLEMENT class for the
# model to apply — deliberately NOT a list of trigger words, and with NO
# reference to any eval case (builder is blind to the sealed holdout).
_SYSTEM_PROMPT = (
    "You classify a single chat/work message for a governance decision-recording "
    "detector. Decide whether the message SETTLES a decision — i.e. a choice has "
    "been COMMITTED or a direction RATIFIED (the deliberation is closed) — versus "
    "NOT a settled decision.\n\n"
    "Answer DECISION (settled) when the message commits to a course of action: a "
    "direction is selected or adopted, an option is ratified/approved, a go-ahead "
    "to execute is given, or a choice is closed out — EVEN IF phrased tentatively "
    "or in passing. The discriminant is settlement, not tone or keywords.\n\n"
    "Answer DISCUSSION (not settled) for anything that does NOT settle a new "
    "choice: an open question, weighing options without choosing, a "
    "recommendation/suggestion/proposal awaiting ratification (recommending is "
    "not deciding), a deferral ('let's decide later / table this'), a status or "
    "CI/log update, coordination chatter, or a message that merely REFERENCES or "
    "quotes a PRIOR decision ('since we decided last week …') without making a "
    "new one.\n\n"
    "Reason about the meaning, not surface words. Respond with EXACTLY ONE token: "
    "DECISION or DISCUSSION. No other text."
)


def _build_user(text: str) -> str:
    return f"Message:\n\"\"\"\n{text}\n\"\"\"\n\nClassify: DECISION or DISCUSSION."


def _parse_verdict(raw: str) -> bool:
    """Map the model's reply to the boolean settlement verdict.

    Fail-closed on an unparseable reply is NOT appropriate here (the judge is the
    classifier itself, not a guard): we take the first DECISION/DISCUSSION token
    seen. An empty/garbled reply → False (treated as 'not a settled decision'),
    matching the no-signal default.
    """
    up = (raw or "").upper()
    i_dec = up.find("DECISION")
    i_dis = up.find("DISCUSSION")
    if i_dec == -1 and i_dis == -1:
        return False
    if i_dec == -1:
        return False
    if i_dis == -1:
        return True
    return i_dec < i_dis  # whichever token appears first wins


def anthropic_completer(model: str = PINNED_MODEL) -> Callable[[str, str], str]:
    """Canonical grade backend — Anthropic Messages API at temperature=0.

    Lazy-imports the SDK so this module loads without it (offline / keyless
    test environments use an injected stub instead). Reads the API key from the
    environment per the SDK default. This is the bit-reproducible-intent path
    the cold-grade binds to.
    """
    def _complete(system: str, user: str) -> str:
        import anthropic  # lazy — only needed for the real grade backend
        client = anthropic.Anthropic()
        resp = client.messages.create(
            model=model,
            max_tokens=16,
            temperature=0,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        parts = [b.text for b in resp.content if getattr(b, "type", None) == "text"]
        return "".join(parts)

    return _complete


def claude_cli_completer(model: str = PINNED_MODEL) -> Callable[[str, str], str]:
    """Keyless backend — shells out to the ``claude`` CLI in print mode.

    For environments without the Anthropic SDK / API key (e.g. the builder's
    --non-holdout local self-check, which runs on the logged-in CLI session).
    NOT the canonical grade backend (the CLI does not expose temperature); the
    reproducible grade uses :func:`anthropic_completer`.
    """
    def _complete(system: str, user: str) -> str:
        prompt = f"{system}\n\n{user}"
        out = subprocess.run(
            ["claude", "-p", prompt, "--model", model],
            capture_output=True, text=True, timeout=120,
        )
        return out.stdout

    return _complete


@dataclass(frozen=True)
class LLMDecisionShapeJudge:
    """LLM-backed realization of ``negative_space.DecisionShapeJudge`` (Option 2).

    ``is_decision_shaped`` classifies settlement semantically from the event
    text. Satisfies the SAME runtime_checkable Protocol (same method signature)
    — so the structural cert (Protocol / DefaultDecisionShapeJudge fallback /
    surface / unrecorded_decisions gating) stays valid; only the wired impl
    swaps lexical→LLM. ``complete`` is injectable (default: Anthropic SDK at
    temperature=0, the reproducible grade backend).
    """

    model: str = PINNED_MODEL
    complete: Callable[[str, str], str] | None = None
    judge_consistency_protocol: str = JUDGE_CONSISTENCY_PROTOCOL

    @staticmethod
    def _body(event: Mapping[str, object]) -> str:
        for key in ("text", "body"):
            val = event.get(key)
            if isinstance(val, str) and val:
                return val
        return ""

    def _default_completer(self) -> Callable[[str, str], str]:
        """Resolve the default backend. The grade path is the Anthropic SDK
        (temperature=0, reproducible). ``BC4_JUDGE_BACKEND=claude_cli`` is an
        EXPLICIT opt-in override for keyless environments (the builder's
        --non-holdout local self-check runs on the logged-in CLI) — it is never
        the grade backend; eval-d's reproducible grade uses the SDK default.
        """
        if os.environ.get("BC4_JUDGE_BACKEND") == "claude_cli":
            return claude_cli_completer(self.model)
        return anthropic_completer(self.model)

    def is_decision_shaped(self, event: Mapping[str, object]) -> bool:
        text = self._body(event)
        if not text.strip():
            return False
        completer = self.complete or self._default_completer()
        return _parse_verdict(completer(_SYSTEM_PROMPT, _build_user(text)))
