"""4.6i dual-recording — the wl-cwd half of the shared canonical-decision
contract.

PARLEY-AGNOSTIC BY CONSTRUCTION (CLAUDE.md Hard Rule 1): this module
NEVER imports or shells out to parley. It is a byte-identical
re-implementation of parley's `decision_log.py:project_decision_markdown`
FORMAT SPEC + the canonical Decision RECORD-SHAPE, derived from the spec
(the parley docstring + body), NOT from imported parley code. The
parley-coupling funnel lives at the skill layer (D27), never here.

Design (per @plan 4.6i wsl-skill-half ruling msg-90ebfe008c87):

- R1: the shared cross-lane contract is the canonical Decision
  RECORD-SHAPE (`CanonicalDecision`) + the deterministic projection
  (`project_decision_markdown`). Two conformance-locked implementations
  (parley's + this one), NOT shared imported code. A wsl-owned
  cross-lane byte-identical conformance test (see
  `tests/test_canonical_decision_conformance.py`) pins this re-impl's
  output to the ACTUAL parley projection bytes captured at an explicitly
  recorded pinned parley rev — golden anchored to the real spec output.

- R2 + REFINEMENT-2: the rich §6 WL decision entity is the WL-native
  SUPERSET and stays unchanged. The canonical Decision record is a
  well-defined DETERMINISTIC EMBEDDING within it: exactly ONE mapping
  (`extract_canonical`) from the §6 entity's canonical-subset to the one
  canonical record; both the parley Kind.DECISION store and the wl
  canonical-projection artifact are pure projections of that one record.

PURE + BYTE-DETERMINISTIC by contract: same `CanonicalDecision` in =>
byte-identical str out, ALWAYS. No time.time(), env, clock, filesystem,
or randomness — `ts` is rendered from the record's own float.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

# Mirrors parley `decision_log.DECISIONS_SCHEMA_VERSION`. Bump only in a
# coordinated cross-lane spec change (the conformance test golden + this
# constant + the parley side move together, never one alone).
DECISIONS_SCHEMA_VERSION = 1

# The 7 parley DecisionKind values (kept as a tuple for validation; a §6
# WL decision entity always embeds as kind="decision" — the locked
# structural choice).
DECISION_KINDS = (
    "decision",
    "scope_change",
    "blocker",
    "test_status",
    "assumption",
    "defer",
    "ownership",
)


@dataclass(frozen=True)
class CanonicalDecision:
    """The one canonical decision record — field model mirrors parley
    `decision_log.Decision` EXACTLY (the shared RECORD-SHAPE half of the
    contract). Field names/order/types are part of the spec; a change is
    a coordinated cross-lane spec bump.
    """

    kind: str
    text: str
    by: str
    ts: float
    schema_version: int = DECISIONS_SCHEMA_VERSION
    ref: str | None = None
    title: str = ""
    rationale: str = ""
    options_considered: list[str] = field(default_factory=list)
    supersedes_id: str | None = None
    links_to: list[str] = field(default_factory=list)
    msg_id: str | None = None
    external_decision_refs: list[str] = field(default_factory=list)


def project_decision_markdown(decision: CanonicalDecision) -> str:
    """Byte-identical re-implementation of parley
    `decision_log.py:project_decision_markdown` (pinned rev recorded in
    the conformance golden). The body below is the FIXED canonical
    format spec — headers, bullets, field order, and the
    "(none)"/"(untitled)" sentinels are FIXED; any change is a
    coordinated cross-lane spec bump (parley side + this side + the
    regenerated golden, never one alone).

    PURE: no time/env/clock/fs/randomness; `ts` rendered from the
    record's own float as %.6f.
    """
    title = (decision.title or decision.text or "(untitled)").strip() or "(untitled)"

    def _block(items: list[str]) -> str:
        items = [str(i) for i in (items or [])]
        if not items:
            return "- (none)"
        return "\n".join(f"- {i}" for i in items)

    lines = [
        f"# Decision: {title}",
        "",
        f"- **kind:** {decision.kind}",
        f"- **by:** {decision.by}",
        f"- **ts:** {float(decision.ts):.6f}",
        f"- **msg_id:** {decision.msg_id or '(none)'}",
        f"- **ref:** {decision.ref or '(none)'}",
        f"- **supersedes_id:** {decision.supersedes_id or '(none)'}",
        "",
        "## Rationale",
        "",
        (decision.rationale.strip() if decision.rationale else "(none)"),
        "",
        "## Options considered",
        "",
        _block(list(decision.options_considered or [])),
        "",
        "## Links",
        "",
        _block(list(decision.links_to or [])),
        "",
        "## External decision refs",
        "",
        _block(list(decision.external_decision_refs or [])),
        "",
    ]
    return "\n".join(lines)


def _created_at_to_ts(created_at: str) -> float:
    """Deterministic ISO-8601 (`...Z` or offset) -> POSIX float. No
    `now()`, no local tz: the string fully determines the value. §6
    `created_at` carries second precision => whole-second float
    (`.000000` under %.6f), fully reproducible.
    """
    s = (created_at or "").strip()
    if not s:
        return 0.0
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def _options_to_canonical(options: list[dict]) -> list[str]:
    """The ONE deterministic render of §6 `options[{label,chosen,
    reasoning}]` -> canonical `options_considered: list[str]`,
    order-preserving. Format is FIXED (part of the embedding spec):

      "<label> [chosen|rejected]: <reasoning>"   (reasoning present)
      "<label> [chosen|rejected]"                (reasoning empty)
    """
    out: list[str] = []
    for opt in options or []:
        label = str(opt.get("label", "?"))
        verdict = "chosen" if opt.get("chosen") else "rejected"
        reasoning = (opt.get("reasoning") or "").strip()
        out.append(f"{label} [{verdict}]: {reasoning}" if reasoning
                   else f"{label} [{verdict}]")
    return out


def extract_canonical(
    *,
    title: str,
    rationale: str,
    options: list[dict],
    author: str,
    created_at: str,
    supersedes: str | None = None,
    linked_msg_ids: list[str] | None = None,
    external_decision_refs: list[str] | None = None,
    msg_id: str | None = None,
) -> CanonicalDecision:
    """REFINEMENT-2: the single deterministic embedding §6-entity ->
    canonical record. Inputs are the §6 entity's canonical-subset (the
    exact values `entities.record_decision` was given), NOT a re-parse —
    so the funnel and a standalone re-derivation produce the identical
    record.

    Fixed mapping (spec):
      kind                = "decision"  (a §6 WL decision entity is a
                                         locked structural choice)
      title               = §6 title
      text                = ""          (title is the carrier; parley
                                         derives text<-title; "" keeps
                                         the projection title-driven)
      by                  = author, leading "@" stripped (parley stores
                                         `by.lstrip("@")`)
      ts                  = created_at -> POSIX float (deterministic)
      ref                 = None        (no §6 field is a parley `ref`;
                                         msg_id carries chat linkage)
      rationale           = §6 rationale (the "## Why" body)
      options_considered  = _options_to_canonical(§6 options)
      supersedes_id       = §6 supersedes
      links_to            = §6 linked_msg_ids  (intra-parley chat ids)
      msg_id              = parley-returned id when funnelled, else None
      external_decision_refs = passed through (e.g. parley://<msg_id>)
      schema_version      = DECISIONS_SCHEMA_VERSION
    """
    return CanonicalDecision(
        kind="decision",
        text="",
        by=(author or "").lstrip("@"),
        ts=_created_at_to_ts(created_at),
        schema_version=DECISIONS_SCHEMA_VERSION,
        ref=None,
        title=title or "",
        rationale=rationale or "",
        options_considered=_options_to_canonical(options or []),
        supersedes_id=supersedes,
        links_to=list(linked_msg_ids or []),
        msg_id=msg_id,
        external_decision_refs=list(external_decision_refs or []),
    )
