"""Schema validators per entity type.

Sprint 1 (dev-mgmt.1) shipped the Decision validator. Sprint 2 (dev-mgmt.2)
adds Sprint Plan + Retrospective validators per
``LIGHTWEIGHT-DEV-MGMT-SYSTEM.md`` §6. Sprint 3 (dev-mgmt.3) adds the
Handoff validator (D6.A — fills the §6 gap; to be amended into the
design doc during session-end ritual). Sprint 4 (dev-mgmt.4) adds Issue
+ Review validators per D12-D16. Sprint 5 (dev-mgmt.5) adds Task-line +
Conversation validators per D20-D25 (parser-validator for inline task
list items in tasks.md; full §6 schema validator for the Conversation
entity).

Sprint 7 adds the ``STATUS_TRANSITIONS`` matrix (D44) consumed by
``validate._check_status_transitions``. The matrix is the canonical
encoding of which statuses (and transitions) are legal per entity
type; today's validator uses it for "current status is known for
this type" drift detection — a strict-superset of the per-type
``_FOO_STATUSES`` membership checks above. Once entities carry a
``status_history`` field, the matrix's transition graph becomes
enforceable end-to-end; until then it's the data-shape declaration
plus the state-validity gate.
"""
from __future__ import annotations

import re


class ValidationError(Exception):
    """Raised when entity frontmatter fails schema validation."""

    def __init__(self, errors: list[str]):
        self.errors = list(errors)
        super().__init__("; ".join(self.errors))


_DECISION_STATUSES = {"accepted", "rejected", "superseded", "open", "proposed"}
_DECISION_REQUIRED = (
    "id", "type", "title", "status", "scope",
    "options", "created_at", "author",
)
# Cohort C D2 — /auto-decision-doc v1-AUTO categorization. OPTIONAL §6
# field: when present, must be one of these 5 values. Absent / None is
# accepted (entities filed before D2 OR by /record-decision direct — the
# detector hook lives in the auto-decision-doc skill layer only).
_DECISION_SHAPES = frozenset({
    "go-no-go",
    "select-from-n",
    "ratify-direction",
    "deferral",
    "ambiguous",
})


def validate_decision(fm: dict) -> None:
    """Validate Decision frontmatter against the §6 schema.

    Raises ``ValidationError`` with field-level messages; returns ``None`` on
    success.
    """
    errors: list[str] = []

    for field in _DECISION_REQUIRED:
        if field not in fm:
            errors.append(f"missing required field: {field}")
        elif fm[field] in (None, ""):
            errors.append(f"required field is empty: {field}")

    type_val = fm.get("type")
    if type_val is not None and type_val != "decision":
        errors.append(f"type must be 'decision', got: {type_val!r}")

    status = fm.get("status")
    if status is not None and status not in _DECISION_STATUSES:
        errors.append(
            f"status must be one of {sorted(_DECISION_STATUSES)}, got: {status!r}"
        )

    options = fm.get("options")
    if options is None:
        pass  # already flagged as required-empty above
    elif not isinstance(options, list):
        errors.append("options must be a list")
    else:
        for i, opt in enumerate(options):
            if not isinstance(opt, dict):
                errors.append(f"options[{i}] must be a mapping")
                continue
            for key in ("label", "chosen"):
                if key not in opt:
                    errors.append(f"options[{i}] missing key: {key}")

    # Cohort C D2 — decision_shape: OPTIONAL; absent / None accepted; when
    # present must be in the 5-enum.
    shape = fm.get("decision_shape")
    if shape is not None and shape not in _DECISION_SHAPES:
        errors.append(
            f"decision_shape must be one of {sorted(_DECISION_SHAPES)}, "
            f"got: {shape!r}"
        )

    for list_field in ("authored_with", "linked_decisions",
                       "linked_reviews", "linked_msg_ids"):
        val = fm.get(list_field)
        if val is not None and not isinstance(val, list):
            errors.append(f"{list_field} must be a list if present")

    if errors:
        raise ValidationError(errors)


_SPRINT_PLAN_STATUSES = {
    "draft", "active", "superseded",
    # workshop-lite cohort (A) substrate-hygiene (charter §2 D5 +
    # chunk-0 PG-4 discipline-applied; ratified msg-bddb14456071):
    # `closed` is the terminal-archived state written by /end-sprint
    # when the sprint folder moves from active/ to archive/. Closes
    # wsl-plan checkpoint #2 §④ (18/18 archived sprints stuck at
    # `status: active`). The matching STATUS_TRANSITIONS["sprint-plan"]
    # entry below carries the active→closed→terminal edges.
    "closed",
}
_SPRINT_PLAN_REQUIRED = (
    "id", "type", "title", "sprint_id", "status",
    "version", "created_at", "author",
)


def validate_sprint_plan(fm: dict) -> None:
    """Validate Sprint Plan frontmatter against the §6 schema."""
    errors: list[str] = []

    for field in _SPRINT_PLAN_REQUIRED:
        if field not in fm:
            errors.append(f"missing required field: {field}")
        elif fm[field] in (None, ""):
            errors.append(f"required field is empty: {field}")

    type_val = fm.get("type")
    if type_val is not None and type_val != "plan":
        errors.append(f"type must be 'plan', got: {type_val!r}")

    status = fm.get("status")
    if status is not None and status not in _SPRINT_PLAN_STATUSES:
        errors.append(
            f"status must be one of {sorted(_SPRINT_PLAN_STATUSES)}, got: {status!r}"
        )

    version = fm.get("version")
    if version is not None and not isinstance(version, int):
        errors.append("version must be an integer")

    linked = fm.get("linked_design_docs")
    if linked is not None and not isinstance(linked, list):
        errors.append("linked_design_docs must be a list if present")

    if errors:
        raise ValidationError(errors)


_RETRO_STATUSES = {"completed"}
_RETRO_REQUIRED = (
    "id", "type", "title", "sprint_id", "status",
    "shipped_at", "created_at", "author",
)


def validate_retrospective(fm: dict) -> None:
    """Validate Retrospective frontmatter against the §6 schema."""
    errors: list[str] = []

    for field in _RETRO_REQUIRED:
        if field not in fm:
            errors.append(f"missing required field: {field}")
        elif fm[field] in (None, ""):
            errors.append(f"required field is empty: {field}")

    type_val = fm.get("type")
    if type_val is not None and type_val != "retrospective":
        errors.append(f"type must be 'retrospective', got: {type_val!r}")

    status = fm.get("status")
    if status is not None and status not in _RETRO_STATUSES:
        errors.append(
            f"status must be one of {sorted(_RETRO_STATUSES)}, got: {status!r}"
        )

    for list_field in ("linked_decisions", "linked_reviews"):
        val = fm.get(list_field)
        if val is not None and not isinstance(val, list):
            errors.append(f"{list_field} must be a list if present")

    tr = fm.get("test_results")
    if tr is not None:
        if not isinstance(tr, dict):
            errors.append("test_results must be a mapping if present")
        else:
            for k in ("passed", "skipped", "xfailed", "xpassed", "failed"):
                if k in tr and not isinstance(tr[k], int):
                    errors.append(f"test_results.{k} must be an integer")

    if errors:
        raise ValidationError(errors)


# Handoff `trigger` enum. Original D6.A canonical values: manual,
# pre_compact, session_end. Extended per workshop-lite Issue 2026-06-03-09
# (paired-cohort 04+09 arc-shape consumer prereqs, PG-5 ratify
# msg-e93e88cc2e07): arc-shape consumers (autonomous-arc operating mode,
# maxai is the empirical surface) need finer-grained lifecycle vocabulary
# for handoffs that document phase-segment / arc-segment / sprint-segment
# closures. Existing values remain valid (back-compat); new values opt-in
# per use site.
_HANDOFF_TRIGGERS = {
    "manual", "pre_compact", "session_end",
    "phase_close", "arc_close", "sprint_close",
}
# Handoff `status` enum. Original de-facto value: 'written' (no prior
# canonical decision recorded). Extended per workshop-lite Issue
# 2026-06-03-09 (PG-5 ratify): arc-shape consumers need routing-state
# vocabulary for handoffs that are dispatched to a downstream recipient,
# routed at a downstream session, or acknowledged by the recipient. The
# F-11 empirical case `status: 'dispatch-to-@plan'` (hyphenated) is
# DELIBERATELY NOT in the enum — the canonical form is `dispatched`
# (underscored, routing-state-only; the recipient address lives elsewhere
# in the doc body or a separate field).
_HANDOFF_STATUSES = {
    "written",
    "dispatched", "routed", "acknowledged",
}
_HANDOFF_REQUIRED = (
    "id", "type", "title", "topic", "trigger",
    "status", "created_at", "author",
)
_HANDOFF_LIST_FIELDS = (
    "linked_decisions", "linked_issues", "linked_tasks", "linked_msg_ids",
)


def validate_handoff(fm: dict) -> None:
    """Validate Handoff frontmatter against the D6.A schema.

    D6.A fills the §6 design-doc gap. Schema:
    Required: id, type=handoff, title, topic, trigger, status, created_at, author.
    trigger ∈ {manual, pre_compact, session_end, phase_close, arc_close,
    sprint_close} (last three added per Issue 2026-06-03-09 PG-5 ratify —
    arc-shape consumer prereq). status ∈ {written, dispatched, routed,
    acknowledged} (routing-state vocabulary added per same ratify; original
    'written' remains the default terminal-write state).
    sprint_id and stage are paired: both null OR both set.
    linked_* arrays default empty; since_handoff_id / since_msg_id / next_action
    are free-form optionals.
    """
    errors: list[str] = []

    for field in _HANDOFF_REQUIRED:
        if field not in fm:
            errors.append(f"missing required field: {field}")
        elif fm[field] in (None, ""):
            errors.append(f"required field is empty: {field}")

    type_val = fm.get("type")
    if type_val is not None and type_val != "handoff":
        errors.append(f"type must be 'handoff', got: {type_val!r}")

    trigger = fm.get("trigger")
    if trigger is not None and trigger not in _HANDOFF_TRIGGERS:
        errors.append(
            f"trigger must be one of {sorted(_HANDOFF_TRIGGERS)}, got: {trigger!r}"
        )

    status = fm.get("status")
    if status is not None and status not in _HANDOFF_STATUSES:
        errors.append(
            f"status must be one of {sorted(_HANDOFF_STATUSES)}, got: {status!r}"
        )

    sprint_id = fm.get("sprint_id")
    stage = fm.get("stage")
    sprint_set = sprint_id not in (None, "")
    stage_set = stage not in (None, "")
    if sprint_set != stage_set:
        errors.append(
            "sprint_id and stage must be both set or both null/empty"
        )

    for list_field in _HANDOFF_LIST_FIELDS:
        val = fm.get(list_field)
        if val is not None and not isinstance(val, list):
            errors.append(f"{list_field} must be a list if present")

    if errors:
        raise ValidationError(errors)


_ISSUE_STATUSES = {
    "open", "investigating", "resolved", "wontfix",
    # workshop-lite cohort (A) substrate-hygiene (charter
    # docs/inbox/2026-06-04-workshop-lite-cohort-A-substrate-hygiene-charter.md
    # §2 D1; 3-way-audit ratified CTO msg-882450598703). `deferred` is the
    # (β) deferred-registry shape's lifecycle anchor; `superseded` closes
    # WL OBS-3 (2026-06-02-01-consult-skill-v2-*.md fires
    # [status_transition_out_of_band] today). Both follow the Option-A
    # canonical-widening proof-pattern from Issue 09 paired cohort
    # (msg-714c1cf85... LAND f4ce664). The STATUS_TRANSITIONS["issue"]
    # graph below carries the matching state-graph edges (chunk-0 PG-3
    # discipline-applied scope: enum-widening dual-update).
    "deferred", "superseded",
}
_ISSUE_SEVERITIES = {"high", "medium", "low"}
# workshop-lite cohort (A) substrate-hygiene (charter §2 D2): the (β)
# deferred-registry shape — 5 frontmatter fields conditionally required
# when status=deferred. All optional by default; the conditional guard
# enforces non-null defer_reason + revisit_trigger_kind + revisit_trigger_ref
# WHEN status=deferred. The other two (defer_date + defer_ratifier) are
# recommended-not-enforced (audit trail; absence on status=deferred is
# permitted but discouraged). Pattern matches the §6 schema convention
# of "optional-but-conditionally-required" first established by the
# Handoff D6.A sprint_id/stage pairing rule.
_ISSUE_DEFERRED_REQUIRED = (
    "defer_reason", "revisit_trigger_kind", "revisit_trigger_ref",
)
# revisit_trigger_kind enum (charter §2 D2). 4-value taxonomy covering
# the empirically-observed defer-lifecycle revisit triggers:
#   - date:               revisit on/after a wall-clock date (ISO date in ref)
#   - artifact_ratify:    revisit when a referenced entity transitions to a
#                         terminal/ratified state (ref = "issue:<id>" / "decision:<id>")
#   - external_event:     revisit when a free-text-described external event
#                         fires (ref = free-text event description)
#   - unblock_on:         revisit when a referenced dependency unblocks
#                         (ref = "<dependency-id>")
_REVISIT_TRIGGER_KINDS = {
    "date", "artifact_ratify", "external_event", "unblock_on",
}
# Base scope-prefix tuple used by ``_check_scope`` (Issue + Review
# validators). Includes ``arc:<id>`` per workshop-lite Issue 2026-06-03-04
# (paired-cohort 04+09 arc-shape consumer prereqs, PG-1 ratify): the
# substrate's other scope-prefix tuples (_WIP_CLAIM_*, _EPIC_SHIPPED_*,
# _STANDING_DISPATCH_*, _PRD_*) already accept arc:; this brings the
# base tuple to parity so arc-scoped issues + reviews validate cleanly
# without the prior ``[validator.ignore]`` carve-out workaround.
_SCOPE_PREFIXES = ("sprint:", "repo:", "design:", "arc:")
_ISSUE_REQUIRED = (
    "id", "type", "title", "status", "severity",
    "scope", "created_at", "reporter",
)
_ISSUE_LIST_FIELDS = ("linked_decisions", "linked_reviews", "linked_msg_ids")


def _check_scope(value: object, errors: list[str]) -> None:
    if value in (None, ""):
        return  # required-empty already flagged
    if not isinstance(value, str) or not value.startswith(_SCOPE_PREFIXES):
        errors.append(
            f"scope must start with one of {list(_SCOPE_PREFIXES)}, got: {value!r}"
        )


def _check_paired_sprint_stage(fm: dict, errors: list[str]) -> None:
    sprint_id = fm.get("sprint_id")
    stage = fm.get("stage")
    sprint_set = sprint_id not in (None, "")
    stage_set = stage not in (None, "")
    if sprint_set != stage_set:
        errors.append("sprint_id and stage must be both set or both null/empty")


def validate_issue(fm: dict) -> None:
    """Validate Issue frontmatter per D12+D13 (Sprint 4 refinements of §6).

    D12: ``class`` is an optional free-form string (default null) — per-repo
    can use it for their own taxonomy. ``linked_decisions`` (not
    ``related_decisions`` from §6 example) for linked_* family consistency.

    D13: ``scope`` accepts the same taxonomy as Decision —
    ``sprint:<id>``, ``repo:<area>``, ``design:<doc-name>``, ``arc:<id>``
    (Issue 2026-06-03-04 PG-1 ratify: arc-shape consumer prereq). ``sprint_id``
    and ``stage`` are paired (both set or both null) per the Handoff D6.A rule.
    """
    errors: list[str] = []

    # workshop-lite cohort (A) substrate-hygiene (charter §2 D4):
    # validator schema-strictness — reject the obsolete `state:` typo
    # in favor of canonical `status:`. wsl-plan checkpoint #1 §② surface:
    # `state: <value>` was a legacy schema-typo (likely Git/GitHub-issue
    # convention bleed-through; the §6 canonical field has always been
    # `status:`). Two historical issue files (2026-06-03-02 +
    # 2026-06-03-03) used the typo. The rejection here is paired with
    # the migration of those 2 files (chunk-1b commit). Subsequent
    # writes through entities.record_issue + /record-issue skill already
    # emit `status:` correctly; this guard catches hand-authored typos
    # and arrests silent invisibility-to-status-grep drift.
    if "state" in fm and "status" not in fm:
        errors.append(
            "issue uses obsolete `state:` field; rename to `status:` "
            "(D4 rejection — `state` is not a recognized issue "
            "frontmatter key per §6 canonical schema)"
        )
    elif "state" in fm and "status" in fm:
        errors.append(
            "issue carries both `state:` AND `status:`; remove obsolete "
            "`state:` (D4 rejection — only canonical `status:` is recognized)"
        )

    for field in _ISSUE_REQUIRED:
        if field not in fm:
            errors.append(f"missing required field: {field}")
        elif fm[field] in (None, ""):
            errors.append(f"required field is empty: {field}")

    type_val = fm.get("type")
    if type_val is not None and type_val != "issue":
        errors.append(f"type must be 'issue', got: {type_val!r}")

    status = fm.get("status")
    if status is not None and status not in _ISSUE_STATUSES:
        errors.append(
            f"status must be one of {sorted(_ISSUE_STATUSES)}, got: {status!r}"
        )

    severity = fm.get("severity")
    if severity is not None and severity not in _ISSUE_SEVERITIES:
        errors.append(
            f"severity must be one of {sorted(_ISSUE_SEVERITIES)}, got: {severity!r}"
        )

    _check_scope(fm.get("scope"), errors)
    _check_paired_sprint_stage(fm, errors)

    klass = fm.get("class")
    if klass is not None and not isinstance(klass, str):
        errors.append("class must be a string if present (optional free-form per D12)")

    # workshop-lite cohort (A) substrate-hygiene (charter §2 D2): the
    # (β) deferred-registry shape — 5 optional frontmatter fields with
    # conditional-required guard when status=deferred. The guard
    # enforces the 3 anchor fields (defer_reason + revisit_trigger_kind
    # + revisit_trigger_ref); defer_date + defer_ratifier are audit-
    # trail-recommended but not validator-enforced. The
    # revisit_trigger_kind enum is enforced unconditionally (rejected
    # if present-but-not-in-enum, even when status != deferred).
    revisit_kind = fm.get("revisit_trigger_kind")
    if revisit_kind is not None and revisit_kind not in _REVISIT_TRIGGER_KINDS:
        errors.append(
            f"revisit_trigger_kind must be one of "
            f"{sorted(_REVISIT_TRIGGER_KINDS)}, got: {revisit_kind!r}"
        )
    if status == "deferred":
        for f in _ISSUE_DEFERRED_REQUIRED:
            if f not in fm or fm[f] in (None, ""):
                errors.append(
                    f"status=deferred requires non-empty `{f}` "
                    "((β) deferred-registry guard per charter §2 D2)"
                )

    for list_field in _ISSUE_LIST_FIELDS:
        val = fm.get(list_field)
        if val is not None and not isinstance(val, list):
            errors.append(f"{list_field} must be a list if present")

    if errors:
        raise ValidationError(errors)


_REVIEW_STATUSES = {"in_progress", "completed", "open_consult", "closed_consult"}
# Cohort HH chunk-6 (par:2026-06-04-03 consultant skill primitive)
# additive extension per Q3 ratify msg-0565d9dc4318: `open_consult` =
# growing-body Review for live consultant member; `closed_consult` =
# consultant departed (turn-aggregator v1 closing snapshot appended).
# Used only when `review_type=consultant`; existing values
# unchanged (in_progress / completed remain valid for non-consult
# review_types per zero-regression guarantee).
_REVIEW_TYPES = {
    "adversarial", "collaborative", "synthesis", "research",
    # Cohort HH chunk-6 LAND — consultant Review path for multi-turn
    # ephemeral LLM consultant primitive (xrequest from par-p0-cohort-HH-
    # builder msg-5722ef2e2157; @par-plan planner-to-planner routing).
    # Growing-body convention (## Turn N sections); no findings list
    # (replaced by per-turn responses); closing snapshot synthesis hook
    # at status=closed_consult.
    "consultant",
    # Sprint S-B D1=A (ce1fc36 §3; @plan-RATIFIED refinement of the
    # D1-literal, msg-c0bb26d0556b — supersedes the imprecise
    # "review-type=adversarial" wording). The cross-check-resolution
    # artifact TYPE is a NEW VALUE in this EXISTING review_type enum
    # (NOT a new frontmatter field; schema_version stays 1 —
    # wl-side-complete). IMPORTABILITY (S-B target-5, MEASURED —
    # @modules msg-a0e161807eee; corrected from the falsified
    # "zero schema delta / importable-without-migration" rationale):
    # Workshop-side review_type is a CLOSED PG-ENUM, so this value is
    # NOT zero-delta-importable — it needs a one-line Workshop-side
    # ALTER TYPE review_type ADD VALUE Alembic migration, a recorded
    # Workshop-side-blocker (docs/design/workshop-side-blockers-
    # anchor.md B-A.5; workshop-importability-matrix.md ~L140). The
    # wl-side validator branch + grandfathering below are structurally
    # sound and unaffected. The validator branch
    # below keys on this value; grandfathering is BY-CONSTRUCTION (no
    # existing reviews/ entity carries it and the prose
    # decisions/2026-05-16-04..11 are not reviews/ entities at all, so
    # the new rule STRUCTURALLY CANNOT MATCH any existing record —
    # stronger than a keyed-exclusion clause; the eliminate-by-
    # construction / single-source discipline).
    "cross-check-resolution",
}
# Review `findings[].severity` enum. Original D16 canonical values:
# high, medium, low. Extended per workshop-lite Issue 2026-06-03-09
# (PG-4 ratify msg-e93e88cc2e07): adversarial-review nuance for
# arc-shape consumers needs `info` (informational, not requiring action)
# and `clean` (no finding surfaced — explicit affirmative no-finding
# state, distinct from omission). Shared by both
# _validate_review_existing_path (line ~493) AND
# _validate_review_persona_path (line ~632). Note: Issue-level
# _ISSUE_SEVERITIES is a SEPARATE tuple and remains narrow
# (high|medium|low) per PG-4 scope discipline.
_FINDING_SEVERITIES = {"high", "medium", "low", "info", "clean"}
#: Sprint S-B D1=A — the structured per-seat-verdict keys a
#: review_type=cross-check-resolution finding carries (D1: seat /
#: verdict / measured-SHA / scope-disciplined-subset / deferred-lanes),
#: in place of the generic severity+summary finding shape.
_XCHECK_SEAT_REQUIRED = (
    "seat", "verdict", "measured_sha", "scope_subset", "deferred_lanes",
)
_XCHECK_VERDICTS = {"PASS", "FAIL"}
_REVIEW_REQUIRED = (
    "id", "type", "review_type", "title", "status",
    "scope", "created_at", "author",
)
_REVIEW_LIST_FIELDS = ("linked_decisions", "linked_reviews", "linked_msg_ids")

# Cohort HH chunk-6 consultant Review schema extension (msg-5722ef2e2157)
_CONSULTANT_AGENT_TYPES = {"claude_code", "codex", "antigravity", "gemini"}
_CONSULTANT_CLOSING_REASONS = {"done", "max_turns", "envelope_exceeded", "aborted"}
_CONSULTANT_STATUSES = {"open_consult", "closed_consult"}
_CONSULTANT_REQUIRED_FIELDS = ("turns", "consultant_id", "consultant_agent_type")

# Persona-mediated Review path (workshop-lite-consult-skill-platform
# charter §2.1 + chunk-0 PG-1(a) ratify — UNION/DISCRIMINATOR-BY-SOURCE
# keyed on `persona_used` field presence). The /consult skill writes
# this shape; the existing /record-review skill never touches it.
# Existing reviews/* entries are grandfathered by-construction (they
# lack `persona_used` → routed to the existing closed-enum path).
_PERSONA_REVIEW_REQUIRED = (
    "id", "type", "review_type", "title", "status",
    "scope", "created_at", "author", "owner_user",
    "mode", "decision", "persona_used", "target_entity_id", "model",
)
_PERSONA_REVIEW_STATUSES = {"landed", "superseded"}
_REVIEW_MODES = {"evaluative", "generative"}
_REVIEW_DECISIONS_EVAL = {"PROCEED", "AMEND", "RETHINK"}
_REVIEW_DECISIONS_GEN = {"N/A"}
_PERSONA_REVIEW_LIST_FIELDS = (
    "linked_decisions", "linked_reviews", "linked_msg_ids",
    "linked_issues", "linked_handoffs", "linked_conversations",
    "linked_prds",
)


def validate_review(fm: dict) -> None:
    """Validate Review frontmatter — DISCRIMINATOR-BY-SOURCE.

    Per workshop-lite-consult-skill-platform charter chunk-0 PG-1(a)
    ratify: two coexisting sub-schemas keyed on ``persona_used`` field
    presence.

    - **Existing closed-enum path** (no ``persona_used``): hand-authored
      Review per D14/D16 — review_type ∈ {adversarial, collaborative,
      synthesis, research, cross-check-resolution}; status ∈
      {in_progress, completed}; ``findings`` list with severity+summary.
      This is what the existing ``/record-review`` skill writes; all
      pre-charter ``docs/reviews/*`` entries land here by construction.
    - **Persona-mediated path** (``persona_used`` present): consult-
      mediated Review from ``/consult <persona-slug> <target>`` — open
      review_type (persona-slug); status ∈ {landed, superseded}; +mode
      + decision + persona_used + target_entity_id + model; findings
      (evaluative-mode) xor insights (generative-mode).

    The dispatcher is purely structural: the presence of ``persona_used``
    selects the sub-validator. No filesystem lookups (validator stays
    pure-string per Hard Rule 7 / parley-agnostic discipline). A
    fat-fingered field name in either path surfaces as a clear
    "missing required field" error specific to that sub-schema.
    """
    if "persona_used" in fm:
        _validate_review_persona_path(fm)
    else:
        _validate_review_existing_path(fm)


def _validate_review_existing_path(fm: dict) -> None:
    """Validate the existing closed-enum Review path (D14/D16).

    See :func:`validate_review` for the dispatcher contract and the
    PG-1(a) ratify rationale.
    """
    errors: list[str] = []

    for field in _REVIEW_REQUIRED:
        if field not in fm:
            errors.append(f"missing required field: {field}")
        elif fm[field] in (None, ""):
            errors.append(f"required field is empty: {field}")

    type_val = fm.get("type")
    if type_val is not None and type_val != "review":
        errors.append(f"type must be 'review', got: {type_val!r}")

    status = fm.get("status")
    if status is not None and status not in _REVIEW_STATUSES:
        errors.append(
            f"status must be one of {sorted(_REVIEW_STATUSES)}, got: {status!r}"
        )

    review_type = fm.get("review_type")
    if review_type is not None and review_type not in _REVIEW_TYPES:
        errors.append(
            f"review_type must be one of {sorted(_REVIEW_TYPES)}, got: {review_type!r}"
        )

    _check_scope(fm.get("scope"), errors)
    _check_paired_sprint_stage(fm, errors)

    # Cohort HH chunk-6 consultant path (msg-5722ef2e2157 / @par-plan
    # planner-to-planner cross-substrate forwarding). When
    # review_type=consultant: status restricted to {open_consult,
    # closed_consult}; turns/consultant_id/consultant_agent_type
    # REQUIRED; closing_reason REQUIRED at closed_consult; findings
    # NOT required (growing-body Turn N convention per draft §3
    # replaces the findings list). Per Q4 ratify msg-0565d9dc4318:
    # consultant-fields are REQUIRED-when-consultant; ABSENT otherwise.
    if review_type == "consultant":
        if status is not None and status not in _CONSULTANT_STATUSES:
            errors.append(
                f"review_type=consultant requires status ∈ "
                f"{sorted(_CONSULTANT_STATUSES)}, got: {status!r}"
            )
        for field in _CONSULTANT_REQUIRED_FIELDS:
            if field not in fm:
                errors.append(
                    f"review_type=consultant: missing required field: {field}"
                )
            elif fm[field] in (None, ""):
                errors.append(
                    f"review_type=consultant: {field} must be non-empty"
                )
        turns = fm.get("turns")
        if turns is not None and not isinstance(turns, int):
            errors.append(
                f"review_type=consultant: turns must be int, got: {type(turns).__name__}"
            )
        agent_type = fm.get("consultant_agent_type")
        if agent_type is not None and agent_type not in _CONSULTANT_AGENT_TYPES:
            errors.append(
                f"review_type=consultant: consultant_agent_type must be one of "
                f"{sorted(_CONSULTANT_AGENT_TYPES)}, got: {agent_type!r}"
            )
        if status == "closed_consult":
            closing_reason = fm.get("closing_reason")
            if "closing_reason" not in fm:
                errors.append(
                    "review_type=consultant + status=closed_consult: missing "
                    "required field: closing_reason"
                )
            elif closing_reason not in _CONSULTANT_CLOSING_REASONS:
                errors.append(
                    f"review_type=consultant + status=closed_consult: "
                    f"closing_reason must be one of "
                    f"{sorted(_CONSULTANT_CLOSING_REASONS)}, got: {closing_reason!r}"
                )
        # Consultant path skips the findings check below (growing-body
        # Turn N sections in body replace the findings list).
        for field in _REVIEW_LIST_FIELDS:
            value = fm.get(field)
            if value is not None and not isinstance(value, list):
                errors.append(
                    f"{field} must be a list (may be empty), got: {type(value).__name__}"
                )
        if errors:
            raise ValidationError(errors)
        return

    findings = fm.get("findings")
    if "findings" not in fm:
        errors.append("missing required field: findings")
    elif findings is None:
        errors.append("findings must be a list (may be empty), got: None")
    elif not isinstance(findings, list):
        errors.append("findings must be a list (may be empty)")
    elif review_type == "cross-check-resolution":
        # Sprint S-B D1=A — the cross-check-resolution artifact's
        # findings are STRUCTURED PER-SEAT VERDICTS (seat / verdict /
        # measured_sha / scope_subset / deferred_lanes), NOT the
        # generic severity+summary finding shape. Non-empty REQUIRED
        # (a resolution with zero seat-verdicts is not a cross-check
        # resolution). This branch — and the accurate_trail mandate
        # below — fire ONLY for this review_type value; existing
        # review_type values keep the severity+summary path untouched
        # (grandfathering by-construction, R-A).
        if not findings:
            errors.append(
                "review_type=cross-check-resolution requires a non-empty "
                "findings list of per-seat verdicts"
            )
        for i, finding in enumerate(findings):
            if not isinstance(finding, dict):
                errors.append(f"findings[{i}] must be a mapping")
                continue
            for key in _XCHECK_SEAT_REQUIRED:
                if key not in finding:
                    errors.append(
                        f"findings[{i}] (cross-check-resolution) missing "
                        f"required key: {key}"
                    )
                elif finding[key] in (None, ""):
                    errors.append(
                        f"findings[{i}].{key} must be non-empty"
                    )
            v = finding.get("verdict")
            if v is not None and v not in _XCHECK_VERDICTS:
                errors.append(
                    f"findings[{i}].verdict must be one of "
                    f"{sorted(_XCHECK_VERDICTS)}, got: {v!r}"
                )
    else:
        for i, finding in enumerate(findings):
            if not isinstance(finding, dict):
                errors.append(f"findings[{i}] must be a mapping")
                continue
            if "severity" not in finding:
                errors.append(f"findings[{i}] missing required key: severity")
            elif finding["severity"] not in _FINDING_SEVERITIES:
                errors.append(
                    f"findings[{i}].severity must be one of "
                    f"{sorted(_FINDING_SEVERITIES)}, got: {finding['severity']!r}"
                )
            if "summary" not in finding:
                errors.append(f"findings[{i}] missing required key: summary")
            elif finding["summary"] in (None, ""):
                errors.append(f"findings[{i}].summary must be non-empty")
            elif not isinstance(finding["summary"], str):
                errors.append(f"findings[{i}].summary must be a string")

    # Sprint S-B D1=A + Q4(STRONGER) + R-A — the 4.6f accurate-trail
    # is VALIDATOR-MANDATORY for the cross-check-resolution artifact
    # type (a typed record missing/empty it FAILS validation; a
    # template-default a future record could omit would be the
    # false-eliminate-by-construction-lock the genuine validator-hard
    # rule exists to prevent). Keyed on the new review_type value ⇒
    # grandfathering is BY-CONSTRUCTION: existing reviews/ entities
    # (other review_type values) and the prose
    # decisions/2026-05-16-04..11 (not reviews/ entities) STRUCTURALLY
    # cannot reach this branch — the rule is unmatchable on every
    # existing record, not exclusion-claused.
    if review_type == "cross-check-resolution":
        at = fm.get("accurate_trail")
        if "accurate_trail" not in fm:
            errors.append(
                "review_type=cross-check-resolution missing required "
                "field: accurate_trail (the mandatory 4.6f "
                "structured accurate-trail section)"
            )
        elif at in (None, "", [], {}):
            errors.append(
                "accurate_trail must be non-empty for "
                "review_type=cross-check-resolution (the 4.6f "
                "accurate-trail section: adjudications-both-ways / "
                "scrum-master-own-errors / dual-independent-verdicts)"
            )

    for list_field in _REVIEW_LIST_FIELDS:
        val = fm.get(list_field)
        if val is not None and not isinstance(val, list):
            errors.append(f"{list_field} must be a list if present")

    if errors:
        raise ValidationError(errors)


def _validate_review_persona_path(fm: dict) -> None:
    """Validate the persona-mediated Review path (charter §2.1 + PG-1(a)).

    Required-fields layer + open ``review_type`` (persona-slug) +
    ``status`` ∈ {landed, superseded} + ``mode`` ∈ {evaluative,
    generative} + ``decision`` per mode + ``findings`` (eval) xor
    ``insights`` (gen). The supersede chain (HR-#7): ``status=superseded``
    requires ``superseded_by`` (forward pointer to the new review id);
    optional ``supersedes`` carries the back-pointer for chain
    traversal.

    Per the forward-only cross-link doctrine (PG-9 ratify), the
    Review carries ``target_entity_id`` (the explicit target) AND a
    ``linked_<target-kind>: [<target-slug>]`` forward link — the
    target entity is NEVER mutated; reverse projection is derived on
    the maintained ledger link index exposed via
    :func:`cross_links.derived_reverse_links`.
    """
    errors: list[str] = []

    for field in _PERSONA_REVIEW_REQUIRED:
        if field not in fm:
            errors.append(f"missing required field: {field}")
        elif fm[field] in (None, ""):
            errors.append(f"required field is empty: {field}")

    type_val = fm.get("type")
    if type_val is not None and type_val != "review":
        errors.append(f"type must be 'review', got: {type_val!r}")

    status = fm.get("status")
    if status is not None and status not in _PERSONA_REVIEW_STATUSES:
        errors.append(
            f"status must be one of {sorted(_PERSONA_REVIEW_STATUSES)} "
            f"(persona-mediated path), got: {status!r}"
        )

    mode = fm.get("mode")
    if mode is not None and mode not in _REVIEW_MODES:
        errors.append(
            f"mode must be one of {sorted(_REVIEW_MODES)}, got: {mode!r}"
        )

    decision = fm.get("decision")
    if mode == "evaluative":
        if decision is not None and decision not in _REVIEW_DECISIONS_EVAL:
            errors.append(
                f"mode=evaluative requires decision ∈ "
                f"{sorted(_REVIEW_DECISIONS_EVAL)}, got: {decision!r}"
            )
    elif mode == "generative":
        if decision is not None and decision not in _REVIEW_DECISIONS_GEN:
            errors.append(
                f"mode=generative requires decision ∈ "
                f"{sorted(_REVIEW_DECISIONS_GEN)} "
                f"(decision='N/A' for generative mode), got: {decision!r}"
            )

    has_findings = "findings" in fm and fm["findings"] is not None
    has_insights = "insights" in fm and fm["insights"] is not None
    if mode == "evaluative":
        if not has_findings:
            errors.append(
                "mode=evaluative requires findings (list, may be empty)"
            )
        if has_insights:
            errors.append(
                "mode=evaluative must not carry insights "
                "(findings xor insights per charter §2.1)"
            )
    elif mode == "generative":
        if not has_insights:
            errors.append(
                "mode=generative requires insights (list, may be empty)"
            )
        if has_findings:
            errors.append(
                "mode=generative must not carry findings "
                "(findings xor insights per charter §2.1)"
            )

    findings = fm.get("findings")
    if has_findings and not isinstance(findings, list):
        errors.append("findings must be a list (may be empty)")
    elif has_findings and isinstance(findings, list):
        for i, finding in enumerate(findings):
            if not isinstance(finding, dict):
                errors.append(f"findings[{i}] must be a mapping")
                continue
            sev = finding.get("severity")
            if sev is None:
                errors.append(f"findings[{i}] missing required key: severity")
            elif sev not in _FINDING_SEVERITIES:
                errors.append(
                    f"findings[{i}].severity must be one of "
                    f"{sorted(_FINDING_SEVERITIES)}, got: {sev!r}"
                )
            summary = finding.get("summary")
            if summary is None or summary == "":
                errors.append(f"findings[{i}].summary must be non-empty")
            elif not isinstance(summary, str):
                errors.append(f"findings[{i}].summary must be a string")

    insights = fm.get("insights")
    if has_insights and not isinstance(insights, list):
        errors.append("insights must be a list (may be empty)")
    elif has_insights and isinstance(insights, list):
        for i, ins in enumerate(insights):
            if not isinstance(ins, dict):
                errors.append(f"insights[{i}] must be a mapping")
                continue
            category = ins.get("category")
            if category is None or category == "":
                errors.append(f"insights[{i}].category must be non-empty")
            elif not isinstance(category, str):
                errors.append(f"insights[{i}].category must be a string")
            summary = ins.get("summary")
            if summary is None or summary == "":
                errors.append(f"insights[{i}].summary must be non-empty")
            elif not isinstance(summary, str):
                errors.append(f"insights[{i}].summary must be a string")

    _check_scope(fm.get("scope"), errors)
    _check_paired_sprint_stage(fm, errors)

    if status == "superseded":
        sby = fm.get("superseded_by")
        if not isinstance(sby, str) or not sby:
            errors.append(
                "status=superseded requires superseded_by "
                "(forward pointer to the new review id; HR-#7 supersede chain)"
            )

    sby_present = fm.get("superseded_by")
    if sby_present is not None and not isinstance(sby_present, str):
        errors.append("superseded_by must be a string if present")
    supersedes = fm.get("supersedes")
    if supersedes is not None and not isinstance(supersedes, str):
        errors.append("supersedes must be a string if present")

    for list_field in _PERSONA_REVIEW_LIST_FIELDS:
        val = fm.get(list_field)
        if val is not None and not isinstance(val, list):
            errors.append(f"{list_field} must be a list if present")

    if errors:
        raise ValidationError(errors)


# ---------------------------------------------------------------------------
# Sprint 5: Task-line parser-validator (D20.A) + Conversation validator (§6 + D22-D25)
# ---------------------------------------------------------------------------

# BC1.5 — task is an R6 six-state kind (spec §2.3 / §11). The explicit
# `status:` field is AUTHORITATIVE; the checkbox is a coarse visual:
#   `[ ]` = created | picked-up   ·  `[~]` = in-progress | verified
#   `[x]` = done | cleaned-up      ·  `[!]` = block-signal OVERLAY (§9) —
# NOT an R6 status; the underlying R6 status is unchanged beneath a block.
_TASK_STATUSES = {"created", "picked-up", "in-progress", "verified", "done", "cleaned-up"}
# v1 4-state → R6 migration map (spec §2.3 / §C.6). `blocked` is NOT an R6
# status (becomes a block-signal, §9); on read it best-effort maps to
# in-progress + an advisory to raise a block-signal.
_TASK_V1_TO_R6 = {
    "pending": "created",
    "in_progress": "in-progress",
    "completed": "done",
    "blocked": "in-progress",
}
# Checkbox char → (bucket-default-status, other-status-in-bucket). The default
# is omitted from metadata (canonical-only); the other carries explicit status.
_CHECKBOX_BUCKET = {
    " ": ("created", "picked-up"),
    "~": ("in-progress", "verified"),
    "x": ("done", "cleaned-up"),
}
# R6 status → canonical checkbox char.
_R6_TO_CHECKBOX = {
    "created": " ", "picked-up": " ",
    "in-progress": "~", "verified": "~",
    "done": "x", "cleaned-up": "x",
}
_TASK_META_FORBIDDEN_CHARS = frozenset(";)],")  # Q1b: forbidden in scalar values
_TASK_LINE_RE = re.compile(
    r"^- \[([ x~!])\] \*\*(task-[A-Za-z0-9._\-]+)\*\* — (.*?)(?: \(([^)]*)\))?$"
)
_LIST_LITERAL_RE = re.compile(r"^\[(.*)\]$")


def _parse_task_metadata(block: str) -> dict:
    """Parse the inside of a `(...)` metadata block per D20.A into a kv dict.

    Format: ``key1: value1; key2: value2; key3: [item1, item2]``. Each value is
    either a scalar string or a list (recognized by leading/trailing brackets).
    Forbidden chars in scalar values OR list items (Q1b): ``; ) ] ,`` — the list
    delimiter ``,`` is structural, not a value-char, so list items themselves
    cannot contain ``,``. Raises ``ValidationError`` on parse errors.
    """
    errors: list[str] = []
    out: dict = {}
    for kv_idx, raw in enumerate(block.split(";")):
        kv = raw.strip()
        if not kv:
            continue
        if ":" not in kv:
            errors.append(f"metadata kv #{kv_idx} missing ':': {kv!r}")
            continue
        key, _, value = kv.partition(":")
        key = key.strip()
        value = value.strip()
        if not key:
            errors.append(f"metadata kv #{kv_idx} has empty key: {raw!r}")
            continue
        m = _LIST_LITERAL_RE.match(value)
        if m:
            inside = m.group(1)
            items = [item.strip() for item in inside.split(",") if item.strip()]
            for item in items:
                bad = set(item) & _TASK_META_FORBIDDEN_CHARS
                if bad:
                    errors.append(
                        f"metadata {key!r} list item {item!r} contains "
                        f"forbidden char(s): {sorted(bad)}"
                    )
            out[key] = items
        else:
            bad = set(value) & _TASK_META_FORBIDDEN_CHARS
            if bad:
                errors.append(
                    f"metadata {key!r} value {value!r} contains "
                    f"forbidden char(s): {sorted(bad)}"
                )
            out[key] = value
    if errors:
        raise ValidationError(errors)
    return out


def validate_task_line(line: str, sprint_id: str | None = None) -> tuple[dict, list[str]]:
    """Parse and validate a single ``tasks.md`` task line per D20.A.

    Returns ``(parsed_dict, warnings_list)``. Raises ``ValidationError`` on
    parse/schema errors.

    ``parsed_dict`` keys:
        ``id``, ``type='task'``, ``status``, ``description``, ``sprint_id``,
        ``assignee``, ``linked_issues``, ``linked_decisions``. Extra metadata
        keys (e.g., ``reason``, ``blocker``) pass through.

    Warnings (non-blocking, advisory; Q2b):
        - ``status=blocked`` without ``reason`` or ``blocker`` key.
    """
    line = line.rstrip("\n")

    m = _TASK_LINE_RE.match(line)
    if not m:
        raise ValidationError([f"task line does not match D20.A format: {line!r}"])

    checkbox, task_id, description, meta_inner = m.groups()
    description = description.rstrip()
    errors: list[str] = []
    warnings: list[str] = []

    meta = _parse_task_metadata(meta_inner) if meta_inner else {}

    # Derive sprint_id from task_id (id format: task-<sprint>.<NN>)
    body = task_id[len("task-"):]
    derived_sprint_id: str | None = None
    if "." not in body:
        errors.append(f"task id missing per-sprint counter '.NN': {task_id!r}")
    else:
        derived_sprint_id, _, nn = body.rpartition(".")
        if not derived_sprint_id:
            errors.append(f"task id has empty sprint prefix: {task_id!r}")
        if not nn.isdigit():
            errors.append(f"task id per-sprint counter must be digits, got: {nn!r}")

    if (
        sprint_id is not None
        and derived_sprint_id is not None
        and derived_sprint_id != sprint_id
    ):
        errors.append(
            f"task id sprint prefix {derived_sprint_id!r} does not match "
            f"expected sprint_id {sprint_id!r}"
        )

    # BC1.5 — R6 six-state resolution. The explicit `status:` field is
    # AUTHORITATIVE; the checkbox is a coarse visual. `[!]` is a block-signal
    # overlay (§9), NOT an R6 status — the underlying R6 status is unchanged.
    explicit_status = meta.pop("status", None) if isinstance(meta, dict) else None
    block_overlay = checkbox == "!"
    status: str | None = None
    if explicit_status is not None and explicit_status in _TASK_V1_TO_R6:
        # Legacy v1 4-state on-disk value — back-compat (§C.6 additive-forward).
        # Map to R6 + advise migration; tolerate checkbox-bucket mismatch.
        mapped = _TASK_V1_TO_R6[explicit_status]
        warnings.append(
            f"task {task_id} carries legacy v1 status {explicit_status!r}; "
            f"R6 equivalent is {mapped!r} (run migrate-tasks to canonicalize)"
        )
        if explicit_status == "blocked":
            warnings.append(
                f"task {task_id}: 'blocked' is no longer an R6 status — raise a "
                "block-signal (§9) and set the underlying R6 status explicitly"
            )
        status = mapped
    elif explicit_status is not None:
        # R6 explicit status — authoritative, with canonical-only discipline.
        if explicit_status not in _TASK_STATUSES:
            errors.append(
                f"status must be one of {sorted(_TASK_STATUSES)}, "
                f"got: {explicit_status!r}"
            )
        elif block_overlay:
            status = explicit_status  # `[!]` overlay carries explicit R6 status
        else:
            bucket = _CHECKBOX_BUCKET.get(checkbox, ())
            if explicit_status not in bucket:
                errors.append(
                    f"status {explicit_status!r} does not match checkbox "
                    f"'[{checkbox}]' (allowed for this checkbox: {list(bucket)})"
                )
            elif explicit_status == bucket[0]:
                errors.append(
                    f"status {explicit_status!r} is the default for '[{checkbox}]'; "
                    "omit '(status: ...)' (canonical-only)"
                )
            else:
                status = explicit_status
    else:
        # No explicit status — derive the bucket default from the checkbox.
        if block_overlay:
            # `[!]` with no explicit status: underlying R6 status defaults to
            # in-progress; advise stamping it explicitly.
            warnings.append(
                f"task {task_id}: block-signal overlay '[!]' without an explicit "
                "underlying R6 status — defaulting to 'in-progress'"
            )
            status = "in-progress"
        else:
            status = _CHECKBOX_BUCKET[checkbox][0]

    assignee = meta.pop("assignee", None)
    if assignee is not None and not isinstance(assignee, str):
        errors.append("assignee must be a string if present")

    def _coerce_list(val: object, key: str) -> list:
        if val is None:
            return []
        if isinstance(val, list):
            return val
        if isinstance(val, str):
            return [val] if val else []
        errors.append(f"{key} must be a list or string, got: {type(val).__name__}")
        return []

    linked_issues = _coerce_list(meta.pop("linked_issues", []), "linked_issues")
    linked_decisions = _coerce_list(meta.pop("linked_decisions", []), "linked_decisions")

    if not description:
        errors.append("description must be non-empty")

    if errors:
        raise ValidationError(errors)

    if block_overlay and "reason" not in meta and "blocker" not in meta:
        warnings.append(
            f"task {task_id} has a block-signal overlay '[!]' but no 'reason' or "
            "'blocker' key (advisory only)"
        )

    parsed = {
        "id": task_id,
        "type": "task",
        "status": status,
        "block_overlay": block_overlay,
        "description": description,
        "sprint_id": derived_sprint_id,
        "assignee": assignee,
        "linked_issues": linked_issues,
        "linked_decisions": linked_decisions,
    }
    for k, v in meta.items():
        if k not in parsed:
            parsed[k] = v

    return parsed, warnings


_CONVERSATION_ZONES = {"sprint", "cross-sprint", "pre-sprint"}
_CONVERSATION_REQUIRED = (
    "id", "type", "title", "topic", "zone",
    "participants", "verbatim_msg_range", "created_at",
)
_CONVERSATION_LIST_FIELDS = (
    "participants",
    "linked_design_docs",
    "linked_decisions",
    "linked_reviews",
    "linked_issues",
    "linked_handoffs",
    "linked_msg_ids",
)


def validate_conversation(fm: dict) -> None:
    """Validate Conversation frontmatter per §6 + D22/D24/D25 (Sprint 5).

    D22: ``verbatim_msg_range`` is a list of exactly 2 (each msg-id string or
    null — null pair allowed for the explicit-empty range when scrollback had
    no matching records).
    D24: ``participants`` is a list of ``@<id>`` strings.
    D25: ``zone`` ∈ {sprint, cross-sprint, pre-sprint}; when ``zone=sprint``,
    ``sprint_id`` and ``stage`` are required and paired.
    """
    errors: list[str] = []

    for field in _CONVERSATION_REQUIRED:
        if field not in fm:
            errors.append(f"missing required field: {field}")
        elif field == "verbatim_msg_range":
            continue
        elif field == "participants":
            continue
        elif fm[field] in (None, ""):
            errors.append(f"required field is empty: {field}")

    type_val = fm.get("type")
    if type_val is not None and type_val != "conversation":
        errors.append(f"type must be 'conversation', got: {type_val!r}")

    zone = fm.get("zone")
    if zone is not None and zone not in _CONVERSATION_ZONES:
        errors.append(
            f"zone must be one of {sorted(_CONVERSATION_ZONES)}, got: {zone!r}"
        )

    sprint_id = fm.get("sprint_id")
    stage = fm.get("stage")
    if zone == "sprint":
        if sprint_id in (None, ""):
            errors.append("zone=sprint requires sprint_id")
        if stage in (None, ""):
            errors.append("zone=sprint requires stage")
    _check_paired_sprint_stage(fm, errors)

    vmr = fm.get("verbatim_msg_range")
    if vmr is None:
        errors.append("verbatim_msg_range must be a list of 2 (may be [null, null])")
    elif not isinstance(vmr, list):
        errors.append("verbatim_msg_range must be a list of 2")
    elif len(vmr) != 2:
        errors.append(
            f"verbatim_msg_range must have exactly 2 elements, got {len(vmr)}"
        )
    else:
        for i, val in enumerate(vmr):
            if val is not None and not isinstance(val, str):
                errors.append(f"verbatim_msg_range[{i}] must be a string or null")

    participants = fm.get("participants")
    if participants is None:
        errors.append("participants must be a list (may be empty)")
    elif not isinstance(participants, list):
        errors.append("participants must be a list")
    else:
        for i, p in enumerate(participants):
            if not isinstance(p, str):
                errors.append(
                    f"participants[{i}] must be a string (e.g., '@work')"
                )
            elif not p.startswith("@"):
                errors.append(
                    f"participants[{i}] must start with '@', got: {p!r}"
                )

    for list_field in _CONVERSATION_LIST_FIELDS:
        if list_field == "participants":
            continue  # already handled above
        val = fm.get(list_field)
        if val is not None and not isinstance(val, list):
            errors.append(f"{list_field} must be a list if present")

    if errors:
        raise ValidationError(errors)


# ---------------------------------------------------------------------------
# WIP-claim (Phase 1 of workshop-lite re-arch arc, sub-spec
# docs/design/2026-05-29-wl-wip-claim-spec.md)
# ---------------------------------------------------------------------------

_WIP_CLAIM_STATES = {"claimed", "committed", "released", "abandoned"}
# Verifier-α MED #3 closure: `owner_user` is per master design §3.2 +
# D-WL-11 ("All new entity types gain owner_user") and is shown in the
# sub-spec §3 frontmatter example. The writer always supplies it (default
# `user/local`); enforcing it here closes the silent-bypass on hand-
# authored / migration-imported claims that lack the field.
_WIP_CLAIM_REQUIRED = (
    "id", "type", "title", "seat", "paths", "scope",
    "status", "token_state", "expires_at",
    "created_at", "created_by", "owner_user",
)
_WIP_CLAIM_LIST_FIELDS = (
    "paths", "linked_sprints", "linked_decisions", "linked_msg_ids",
)
# Sub-spec §3: WIP-claim scope accepts the same taxonomy as other
# entities PLUS ``arc:<id>`` (the re-arch arc-level scope, used for
# multi-sprint arc work). The base ``_SCOPE_PREFIXES`` tuple is
# entity-shared and predates the arc: addition — wip extends it locally.
_WIP_CLAIM_SCOPE_PREFIXES = ("sprint:", "repo:", "design:", "arc:", "decision:")


def _check_wip_scope(value: object, errors: list[str]) -> None:
    if value in (None, ""):
        return  # required-empty already flagged
    if not isinstance(value, str) or not value.startswith(
        _WIP_CLAIM_SCOPE_PREFIXES
    ):
        errors.append(
            f"scope must start with one of {list(_WIP_CLAIM_SCOPE_PREFIXES)},"
            f" got: {value!r}"
        )


# ---------------------------------------------------------------------------
# EpicShipped (Phase 2 of workshop-lite re-arch arc, sub-spec
# docs/design/2026-05-29-wl-sync-from-parley-spec.md §5)
# ---------------------------------------------------------------------------

_EPIC_SHIPPED_STATUSES = {"shipped", "superseded"}
_EPIC_SHIPPED_REQUIRED = (
    "id", "type", "title", "status", "scope",
    "shipped_at", "shipped_by_seat", "parley_ship_epic_msg_id",
    "created_at", "created_by", "owner_user",
)
_EPIC_SHIPPED_LIST_FIELDS = (
    "load_artifacts", "linked_decisions", "linked_msg_ids",
)
# Sub-spec §5.1: scope accepts ``arc:<id>``, ``sprint:<id>``, or
# ``repo:<area>``. Mirrors wip_claim scope-prefix extension.
_EPIC_SHIPPED_SCOPE_PREFIXES = ("arc:", "sprint:", "repo:")
# Sub-spec §5.1: ``created_by_source`` enum.
_EPIC_SHIPPED_CREATED_BY_SOURCES = {"sync-daemon", "manual", "other"}


def _check_epic_shipped_scope(value: object, errors: list[str]) -> None:
    if value in (None, ""):
        return
    if not isinstance(value, str) or not value.startswith(
        _EPIC_SHIPPED_SCOPE_PREFIXES
    ):
        errors.append(
            f"scope must start with one of "
            f"{list(_EPIC_SHIPPED_SCOPE_PREFIXES)}, got: {value!r}"
        )


def validate_epic_shipped(fm: dict) -> None:
    """Validate EpicShipped frontmatter per sub-spec §5.1.

    Strict; raises ``ValidationError`` on schema violations. The
    ``status`` enum is ``{shipped, superseded}``; ``shipped`` is the
    terminal/creation state, ``superseded`` is reached only via a later
    EPIC_SHIPPED with ``supersedes_msg_id``.

    ``created_by_source`` carries the provenance flag introduced by
    composite-audit LOW #16 — must be one of ``{sync-daemon, manual,
    other}`` when present.
    """
    errors: list[str] = []

    for field in _EPIC_SHIPPED_REQUIRED:
        if field not in fm:
            errors.append(f"missing required field: {field}")
        elif fm[field] in (None, ""):
            errors.append(f"required field is empty: {field}")

    type_val = fm.get("type")
    if type_val is not None and type_val != "epic_shipped":
        errors.append(f"type must be 'epic_shipped', got: {type_val!r}")

    status = fm.get("status")
    if status is not None and status not in _EPIC_SHIPPED_STATUSES:
        errors.append(
            f"status must be one of {sorted(_EPIC_SHIPPED_STATUSES)}, "
            f"got: {status!r}"
        )

    _check_epic_shipped_scope(fm.get("scope"), errors)

    cbs = fm.get("created_by_source")
    if cbs is not None and cbs not in _EPIC_SHIPPED_CREATED_BY_SOURCES:
        errors.append(
            f"created_by_source must be one of "
            f"{sorted(_EPIC_SHIPPED_CREATED_BY_SOURCES)}, got: {cbs!r}"
        )

    for list_field in _EPIC_SHIPPED_LIST_FIELDS:
        val = fm.get(list_field)
        if val is not None and not isinstance(val, list):
            errors.append(f"{list_field} must be a list if present")

    if errors:
        raise ValidationError(errors)


def validate_wip_claim(fm: dict) -> None:
    """Validate WIP-claim frontmatter per sub-spec §3.

    Strict; raises ``ValidationError`` on schema violations. The
    advisory rules V1-V5 (see ``run_wip_claim_checks``) are SEPARATE
    from this schema validator — they are inter-entity / inter-state
    drift signals that fire from ``validate.run_checks``, never from
    the entity-write path.

    Per composite-audit HIGH #1 + sub-spec §3 amendment: ``status`` and
    ``token_state`` are isomorphic 1:1 by NAME (both use the same enum
    ``{claimed, committed, released, abandoned}``; ``claimed`` is the
    active-state name — NOT ``active``). The validator enforces the
    isomorphism: a mismatch is a schema error.
    """
    errors: list[str] = []

    for field in _WIP_CLAIM_REQUIRED:
        if field not in fm:
            errors.append(f"missing required field: {field}")
        elif fm[field] in (None, ""):
            errors.append(f"required field is empty: {field}")

    type_val = fm.get("type")
    if type_val is not None and type_val != "wip_claim":
        errors.append(f"type must be 'wip_claim', got: {type_val!r}")

    status = fm.get("status")
    token_state = fm.get("token_state")
    if status is not None and status not in _WIP_CLAIM_STATES:
        errors.append(
            f"status must be one of {sorted(_WIP_CLAIM_STATES)}, "
            f"got: {status!r}"
        )
    if token_state is not None and token_state not in _WIP_CLAIM_STATES:
        errors.append(
            f"token_state must be one of {sorted(_WIP_CLAIM_STATES)}, "
            f"got: {token_state!r}"
        )
    # Isomorphism by name (composite-audit HIGH #1 amendment):
    if (
        status is not None
        and token_state is not None
        and status != token_state
    ):
        errors.append(
            f"status ({status!r}) and token_state ({token_state!r}) "
            "must be equal (isomorphic 1:1 by name; sub-spec §3 amendment)"
        )

    _check_wip_scope(fm.get("scope"), errors)
    _check_paired_sprint_stage(fm, errors)

    paths = fm.get("paths")
    if paths is None:
        pass  # already flagged as required-empty above
    elif not isinstance(paths, list):
        errors.append("paths must be a list")
    elif not paths:
        errors.append("paths must be a non-empty list")
    else:
        for i, p in enumerate(paths):
            if not isinstance(p, str):
                errors.append(f"paths[{i}] must be a string, got: {type(p).__name__}")

    for list_field in _WIP_CLAIM_LIST_FIELDS:
        if list_field == "paths":
            continue  # already handled above
        val = fm.get(list_field)
        if val is not None and not isinstance(val, list):
            errors.append(f"{list_field} must be a list if present")

    if errors:
        raise ValidationError(errors)


# ---------------------------------------------------------------------------
# Standing-dispatch (Phase 2 of workshop-lite re-arch arc, sub-spec
# docs/design/2026-05-29-wl-standing-dispatch-spec.md)
# ---------------------------------------------------------------------------

_STANDING_DISPATCH_STATUSES = {
    "standing", "satisfied", "superseded", "expired",
}
_STANDING_DISPATCH_PURPOSES = {
    "charter", "brief", "governance", "routing", "other",
}
_STANDING_DISPATCH_REQUIRED = (
    "id", "type", "title", "status", "purpose", "scope",
    "recipients", "expected_outcome",
    "created_at", "created_by", "owner_user",
)
_STANDING_DISPATCH_LIST_FIELDS = (
    "recipients", "linked_msg_ids", "linked_decisions",
    "linked_handoffs", "linked_reviews",
)
# Sub-spec §3: standing-dispatch scope accepts arc:, sprint:, repo:,
# design: (mirrors the WIP-claim widened taxonomy).
_STANDING_DISPATCH_SCOPE_PREFIXES = (
    "sprint:", "repo:", "design:", "arc:", "decision:",
)


def _check_standing_dispatch_scope(value: object, errors: list[str]) -> None:
    if value in (None, ""):
        return  # required-empty already flagged
    if not isinstance(value, str) or not value.startswith(
        _STANDING_DISPATCH_SCOPE_PREFIXES
    ):
        errors.append(
            f"scope must start with one of "
            f"{list(_STANDING_DISPATCH_SCOPE_PREFIXES)}, got: {value!r}"
        )


def validate_standing_dispatch(fm: dict) -> None:
    """Validate standing_dispatch frontmatter per sub-spec §3.

    Strict; raises :class:`ValidationError`. The advisory rules V1-V6
    (see :mod:`dispatch_checks`) are SEPARATE from this schema validator
    — they are inter-entity / cross-arc drift signals that fire from
    ``validate.run_checks``, never from the entity-write path.

    Per D-WL-19 element 1 (sub-spec §2.1): ``recipients`` is multi-
    recipient by construction; the list shape composes directly with
    parley primitive #1's per-(sender, recipient, msg-id) state machine.
    The validator enforces the list shape only; primitive #1 state
    lookups live at the skill / hook layer (Hard Rule 1).
    """
    errors: list[str] = []

    for field in _STANDING_DISPATCH_REQUIRED:
        if field not in fm:
            errors.append(f"missing required field: {field}")
        elif field == "recipients":
            continue  # list-shape check below
        elif fm[field] in (None, ""):
            errors.append(f"required field is empty: {field}")

    type_val = fm.get("type")
    if type_val is not None and type_val != "standing_dispatch":
        errors.append(
            f"type must be 'standing_dispatch', got: {type_val!r}"
        )

    status = fm.get("status")
    if status is not None and status not in _STANDING_DISPATCH_STATUSES:
        errors.append(
            f"status must be one of {sorted(_STANDING_DISPATCH_STATUSES)}, "
            f"got: {status!r}"
        )

    purpose = fm.get("purpose")
    if purpose is not None and purpose not in _STANDING_DISPATCH_PURPOSES:
        errors.append(
            f"purpose must be one of "
            f"{sorted(_STANDING_DISPATCH_PURPOSES)}, got: {purpose!r}"
        )

    _check_standing_dispatch_scope(fm.get("scope"), errors)
    _check_paired_sprint_stage(fm, errors)

    recipients = fm.get("recipients")
    if recipients is None:
        # already flagged as required-missing above (or required-empty)
        pass
    elif not isinstance(recipients, list):
        errors.append("recipients must be a list")
    elif not recipients:
        errors.append(
            "recipients must be a non-empty list (multi-recipient "
            "by construction per D-WL-19 element 1)"
        )
    else:
        for i, r in enumerate(recipients):
            if not isinstance(r, str):
                errors.append(
                    f"recipients[{i}] must be a string (FQID per D-RA-4), "
                    f"got: {type(r).__name__}"
                )
            elif not r:
                errors.append(f"recipients[{i}] must be non-empty")

    for list_field in _STANDING_DISPATCH_LIST_FIELDS:
        if list_field == "recipients":
            continue
        val = fm.get(list_field)
        if val is not None and not isinstance(val, list):
            errors.append(f"{list_field} must be a list if present")

    quorum = fm.get("satisfy_quorum")
    if quorum is not None and not isinstance(quorum, int):
        errors.append(
            f"satisfy_quorum must be an integer if present, got: "
            f"{type(quorum).__name__}"
        )
    elif isinstance(quorum, int) and quorum < 1:
        errors.append("satisfy_quorum must be >= 1 if set")

    par_ref = fm.get("parley_external_ref")
    if par_ref is not None and par_ref != "":
        # Per D-WL-19 element 2: workshop-lite-dispatch:// scheme
        # auto-populated by the writer. Validate the prefix when set.
        if not isinstance(par_ref, str):
            errors.append("parley_external_ref must be a string if set")
        elif not par_ref.startswith("workshop-lite-dispatch://"):
            errors.append(
                f"parley_external_ref must be a "
                f"'workshop-lite-dispatch://<id>' URI per D-WL-19 element 2, "
                f"got: {par_ref!r}"
            )

    if errors:
        raise ValidationError(errors)


# ---------------------------------------------------------------------------
# PRD (cross-repo PM-bridge supporting substrate; charter
# docs/inbox/2026-06-02-prd-entity-cross-repo-pm-bridge-charter.md)
# ---------------------------------------------------------------------------

_PRD_STATES = {
    "draft", "ratified", "converting", "technical_plan_ready", "shipped",
}
# Base required fields (every PRD regardless of state).
_PRD_REQUIRED = (
    "id", "type", "title", "state", "scope",
    "created_at", "author", "owner_user",
)
# Per-state additional required fields (chunk-0 PG-2 ratify — clean
# extension on top of base). Writer-driven flow always stamps these at
# transition-time; hand-edited bad-state fails by design (AXIS-7+8).
_PRD_PER_STATE_REQUIRED: dict[str, tuple[str, ...]] = {
    "draft": (),
    "ratified": ("ratified_at", "ratified_by"),
    "converting": ("ratified_at", "ratified_by"),
    "technical_plan_ready": (
        "ratified_at", "ratified_by", "technical_plan_url",
    ),
    "shipped": (
        "ratified_at", "ratified_by", "technical_plan_url", "shipped_sha",
    ),
}
_PRD_LIST_FIELDS = (
    "linked_msg_ids", "linked_decisions", "cross_repo_prds",
)
# Sub-spec / charter §2.2: PRD scope accepts the same taxonomy as other
# entities (sprint:, repo:, design:, arc:, decision:).
_PRD_SCOPE_PREFIXES = (
    "sprint:", "repo:", "design:", "arc:", "decision:",
)
# Charter AXIS-13: cross_repo_prds entries match `<repo>:<id>` shape
# (repo-name colon entity-id). par-p0-defect-56 multi-repo coordination
# convention (LANDed at a7d6384) is the canonical home for the URI
# grammar; we enforce the literal shape here per AXIS-13.
_CROSS_REPO_PRD_RE = re.compile(r"^[a-z0-9_-]+:[A-Za-z0-9._-]+$")

# Charter AXIS-12: PRD body REQUIRES a `## PM Summary` section
# (belt-and-suspenders alongside parley-side /translate skill). Validator
# rejects PRD bodies missing it. Case-insensitive header match per
# chunk-0 PG-3 ratify.
_PRD_BODY_PM_SUMMARY_RE = re.compile(
    r"^##\s+PM\s+Summary\s*$", re.IGNORECASE | re.MULTILINE,
)


def _check_prd_scope(value: object, errors: list[str]) -> None:
    if value in (None, ""):
        return  # required-empty already flagged
    if not isinstance(value, str) or not value.startswith(
        _PRD_SCOPE_PREFIXES
    ):
        errors.append(
            f"scope must start with one of {list(_PRD_SCOPE_PREFIXES)}, "
            f"got: {value!r}"
        )


def validate_prd(fm: dict) -> None:
    """Validate PRD frontmatter per charter §2.1 + §2.2.

    Strict; raises :class:`ValidationError`. Per chunk-0 PG-2 ratify:
    base required-fields tuple ``_PRD_REQUIRED`` first; then per-state
    conditional required-fields from ``_PRD_PER_STATE_REQUIRED`` layered
    on top. Writer-driven transition functions stamp the per-state
    fields at transition-time, so writer-driven flow always passes.

    The 5-state forward-only chain (draft → ratified → converting →
    technical_plan_ready → shipped) is encoded in
    ``STATUS_TRANSITIONS["prd"]`` (D44 matrix); this validator enforces
    state-membership of the enum.

    ``cross_repo_prds`` (charter AXIS-13): list of ``<repo>:<id>``
    refs. The URI grammar canonically lives in par-p0-defect-56's
    multi-repo coordination convention (LANDed at a7d6384); we enforce
    the literal shape here per the AXIS contract.

    ``parley_external_ref`` (chunk-0 open-Q ratify): auto-populated by
    the writer as ``workshop-lite-prd://<id>`` (D-WL-19 grammar
    mirror); validator enforces the prefix when set.
    """
    errors: list[str] = []

    for field in _PRD_REQUIRED:
        if field not in fm:
            errors.append(f"missing required field: {field}")
        elif fm[field] in (None, ""):
            errors.append(f"required field is empty: {field}")

    type_val = fm.get("type")
    if type_val is not None and type_val != "prd":
        errors.append(f"type must be 'prd', got: {type_val!r}")

    state = fm.get("state")
    if state is not None and state not in _PRD_STATES:
        errors.append(
            f"state must be one of {sorted(_PRD_STATES)}, got: {state!r}"
        )

    # Per-state required-fields layer (chunk-0 PG-2).
    if state in _PRD_PER_STATE_REQUIRED:
        for field in _PRD_PER_STATE_REQUIRED[state]:
            if field not in fm or fm[field] in (None, ""):
                errors.append(
                    f"state={state!r} requires field: {field} "
                    "(charter §2.2 per-state required-fields)"
                )

    _check_prd_scope(fm.get("scope"), errors)

    for list_field in _PRD_LIST_FIELDS:
        val = fm.get(list_field)
        if val is not None and not isinstance(val, list):
            errors.append(f"{list_field} must be a list if present")

    # cross_repo_prds entries must match <repo>:<id> shape per AXIS-13.
    xrp = fm.get("cross_repo_prds")
    if isinstance(xrp, list):
        for i, ref in enumerate(xrp):
            if not isinstance(ref, str):
                errors.append(
                    f"cross_repo_prds[{i}] must be a string, "
                    f"got: {type(ref).__name__}"
                )
            elif not _CROSS_REPO_PRD_RE.match(ref):
                errors.append(
                    f"cross_repo_prds[{i}] must match '<repo>:<id>' "
                    f"shape per charter AXIS-13 + par-p0-defect-56 "
                    f"multi-repo coordination convention, got: {ref!r}"
                )

    par_ref = fm.get("parley_external_ref")
    if par_ref is not None and par_ref != "":
        if not isinstance(par_ref, str):
            errors.append("parley_external_ref must be a string if set")
        elif not par_ref.startswith("workshop-lite-prd://"):
            errors.append(
                f"parley_external_ref must be a "
                f"'workshop-lite-prd://<id>' URI per chunk-0 open-Q "
                f"ratify (mirrors D-WL-19 grammar), got: {par_ref!r}"
            )

    if errors:
        raise ValidationError(errors)


def validate_prd_body(body: str) -> None:
    """Validate PRD body per charter AXIS-12.

    The body MUST contain a ``## PM Summary`` header (case-insensitive).
    This is the belt-and-suspenders structural marker the parley-side
    PM-bridge ``/translate`` skill echoes verbatim. Chunk-0 PG-3 ratify:
    template-default scaffolds the section, so writer-driven flow always
    passes; the rule fires on hand-stripped bodies.

    Raises :class:`ValidationError` if the section header is missing.
    """
    if not isinstance(body, str):
        raise ValidationError(["PRD body must be a string"])
    if not _PRD_BODY_PM_SUMMARY_RE.search(body):
        raise ValidationError([
            "PRD body missing required '## PM Summary' section "
            "(charter AXIS-12 belt-and-suspenders; the parley-side "
            "/translate skill echoes this section verbatim)"
        ])


# ---------------------------------------------------------------------------
# workshop-lite cohort (B) install-rollout — D1: gate + halt entities
# ---------------------------------------------------------------------------
#
# Source-of-truth issue: workshop-lite:2026-06-04-01 (full body authoritative).
# Cohort B charter: docs/inbox/2026-06-04-cohort-B-install-rollout-charter.md.
#
# Gate is a per-repo entity at ``docs/gates/<gate-id>.md`` describing a
# cross-session / external-policy hold on the consuming repo (release
# freeze, in-flight cross-session plan, incident, manual operator hold,
# etc.). The source-issue spec used the field name ``state``; the
# substrate-uniform field name is ``status`` (so STATUS_TRANSITIONS
# coverage applies; mirrors decision/issue/review/etc.). Templates
# carry ``status`` per the convention. ``state`` is NOT accepted —
# fail-fast at validate time keeps the substrate uniform.
#
# Halt is a SINGLETON entity at top-level ``HALT.md`` (NOT under
# ``docs/``) — max-discoverable on ``ls``. No status field per the
# source-issue spec (the file's existence IS the halt state; deletion
# resolves it; ``ttl_until`` exceeded is detected by the parley-side
# halt_detection_loop, not by the validator). Validator only checks
# frontmatter shape.

_GATE_STATUSES = {"open", "closed", "resolved"}
_GATE_REQUIRED = (
    "id", "type", "gate_id", "created",
    "gated_by", "status", "how_to_close",
)
_GATE_LIST_FIELDS = (
    "what_you_can_do", "what_you_cannot_do", "linked_msg_ids",
)


def validate_gate(fm: dict) -> None:
    """Validate Gate frontmatter against the workshop-lite:2026-06-04-01 schema.

    Source-issue § "Frontmatter shape" (with one substrate-uniform
    rename — ``state`` → ``status`` so STATUS_TRANSITIONS coverage
    applies). Required: ``id``, ``type=gate``, ``gate_id``, ``created``,
    ``gated_by``, ``status``, ``how_to_close``. Optional: ``plan_ref``,
    ``ttl_until``, ``what_you_can_do[]``, ``what_you_cannot_do[]``,
    ``linked_msg_ids[]``.

    status ∈ {open, closed, resolved}. ``open`` is the live-hold state;
    ``closed`` is the operator-acknowledged finalization;
    ``resolved`` is the in-flight-condition-cleared finalization
    (both terminal in the transition graph).
    """
    errors: list[str] = []

    for field in _GATE_REQUIRED:
        if field not in fm:
            errors.append(f"missing required field: {field}")
        elif fm[field] in (None, ""):
            errors.append(f"required field is empty: {field}")

    type_val = fm.get("type")
    if type_val is not None and type_val != "gate":
        errors.append(f"type must be 'gate', got: {type_val!r}")

    status = fm.get("status")
    if status is not None and status not in _GATE_STATUSES:
        errors.append(
            f"status must be one of {sorted(_GATE_STATUSES)}, got: {status!r}"
        )

    for list_field in _GATE_LIST_FIELDS:
        val = fm.get(list_field)
        if val is not None and not isinstance(val, list):
            errors.append(f"{list_field} must be a list if present")

    if errors:
        raise ValidationError(errors)


# cohort P (wl:2026-06-04-01 schema-handshake) — cross-substrate contract
# pinned in parley/docs/inbox/2026-06-05-cohort-O-track-F-halt-md-detection-cron-charter.md §1.8.
# WL substrate fields (id, type, what_i_tried) preserved alongside the
# 9-field cross-substrate contract.
_HALT_REQUIRED = (
    "id", "type", "halt_id", "halt_ts", "agent",
    "reason", "what_i_need", "ttl_until",
)
# REQ-but-nullable: field MUST be present in frontmatter; value MAY be None.
_HALT_REQUIRED_NULLABLE = ("gate_ref",)
_HALT_LIST_FIELDS = ("what_i_tried",)
# UUID4 36-char canonical form (8-4-4-4-12 hex with hyphens).
_HALT_ID_LEN = 36
# sha256 hex digest length.
_HALT_CONTENT_HASH_LEN = 64


def validate_halt(fm: dict) -> None:
    """Validate HALT frontmatter against the workshop-lite:2026-06-04-01 schema.

    Cross-substrate contract (parley Track F charter §1.8). Required:
    ``id``, ``type=halt``, ``halt_id`` (UUID4), ``halt_ts`` (ISO-8601),
    ``agent``, ``reason``, ``what_i_need``, ``ttl_until``. Required-but-
    nullable: ``gate_ref`` (field must be present; value may be None for
    non-gate-induced halts). Optional: ``contact`` (routing override),
    ``content_hash`` (sha256 hex fallback dedup), ``what_i_tried[]``.

    Renames since cohort B: ``halted_at`` → ``halt_ts`` (clean rename per
    cross-substrate parity; legacy field name rejected with actionable
    error). Lifts: ``ttl_until`` OPT→REQ (parley-side STALE detection
    needs explicit value). Drops: ``contact`` REQ→OPT (routing override
    semantics; absence falls back to substrate default routing).

    No ``status`` field — the file's existence IS the halt state;
    deletion resolves it. The parley-side halt_detection_loop
    (parley:2026-06-04-02 / Track F cohort O) emits
    ``Kind.WL_AGENT_HALT_DETECTED`` / ``_RESOLVED`` / ``_STALE`` /
    ``_SCHEMA_VIOLATION`` audit records keyed on ``halt_id`` (stable
    across body edits; mtime is NOT a dedup key). STATUS_TRANSITIONS
    coverage intentionally absent (mirrors Conversation / Handoff /
    Retrospective per D44.A).
    """
    errors: list[str] = []

    # Legacy field-name guard — explicit reject of pre-cohort-P ``halted_at``
    # so consumers get an actionable rename diagnostic, not a silent missing-
    # required-field on the new ``halt_ts`` name.
    if "halted_at" in fm and "halt_ts" not in fm:
        errors.append(
            "field 'halted_at' is legacy (pre-cohort-P); rename to 'halt_ts' "
            "per cross-substrate contract (parley Track F §1.8)"
        )

    for field in _HALT_REQUIRED:
        if field not in fm:
            errors.append(f"missing required field: {field}")
        elif fm[field] in (None, ""):
            errors.append(f"required field is empty: {field}")

    # REQ-but-nullable: presence required; None value allowed; empty string
    # NOT allowed (must be either a populated value or explicit None).
    for field in _HALT_REQUIRED_NULLABLE:
        if field not in fm:
            errors.append(f"missing required field (nullable): {field}")
        elif fm[field] == "":
            errors.append(
                f"required-nullable field is empty string (use None for absent): {field}"
            )

    type_val = fm.get("type")
    if type_val is not None and type_val != "halt":
        errors.append(f"type must be 'halt', got: {type_val!r}")

    # halt_id shape: UUID4 canonical 36-char string with hyphens. Validator
    # checks length only (not the UUID4-specific bit layout) — agent-generated
    # via uuid.uuid4() naturally satisfies the shape; manual edits get a
    # length-mismatch diagnostic.
    halt_id_val = fm.get("halt_id")
    if halt_id_val is not None and halt_id_val != "":
        if not isinstance(halt_id_val, str) or len(halt_id_val) != _HALT_ID_LEN:
            errors.append(
                f"halt_id must be a 36-char UUID4 string, got: {halt_id_val!r}"
            )

    # content_hash shape (OPTIONAL): sha256 hex digest = 64 chars. Validator
    # checks length only; not the actual hash content (parley side may recompute).
    content_hash_val = fm.get("content_hash")
    if content_hash_val is not None and content_hash_val != "":
        if not isinstance(content_hash_val, str) or len(content_hash_val) != _HALT_CONTENT_HASH_LEN:
            errors.append(
                f"content_hash must be a 64-char sha256 hex string when present, got: {content_hash_val!r}"
            )

    for list_field in _HALT_LIST_FIELDS:
        val = fm.get(list_field)
        if val is not None and not isinstance(val, list):
            errors.append(f"{list_field} must be a list if present")

    if errors:
        raise ValidationError(errors)


# ---------------------------------------------------------------------------
# BC1.2 — the 5 new kinds (spec §2.3): workflow · role-set · block-signal ·
# resume-ledger · canonical-pointer. Validators follow the established
# required-field + enum + list-shape pattern. owner_user is the Phase-4
# carry field on the 4 authored kinds (workflow / role-set / resume-ledger /
# canonical-pointer) — OPTIONAL at validation (read-time default user/local),
# REQUIRED-present only on kinds whose v1 peers already hard-require it. The
# carry-set MEMBERSHIP is enforced structurally by body_schemas (BC1.3).
# ---------------------------------------------------------------------------

_LIBRARY_LAYERS = {"built-in", "project", "user"}

_WORKFLOW_REQUIRED = (
    "id", "type", "title", "status", "stages", "library_layer",
    "is_default", "created_at", "author",
)
_WORKFLOW_STATUSES = {"draft", "active", "superseded", "retired"}


def validate_workflow(fm: dict) -> None:
    """Validate a workflow library entry (spec §2.3; DOC1 §6.4).

    A workflow is data: a declared ordered set of stages. Each stage is a dict
    with a required ``name`` and optional ``produces_artifact_kind`` +
    ``parallelizable`` (bool). ``library_layer`` ∈ {built-in, project, user};
    ``is_default`` is a bool. ``owner_user`` carries (read-time default).
    """
    errors: list[str] = []

    for field in _WORKFLOW_REQUIRED:
        if field not in fm:
            errors.append(f"missing required field: {field}")
        elif field in ("stages", "is_default"):
            continue
        elif fm[field] in (None, ""):
            errors.append(f"required field is empty: {field}")

    type_val = fm.get("type")
    if type_val is not None and type_val != "workflow":
        errors.append(f"type must be 'workflow', got: {type_val!r}")

    status = fm.get("status")
    if status is not None and status not in _WORKFLOW_STATUSES:
        errors.append(
            f"status must be one of {sorted(_WORKFLOW_STATUSES)}, got: {status!r}"
        )

    layer = fm.get("library_layer")
    if layer is not None and layer not in _LIBRARY_LAYERS:
        errors.append(
            f"library_layer must be one of {sorted(_LIBRARY_LAYERS)}, got: {layer!r}"
        )

    is_default = fm.get("is_default")
    if is_default is not None and not isinstance(is_default, bool):
        errors.append("is_default must be a bool")

    stages = fm.get("stages")
    if "stages" in fm:
        if not isinstance(stages, list) or not stages:
            errors.append("stages must be a non-empty ordered list")
        else:
            for idx, stage in enumerate(stages):
                if not isinstance(stage, dict):
                    errors.append(f"stage #{idx} must be a mapping")
                    continue
                if not stage.get("name"):
                    errors.append(f"stage #{idx} missing required 'name'")
                par = stage.get("parallelizable")
                if par is not None and not isinstance(par, bool):
                    errors.append(f"stage #{idx} parallelizable must be a bool")

    for list_field in ("linked_decisions",):
        val = fm.get(list_field)
        if val is not None and not isinstance(val, list):
            errors.append(f"{list_field} must be a list if present")

    if errors:
        raise ValidationError(errors)


_ROLE_SET_REQUIRED = (
    "id", "type", "title", "status", "roles", "sod_predicates",
    "per_stage_markers", "library_layer", "is_default", "created_at", "author",
)
_ROLE_SET_STATUSES = {"draft", "active", "superseded", "retired"}
_ROLE_SET_AGGREGATIONS = {"all-must-pass", "merge", "pick-one"}


def validate_role_set(fm: dict) -> None:
    """Validate a role-set library entry (spec §2.3; DOC1 §6.4; companion to a
    workflow). Names roles + SoD rules, never a runtime.

    ``roles``: non-empty list of {name, owns_stage, identity_predicate?}.
    ``sod_predicates``: list (the SoD/identity constraints, §12).
    ``per_stage_markers``: mapping stage → {parallelizable: bool,
    aggregation ∈ {all-must-pass, merge, pick-one}}.
    """
    errors: list[str] = []

    for field in _ROLE_SET_REQUIRED:
        if field not in fm:
            errors.append(f"missing required field: {field}")
        elif field in ("roles", "sod_predicates", "per_stage_markers", "is_default"):
            continue
        elif fm[field] in (None, ""):
            errors.append(f"required field is empty: {field}")

    type_val = fm.get("type")
    if type_val is not None and type_val != "role-set":
        errors.append(f"type must be 'role-set', got: {type_val!r}")

    status = fm.get("status")
    if status is not None and status not in _ROLE_SET_STATUSES:
        errors.append(
            f"status must be one of {sorted(_ROLE_SET_STATUSES)}, got: {status!r}"
        )

    layer = fm.get("library_layer")
    if layer is not None and layer not in _LIBRARY_LAYERS:
        errors.append(
            f"library_layer must be one of {sorted(_LIBRARY_LAYERS)}, got: {layer!r}"
        )

    is_default = fm.get("is_default")
    if is_default is not None and not isinstance(is_default, bool):
        errors.append("is_default must be a bool")

    roles = fm.get("roles")
    if "roles" in fm:
        if not isinstance(roles, list) or not roles:
            errors.append("roles must be a non-empty list")
        else:
            for idx, role in enumerate(roles):
                if not isinstance(role, dict):
                    errors.append(f"role #{idx} must be a mapping")
                    continue
                if not role.get("name"):
                    errors.append(f"role #{idx} missing required 'name'")
                if not role.get("owns_stage"):
                    errors.append(f"role #{idx} missing required 'owns_stage'")

    sod = fm.get("sod_predicates")
    if "sod_predicates" in fm and not isinstance(sod, list):
        errors.append("sod_predicates must be a list")

    markers = fm.get("per_stage_markers")
    if "per_stage_markers" in fm:
        if not isinstance(markers, dict):
            errors.append("per_stage_markers must be a mapping")
        else:
            for stage_name, marker in markers.items():
                if not isinstance(marker, dict):
                    errors.append(f"per_stage_markers[{stage_name!r}] must be a mapping")
                    continue
                par = marker.get("parallelizable")
                if par is not None and not isinstance(par, bool):
                    errors.append(
                        f"per_stage_markers[{stage_name!r}] parallelizable must be a bool"
                    )
                agg = marker.get("aggregation")
                if agg is not None and agg not in _ROLE_SET_AGGREGATIONS:
                    errors.append(
                        f"per_stage_markers[{stage_name!r}] aggregation must be one of "
                        f"{sorted(_ROLE_SET_AGGREGATIONS)}, got: {agg!r}"
                    )

    if errors:
        raise ValidationError(errors)


_BLOCK_SIGNAL_REQUIRED = (
    "id", "type", "blocked_subject", "waits_on", "class", "status",
    "created_at", "created_by",
)
_BLOCK_SIGNAL_CLASSES = {"HALT", "wait_for"}
_BLOCK_SIGNAL_STATUSES = {"raised", "resolved", "expired"}


def validate_block_signal(fm: dict) -> None:
    """Validate a block-signal (spec §2.3; DOC1 §6.3; the runtime block).

    Two classes only (§11.5): ``HALT`` (cleared only by a human unblock; the
    only block that may wait indefinitely) and ``wait_for`` (bounded — a TTL
    is REQUIRED; indefinite forbidden). block-signal does NOT carry owner_user
    (transient runtime signal; created_by only).
    """
    errors: list[str] = []

    for field in _BLOCK_SIGNAL_REQUIRED:
        if field not in fm:
            errors.append(f"missing required field: {field}")
        elif fm[field] in (None, ""):
            errors.append(f"required field is empty: {field}")

    type_val = fm.get("type")
    if type_val is not None and type_val != "block-signal":
        errors.append(f"type must be 'block-signal', got: {type_val!r}")

    klass = fm.get("class")
    if klass is not None and klass not in _BLOCK_SIGNAL_CLASSES:
        errors.append(
            f"class must be one of {sorted(_BLOCK_SIGNAL_CLASSES)}, got: {klass!r}"
        )

    status = fm.get("status")
    if status is not None and status not in _BLOCK_SIGNAL_STATUSES:
        errors.append(
            f"status must be one of {sorted(_BLOCK_SIGNAL_STATUSES)}, got: {status!r}"
        )

    # wait_for is bounded: a TTL is required, indefinite forbidden (§11.5).
    # HALT is the only class that may wait indefinitely (ttl absent is OK).
    if klass == "wait_for" and fm.get("ttl") in (None, ""):
        errors.append("class=wait_for requires a ttl (indefinite wait forbidden, §11.5)")
    if klass == "HALT" and fm.get("ttl") not in (None, ""):
        errors.append("class=HALT must not carry a ttl (HALT may wait indefinitely, §11.5)")

    if "owner_user" in fm:
        errors.append("block-signal does not carry owner_user (created_by only)")

    if errors:
        raise ValidationError(errors)


_RESUME_LEDGER_REQUIRED = (
    "id", "type", "worker", "status", "in_flight_state", "next_actions",
    "created_at", "author",
)
_RESUME_LEDGER_STATUSES = {"written"}


def validate_resume_ledger(fm: dict) -> None:
    """Validate a resume-ledger (spec §2.3; DOC1 §7; continuity).

    The in-flight state + immediate next actions for the NEXT incarnation of
    THIS worker after a restart (distinct from handoff = settled post-state for
    the NEXT worker). Carries owner_user (read-time default).
    """
    errors: list[str] = []

    for field in _RESUME_LEDGER_REQUIRED:
        if field not in fm:
            errors.append(f"missing required field: {field}")
        elif field == "next_actions":
            continue
        elif fm[field] in (None, ""):
            errors.append(f"required field is empty: {field}")

    type_val = fm.get("type")
    if type_val is not None and type_val != "resume-ledger":
        errors.append(f"type must be 'resume-ledger', got: {type_val!r}")

    status = fm.get("status")
    if status is not None and status not in _RESUME_LEDGER_STATUSES:
        errors.append(
            f"status must be one of {sorted(_RESUME_LEDGER_STATUSES)}, got: {status!r}"
        )

    next_actions = fm.get("next_actions")
    if "next_actions" in fm and not isinstance(next_actions, list):
        errors.append("next_actions must be a list")

    if errors:
        raise ValidationError(errors)


_CANONICAL_POINTER_REQUIRED = (
    "id", "type", "names", "points_to", "updated_at", "updated_by",
)


def validate_canonical_pointer(fm: dict) -> None:
    """Validate a canonical-pointer (spec §2.3; DOC1 §7).

    One per named body-of-work; mutable head (updated in place, not
    forward-only) so a fresh incarnation never re-anchors on a stale draft.
    Carries owner_user (read-time default).
    """
    errors: list[str] = []

    for field in _CANONICAL_POINTER_REQUIRED:
        if field not in fm:
            errors.append(f"missing required field: {field}")
        elif fm[field] in (None, ""):
            errors.append(f"required field is empty: {field}")

    type_val = fm.get("type")
    if type_val is not None and type_val != "canonical-pointer":
        errors.append(f"type must be 'canonical-pointer', got: {type_val!r}")

    if errors:
        raise ValidationError(errors)


# BC2.3 — closure record (spec §11.3). NOT a §2.3/§1.3 built-in kind (the
# catalog stays at 20); it is the lifecycle sub-record written on the two
# terminal edges (done→cleaned-up and the pre-done abandon edge, §11.1). Stored
# flat at closures/<id>.md.
_CLOSURE_REQUIRED = (
    "id", "type", "task_ref", "disposition", "closure_signal_ref",
    "closed_by", "closed_at",
)
_CLOSURE_DISPOSITIONS = {"completed", "superseded", "abandoned"}


def validate_closure_record(fm: dict) -> None:
    """Validate a closure record (spec §11.3).

    ``disposition`` ∈ {completed, superseded, abandoned} — completed/superseded
    on ``done → cleaned-up``; abandoned on the pre-done abandon edge. The
    ``supersedes_ref`` field is set **iff** ``disposition == superseded`` (a
    superseding closure must name what it supersedes; a non-superseded closure
    must not carry one).
    """
    errors: list[str] = []

    for field in _CLOSURE_REQUIRED:
        if field not in fm:
            errors.append(f"missing required field: {field}")
        elif fm[field] in (None, ""):
            errors.append(f"required field is empty: {field}")

    type_val = fm.get("type")
    if type_val is not None and type_val != "closure-record":
        errors.append(f"type must be 'closure-record', got: {type_val!r}")

    disposition = fm.get("disposition")
    if disposition is not None and disposition not in _CLOSURE_DISPOSITIONS:
        errors.append(
            f"disposition must be one of {sorted(_CLOSURE_DISPOSITIONS)}, "
            f"got: {disposition!r}"
        )

    # supersedes_ref ⇔ disposition == superseded (§11.3).
    has_supersedes = fm.get("supersedes_ref") not in (None, "")
    if disposition == "superseded" and not has_supersedes:
        errors.append("disposition=superseded requires a supersedes_ref (§11.3)")
    if has_supersedes and disposition != "superseded":
        errors.append(
            "supersedes_ref is only valid when disposition=superseded (§11.3)"
        )

    if errors:
        raise ValidationError(errors)


# ---------------------------------------------------------------------------
# Sprint 7: STATUS_TRANSITIONS matrix (D44 / D47.5)
# ---------------------------------------------------------------------------
#
# Per-entity-type allowed-transitions graph. Each entry maps a SOURCE
# state to the set of states reachable from it (use the sentinel
# ``"terminal"`` literal for sink states — i.e., the state has no
# outgoing edges; current-status remains the terminal value). Used by
# ``validate._check_status_transitions``.
#
# Entity types ABSENT from this matrix are considered "no status
# transition coverage" and skipped by the check — that's the Handoff
# (status always 'written' per D6.A), Retrospective (status always
# 'completed'), and Conversation (no status field at all) per D44.A.
#
# To extend the matrix in a future sprint (e.g., when status_history
# lands), add the new state as a key with its allowed-next-states set;
# the data shape stays the same.

STATUS_TRANSITIONS: dict[str, dict[str, set[str]]] = {
    "sprint-plan": {
        # Sprint plan: status='active' from creation; transitions to
        # 'superseded' when a new version replaces it. 'draft' is a
        # pre-active state the writers don't currently use but the §6
        # schema permits.
        # workshop-lite cohort (A) substrate-hygiene (charter §2 D5 +
        # chunk-0 PG-4 discipline-applied): added `closed` reachable
        # from active. /end-sprint writes status: closed + closed_at
        # on archive-move (closes wsl-plan checkpoint #2 §④ — the
        # 18-archived-sprints-stuck-at-active surface). Disk-folder
        # archive-move is the "shipping" signal that pairs with the
        # status flip; together they remove the prior ambiguity where
        # the retrospective marked completion but the plan still read
        # active.
        "draft":      {"active"},
        "active":     {"superseded", "closed"},
        "superseded": {"terminal"},
        "closed":     {"terminal"},
    },
    "decision": {
        # Decision: 'accepted' is the most common creation status
        # (record_decision default); rare 'open' for in-progress
        # proposals. Supersession marks a decision as terminal in
        # the graph but the slug remains as the durable record.
        "open":       {"accepted", "rejected", "superseded", "open"},
        "accepted":   {"superseded", "open"},
        "rejected":   {"terminal"},
        "superseded": {"terminal"},
    },
    "review": {
        # Review: writer defaults to 'completed'. 'in_progress' is
        # a less-common path for mid-review captures.
        "in_progress": {"completed"},
        "completed":   {"terminal"},
        # Persona-mediated path (workshop-lite-consult-skill-platform
        # charter §2.1 + chunk-0 PG-1(a) ratify + PG-2 auto-resolved):
        # /consult writes status='landed' on initial write; supersede
        # transition stamps status='superseded' on the OLD review when
        # a NEW persona-Review is written for the same target.
        # Mirrors the dispatch supersede pattern (HR-#7).
        "landed":      {"superseded", "terminal"},
        "superseded":  {"terminal"},
    },
    "issue": {
        # Issue: 'open' on creation; re-open from any state is
        # allowed (the bug came back). 'wontfix' and 'resolved'
        # are not strictly terminal — D44.A permits re-open.
        # workshop-lite cohort (A) substrate-hygiene (charter §2 D1
        # + chunk-0 PG-3 discipline-applied): added `deferred` and
        # `superseded`. `deferred` is the (β) deferred-registry
        # lifecycle anchor; reachable from open/investigating, and
        # exits to open (un-defer / revisit-trigger fires) or
        # resolved/wontfix/superseded (disposition reached without
        # re-opening). `superseded` mirrors the Decision/Review
        # pattern (issue replaced by a newer issue carrying the
        # canonical surface); reachable from any non-superseded
        # state, terminal in the graph.
        "open":          {"investigating", "wontfix", "resolved",
                          "deferred", "superseded"},
        "investigating": {"resolved", "wontfix", "open",
                          "deferred", "superseded"},
        "resolved":      {"terminal", "open", "superseded"},
        "wontfix":       {"terminal", "open", "superseded"},
        "deferred":      {"open", "investigating", "resolved",
                          "wontfix", "superseded", "terminal"},
        "superseded":    {"terminal"},
    },
    "wip-claim": {
        # WIP-claim (sub-spec §4): 'claimed' → released | committed |
        # abandoned. 'released' + 'committed' are terminal; 'abandoned'
        # is a degraded form (validator-detected, not seat-written) but
        # also terminal from a state-graph perspective.
        "claimed":    {"released", "committed", "abandoned"},
        "released":   {"terminal"},
        "committed":  {"terminal"},
        "abandoned":  {"terminal"},
    },
    "standing-dispatch": {
        # Standing-dispatch (sub-spec §4): 'standing' →
        # satisfied | superseded | expired. All three are terminal.
        # Transitions are author-driven (the validator surfaces
        # candidates via V2 / V4 / V5 INFO advisories — never mutates;
        # Hard Rule 5 / D33).
        "standing":   {"satisfied", "superseded", "expired"},
        "satisfied":  {"terminal"},
        "superseded": {"terminal"},
        "expired":    {"terminal"},
    },
    "prd": {
        # PRD (charter §2.1 + chunk-0 PG-4 ratify): forward-only linear
        # chain. Each non-terminal state transitions to exactly ONE
        # next state via a dedicated CLI verb (record-prd-ratify /
        # convert / technical-plan-ready / ship). 'shipped' is the
        # terminal state. No back-transitions; bidirectional supersede
        # deferred to v2 iff real PM workflow surfaces the need.
        "draft":                {"ratified"},
        "ratified":             {"converting"},
        "converting":           {"technical_plan_ready"},
        "technical_plan_ready": {"shipped"},
        "shipped":              {"terminal"},
    },
    "gate": {
        # Gate (workshop-lite cohort (B) install-rollout D1 / source
        # issue 2026-06-04-01): open → {closed, resolved}. 'open' is
        # the live-hold state — the gated_by source is in-flight or
        # the operator hold is active. 'closed' is operator-acknowledged
        # finalization (the gater explicitly closed the gate;
        # what_you_cannot_do no longer applies). 'resolved' is the
        # in-flight-condition-cleared finalization (the gate expired
        # naturally; e.g., the release freeze ended). Both terminal.
        # Re-open from a terminal state is intentionally NOT modeled
        # in v1 — author a NEW gate file with a fresh gate_id if the
        # condition recurs. Matches the PRD/wip-claim/standing-dispatch
        # forward-only discipline.
        "open":     {"closed", "resolved"},
        "closed":   {"terminal"},
        "resolved": {"terminal"},
    },
    # BC1.5 — task R6 six-state lifecycle (spec §2.3 / §11). Linear forward
    # with a verified→in-progress rework back-edge. `blocked` is intentionally
    # absent (not an R6 status; a block-signal overlay sits atop, §9).
    "task": {
        "created":     {"picked-up"},
        "picked-up":   {"in-progress"},
        "in-progress": {"verified"},
        "verified":    {"done", "in-progress"},
        "done":        {"cleaned-up"},
        "cleaned-up":  {"terminal"},
    },
    # BC1.2 — the 4 stateful new kinds (spec §2.3). canonical-pointer is
    # absent (mutable-head; no status field).
    "workflow": {
        "draft":      {"active"},
        "active":     {"superseded", "retired"},
        "superseded": {"terminal"},
        "retired":    {"terminal"},
    },
    "role-set": {
        "draft":      {"active"},
        "active":     {"superseded", "retired"},
        "superseded": {"terminal"},
        "retired":    {"terminal"},
    },
    "block-signal": {
        # §11.5: raised → resolved (release / human unblock) | expired
        # (wait_for TTL elapsed). Both terminal.
        "raised":   {"resolved", "expired"},
        "resolved": {"terminal"},
        "expired":  {"terminal"},
    },
    "resume-ledger": {
        # Continuity record; status invariant at 'written' (superseded by a
        # newer ledger via the supersedes back-ref, not a status flip).
        "written":  {"terminal"},
    },
    # Conversation / Handoff / Retrospective / Halt: intentionally absent.
    # No status field OR status is invariant. _check_status_transitions
    # treats absence as "skip the check entirely for this type".
    # Halt specifically (D1 / source issue 2026-06-04-01): the file's
    # existence IS the halt state; deletion is the resolve signal;
    # ttl_until exceeded is detected by the parley-side halt_detection_loop
    # (workshop-lite:2026-06-04-02 / D2), not by the validator.
}


def known_statuses_for(entity_kind: str) -> set[str] | None:
    """Return the set of known statuses (states) for an entity kind.

    The set is the UNION of source-states (keys) and target-states
    (values, less the 'terminal' sentinel) in the transition graph.

    Returns ``None`` (sentinel: type not covered) when the kind has
    no transition entry — Conversation, Handoff, Retrospective.
    Callers should treat None as "skip the status check for this
    entity"; this is distinct from an empty set which would imply
    "no valid states".
    """
    matrix = STATUS_TRANSITIONS.get(entity_kind)
    if matrix is None:
        return None
    states: set[str] = set(matrix.keys())
    for nexts in matrix.values():
        states.update(nexts)
    states.discard("terminal")
    return states
