"""Workshop-Lite Layer-C prompt-pack payload emitter (issue 2026-06-10-02).

WL's half of the Layer-C render seam per design
``docs/design/2026-06-10-wl-layer-c-prompt-pack-render-seam.md`` §3-§5 and
the Layer-B registration ``prompt_pack`` (§4.4, EnforcementRegistration v1).

This module *authors* the adapter-neutral pack payload as data — the
``workshop_lite.pack_payload_emitter`` mechanism named in the Layer-B
registration. It does **not** write any instructions file: per HR-1
(parley-agnostic / adapter-host-agnostic at base) WL never writes another
agent's ``CLAUDE.md`` / ``AGENTS.md``. The render seam (par-plan surface)
consumes this payload and performs the managed-block file write. WL emits
a payload whether or not a render seam exists to consume it — the payload
is inert data when nothing renders it (Layer-C §9 absence-safety).

The render seam shells out to this via the ``wl emit-pack-payload`` CLI
verb (mirrors how the codex-host SessionStart hook shells out to
``wl state-digest``) — an HR-1-clean consumption surface: the seam shells
*to* ``wl``; ``wl`` never shells *to* parley.

MARKER CONVENTION (resolved 2026-06-10, @plan msg-e44efe2ed7af → predecessor
ack msg-2c50f7973e32; par's PUBLISHED PackPayload contract @ 340c39a confirms
marker is render-seam-owned, not contract-owned, so WL owns the name):
``<!-- BEGIN workshop-lite-pack --> / <!-- END workshop-lite-pack -->``.
Suffix-disambiguated from the STATIC install fragment marker
``<!-- workshop-lite-start --> / <!-- workshop-lite-end -->`` (shipped by
``workshop_lite_content.py`` / ``codex_host_content.py``, WL.29/30) — both
match the HR-3 ``workshop-lite-*`` prefix scan, cleanly separating the
dynamic spawn-pack from the static install fragment. The render seam may
override the per-render block name (par's contract leaves it
render-seam-owned); ``MANAGED_BLOCK`` is the WL default so a standalone
``wl emit-pack-payload`` is self-describing.
"""
from __future__ import annotations

from typing import Any

import yaml

# Schema version of the pack payload contract (Layer-C §4). Bump on any
# breaking change to the section shape.
PACK_VERSION = 1

# Layer-C managed-block marker name. See MARKER CONVENTION in the module
# docstring for the suffix-disambiguation rationale and cross-links. The
# render seam may override per render target.
MANAGED_BLOCK = "workshop-lite-pack"

# Adapters the same payload renders to (only the skill-ref path + any
# adapter-specific phrasing differ; the render seam owns that substitution).
SUPPORTED_ADAPTERS = ("claude_code", "codex")


# ---------------------------------------------------------------------------
# §5 — Layer-B prompt-only degradation reminders (honest, advisory).
#
# Each known intent that registered native_mechanism:null (tool_policy,
# edit_policy) or a partial write_scope remainder degrades to a Layer-C
# honest reminder. The reminder NAMES where real enforcement lives so the
# seat (or its operator) knows Layer C is the backstop, not the mechanism.
# ---------------------------------------------------------------------------

_CONSTRAINT_REMINDERS: dict[str, str] = {
    "write_scope_remainder": (
        "Entity writes go through the entity-writer skills (/record-decision, "
        "/record-issue, /handoff, ...), which bind the write path from the "
        "entity-id template. Do not hand-write files under docs/<type>/ — the "
        "skill computes the id + frontmatter. Arbitrary Write/Edit outside the "
        "skills is not enforced by workshop-lite; the host adapter's write "
        "policy (CC settings deny-rules / PreToolUse hooks; codex --sandbox) is "
        "the real boundary. This reminder is advisory."
    ),
    "tool_policy": (
        "This seat's declared tool policy is surfaced here as a reminder only. "
        "Tool-call enforcement is the host adapter's surface — settings.json "
        "allowlist + PreToolUse hooks for Claude Code; --sandbox + "
        "approval-policy for codex. workshop-lite has no native tool-policy "
        "mechanism; this reminder is the honest backstop, not a gate."
    ),
    "edit_policy": (
        "Edit constraints (existing-file vs new-file, atomic multi-edit) are "
        "surfaced as a reminder. workshop-lite does not intercept Edit calls; "
        "enforcement lives in the host adapter (CC PreToolUse hooks on the Edit "
        "matcher; codex --sandbox workspace-write). Advisory only."
    ),
}


def build_constraint_section(intents: list[str]) -> list[dict[str, str]]:
    """Build the ``constraints`` section for the given prompt-only intents.

    Each entry is ``{"intent": <id>, "text": <honest reminder prose>}``.
    Unknown intents are skipped (the emitter only renders reminders it has
    canonical honest text for — it never invents enforcement prose).
    Order follows the input ``intents`` (caller-controlled, deterministic).
    """
    out: list[dict[str, str]] = []
    for intent in intents:
        text = _CONSTRAINT_REMINDERS.get(intent)
        if text is not None:
            out.append({"intent": intent, "text": text})
    return out


# Default prompt-only intents the WL Layer-B registration degrades to Layer C
# (§4.1 write_scope remainder, §4.2 tool_policy, §4.3 edit_policy).
DEFAULT_CONSTRAINT_INTENTS: tuple[str, ...] = (
    "write_scope_remainder",
    "tool_policy",
    "edit_policy",
)


# ---------------------------------------------------------------------------
# §6 — rec #10 evidence_obligation (WL-side fold; advisory render half).
# ---------------------------------------------------------------------------

# WL entity provenance fields a claim-class entity should populate. These
# already exist in the entity frontmatter schema (HR-2 unchanged).
EVIDENCE_PROVENANCE_FIELDS = ("linked_msg_ids", "linked_decisions")

_EVIDENCE_RENDER_TEXT = (
    "Verdicts and decisions you file should populate their provenance fields "
    "(linked_msg_ids / linked_decisions / evidence refs). Authority follows "
    "provenance, not tier — a claim's weight is a function of its evidence. "
    "The advisory validator (wl validate) flags claim-class entities with "
    "empty provenance; this is a reminder, not a gate."
)


def build_evidence_obligation_section() -> dict[str, Any]:
    """Build the ``evidence_obligation`` section (rec #10 WL-side fold)."""
    return {
        "required_provenance_fields": list(EVIDENCE_PROVENANCE_FIELDS),
        "render_text": _EVIDENCE_RENDER_TEXT,
    }


# ---------------------------------------------------------------------------
# §7 — rec #14 memory_scope (WL-side fold; curate-policy render half).
#
# Scoped to WL's OWN durable entity corpus (docs/{decisions,reviews,...} +
# preferences), NOT the host harness auto-memory (verify-before-assert §7).
# ---------------------------------------------------------------------------

_MEMORY_CURATE_POLICY = (
    "curate, not append-only accrete: handoffs supersede rather than stack "
    "(handoff_aging.py supersession chain); the per-folder INDEX is the "
    "curated view, not the raw file list."
)

_MEMORY_RENDER_TEXT = (
    "workshop-lite's durable corpus (docs/{decisions,reviews,issues,handoffs,"
    "conversations} + .claude/preferences.toml) is curated, not append-only. "
    "Fold superseded handoffs, keep INDEX coherent, prune orphaned "
    "cross-links. The validator flags un-curated accretion in audit mode. "
    "This curates WL's own entity corpus only — not the host adapter's "
    "auto-memory."
)


def build_memory_scope_section() -> dict[str, Any]:
    """Build the ``memory_scope`` section (rec #14 WL-side fold)."""
    return {
        "curate_policy": _MEMORY_CURATE_POLICY,
        "render_text": _MEMORY_RENDER_TEXT,
    }


# ---------------------------------------------------------------------------
# §8 — rec #19 persona-dimensions (WL-side fold; render half).
# ---------------------------------------------------------------------------

# The three explicit persona dimensions the rec asks for. ``mode`` collapses
# into conflict + reasoning (kept as a back-compat alias at the persona
# frontmatter layer; not rendered here).
PERSONA_DIMENSIONS = ("reasoning", "register", "conflict")


def build_persona_section(dimensions: dict[str, str]) -> dict[str, Any]:
    """Build the ``persona`` section from explicit dimension values.

    ``dimensions`` is a mapping over a subset of ``PERSONA_DIMENSIONS``
    (e.g. ``{"reasoning": "empirical", "register": "terse",
    "conflict": "adversarial"}``). Unknown keys are dropped; the section
    renders only the recognized dimensions so a partial persona is honest
    about which dims it declares.
    """
    dims = {
        k: dimensions[k]
        for k in PERSONA_DIMENSIONS
        if k in dimensions and dimensions[k] is not None
    }
    rendered = ", ".join(f"{k}={v}" for k, v in dims.items())
    return {
        "dimensions": dims,
        "render_text": (
            f"This persona's declared dimensions: {rendered}. Hold this "
            f"voice/stance consistently across the spawn."
        ),
    }


# ---------------------------------------------------------------------------
# Payload composition.
# ---------------------------------------------------------------------------


def build_pack_payload(
    *,
    adapter: str | None = None,
    constraint_intents: list[str] | None = None,
    include_evidence_obligation: bool = True,
    include_memory_scope: bool = True,
    persona_dimensions: dict[str, str] | None = None,
    managed_block: str = MANAGED_BLOCK,
) -> dict[str, Any]:
    """Compose the adapter-neutral Layer-C pack payload (Layer-C §4).

    Absence-safe: a section is included only when it has content. An empty
    ``sections`` is legal (yields an inert pack the render seam can no-op).

    ``adapter`` is ``None`` by default — the render seam sets it per render
    target. When provided it must be one of ``SUPPORTED_ADAPTERS``.

    ``constraint_intents`` defaults to ``DEFAULT_CONSTRAINT_INTENTS`` (the WL
    Layer-B prompt-only degradations). Pass ``[]`` to omit the constraints
    section.

    The payload is deterministic: identical inputs yield an identical dict,
    so re-render is idempotent (Layer-C §9).
    """
    if adapter is not None and adapter not in SUPPORTED_ADAPTERS:
        raise ValueError(
            f"unknown adapter {adapter!r}; "
            f"expected one of {SUPPORTED_ADAPTERS}"
        )

    intents = (
        list(DEFAULT_CONSTRAINT_INTENTS)
        if constraint_intents is None
        else constraint_intents
    )

    sections: dict[str, Any] = {}

    constraints = build_constraint_section(intents)
    if constraints:
        sections["constraints"] = constraints

    if include_evidence_obligation:
        sections["evidence_obligation"] = build_evidence_obligation_section()

    if include_memory_scope:
        sections["memory_scope"] = build_memory_scope_section()

    if persona_dimensions:
        persona = build_persona_section(persona_dimensions)
        if persona["dimensions"]:
            sections["persona"] = persona

    return {
        "pack_version": PACK_VERSION,
        "adapter": adapter,
        "managed_block": managed_block,
        "sections": sections,
    }


def to_yaml(payload: dict[str, Any]) -> str:
    """Serialize a pack payload to adapter-neutral YAML (stable key order).

    ``sort_keys=False`` preserves the composed section order; the render
    seam consumes this on stdout.
    """
    return yaml.safe_dump(
        payload,
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
    )
