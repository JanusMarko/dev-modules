"""Sprint structured-charter (``spec.yaml``) library + validator gates.

Phase 3 of the workshop-lite re-architecture arc. Per sub-spec
``docs/design/2026-05-29-wl-sprint-spec-yaml.md`` (binding):

- New optional file: ``docs/sprints/active/sprint-<id>/spec.yaml`` declaring
  a sprint's binding doctrines, required artifacts, and parent charter(s).
- Validator V1-V8 gates surface drift between declared spec.yaml + the
  artifacts on disk. Most checks are advisory (WARN/INFO); two are ERROR
  and contribute to ``--strict`` exit; the ``/end-sprint`` skill calls
  ``--strict --sprint <id>`` to abort sprint-close when a kris-binding
  sprint has missing required artifacts.

Hard Rule 1 (parley-agnostic at base): this module NEVER imports parley
or shells out to it. ``parley://charters/<id>`` URI strings are accepted
as opaque durable references and resolution is delegated to the skill
layer; the library treats unresolved parley URIs as INFO-log (silent
skip) per Hard Rule 5.

Hard Rule 5 (validator advisory by default): only V1, V5, V6 contribute
to ``--strict`` exit; all other gates are advisory. The ``/end-sprint``
strict gate is OPT-IN (spec.yaml present + ``sprint_kind=kris-binding``).

Hard Rule 7 (NOT a judgment surface): every gate is a binary structural
check — file-exists / frontmatter-parses / enum-member / list-shape. No
graded similarity, no behavioral scoring.

Closes charter §4 failure #3 (sprint dead-code in autonomous-arc) +
failure #7 (doctrine-adherence discretion as failure surface). Resolves
master design Q-WL-12, Q-WL-13, Q-WL-14 (see §3.1 / §5 / §6).
"""
from __future__ import annotations

from collections import namedtuple
from pathlib import Path
from typing import Any

import yaml
import ledger_paths

# Per-rule severity per sub-spec §4.1.
SEVERITY_ERROR = "ERROR"
SEVERITY_WARN = "WARN"
SEVERITY_INFO = "INFO"

# WarningRecord shape mirrors ``validate.WarningRecord`` (4-tuple with
# default-None ``suppressed_by``). Defined locally to avoid an import
# cycle with ``validate.py``; the caller (``validate._check_sprint_specs``)
# rebuilds these as the canonical validate.WarningRecord on collection.
WarningRecord = namedtuple(
    "WarningRecord",
    ("category", "path", "message", "suppressed_by"),
    defaults=(None,),
)

# Initial built-in sprint_kind enum (sub-spec §3.1). Per-repo extensions
# live in workshop-lite-config.toml ``[sprints.kinds]`` and merge with
# this set; see ``_registered_kinds``.
BUILTIN_SPRINT_KINDS: dict[str, dict] = {
    # name -> {gate_at_end: bool, required_artifact_keys: list[str]}
    "kris-binding": {
        "gate_at_end": True,
        "required_artifact_keys": [
            "adversarial_crosscheck",
            "dogfood_step",
            "eval_corpus",
            "golden_path_verifier",
            "ship_epic_3step",
        ],
    },
    "autonomous-arc": {
        "gate_at_end": False,
        "required_artifact_keys": [],
    },
    "routine": {
        "gate_at_end": False,
        "required_artifact_keys": [],
    },
}

# Standard artifact-key shape registry (sub-spec §3.2). Each key declares
# which typed reference it expects so the validator picks the right
# resolver.
ARTIFACT_REF_KINDS: dict[str, str] = {
    "adversarial_crosscheck": "path",
    "dogfood_step": "path",
    "eval_corpus": "path",
    "golden_path_verifier": "path",
    "ship_epic_3step": "parley_msg_id",
}

# Required top-level spec.yaml fields per sub-spec §3.
_REQUIRED_FIELDS = (
    "schema_version",
    "sprint_id",
    "sprint_kind",
    "required_artifacts",
    "binding_doctrines",
    "charter_ref",
    "created_at",
    "created_by",
    "owner_user",
    "has_user_journey",
)

# Parley URI scheme accepted as opaque per D-WL-20 element 2 (sub-spec §7.1).
_PARLEY_CHARTER_URI_PREFIX = "parley://charters/"


# ---------- config loading ----------


def _registered_kinds(repo_root: Path) -> dict[str, dict]:
    """Merge built-in ``sprint_kind`` enum with per-repo extensions.

    Per sub-spec §3.1: ``.claude/workshop-lite-config.toml`` may declare
    ``[sprints.kinds]`` entries that add to the enum. Schema:

        [sprints.kinds]
        "contract-gated" = { gate_at_end = true, required_artifact_keys = [...] }

    Robustness (Hard Rule 5): malformed config => silent fallback to
    built-ins only; never raises.
    """
    out = {k: dict(v) for k, v in BUILTIN_SPRINT_KINDS.items()}
    try:
        import index as _index_mod
        cfg = _index_mod._load_workshop_lite_config(repo_root)
    except Exception:
        return out
    if not isinstance(cfg, dict):
        return out
    sprints_section = cfg.get("sprints")
    if not isinstance(sprints_section, dict):
        return out
    kinds = sprints_section.get("kinds")
    if not isinstance(kinds, dict):
        return out
    for name, value in kinds.items():
        if not isinstance(name, str) or not name:
            continue
        if not isinstance(value, dict):
            continue
        gate_at_end = bool(value.get("gate_at_end", False))
        keys = value.get("required_artifact_keys")
        if not isinstance(keys, list):
            keys = []
        keys = [k for k in keys if isinstance(k, str) and k]
        out[name] = {
            "gate_at_end": gate_at_end,
            "required_artifact_keys": keys,
        }
    return out


# ---------- spec.yaml load + parse ----------


def load_spec_yaml(path: Path) -> tuple[dict | None, list[str]]:
    """Load + parse a sprint ``spec.yaml`` from disk.

    Returns ``(spec_dict, parse_errors)``. On any I/O failure or YAML
    parse error, returns ``(None, [<error-msg>])``. Caller decides how
    to surface (V1 emits SCHEMA error from the parse-error list).
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return None, [f"read failed: {exc}"]
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        return None, [f"YAML parse failed: {exc}"]
    if data is None:
        return None, ["spec.yaml is empty"]
    if not isinstance(data, dict):
        return None, [
            f"spec.yaml top-level must be a mapping, got: {type(data).__name__}"
        ]
    return data, []


# ---------- V1: schema validation ----------


def _validate_schema(
    spec: dict, repo_root: Path,
) -> list[str]:
    """Return a list of V1 schema-error messages (empty == OK).

    Binary structural checks: required-fields present + non-null,
    schema_version=1, sprint_id is non-empty string, sprint_kind is
    string, required_artifacts is mapping, binding_doctrines is list,
    charter_ref is list, has_user_journey is bool.
    """
    errors: list[str] = []
    for field in _REQUIRED_FIELDS:
        if field not in spec:
            errors.append(f"missing required field: {field}")
            continue
        val = spec[field]
        # has_user_journey is bool; False is a valid value, don't reject.
        if field == "has_user_journey":
            if not isinstance(val, bool):
                errors.append(
                    f"has_user_journey must be bool, got: {type(val).__name__}"
                )
            continue
        if val is None or val == "":
            errors.append(f"required field is empty: {field}")
            continue
    sv = spec.get("schema_version")
    if sv is not None and sv != 1:
        errors.append(f"schema_version must be 1, got: {sv!r}")
    if "sprint_id" in spec:
        sid = spec.get("sprint_id")
        if sid is not None and not isinstance(sid, str):
            errors.append(
                f"sprint_id must be string, got: {type(sid).__name__}"
            )
    if "sprint_kind" in spec:
        kind = spec.get("sprint_kind")
        if kind is not None and not isinstance(kind, str):
            errors.append(
                f"sprint_kind must be string, got: {type(kind).__name__}"
            )
    if "required_artifacts" in spec:
        ra = spec.get("required_artifacts")
        if ra is not None and not isinstance(ra, dict):
            errors.append(
                f"required_artifacts must be a mapping, got: {type(ra).__name__}"
            )
        elif isinstance(ra, dict):
            for key, entry in ra.items():
                if not isinstance(entry, dict):
                    errors.append(
                        f"required_artifacts[{key!r}] must be a mapping"
                    )
                    continue
                if "required" in entry and not isinstance(
                    entry["required"], bool
                ):
                    errors.append(
                        f"required_artifacts[{key!r}].required must be bool"
                    )
    if "binding_doctrines" in spec:
        bd = spec.get("binding_doctrines")
        if bd is not None and not isinstance(bd, list):
            errors.append(
                f"binding_doctrines must be a list, got: {type(bd).__name__}"
            )
    if "charter_ref" in spec:
        cr = spec.get("charter_ref")
        # Per §6 (Q-WL-14): list, not scalar.
        if cr is not None and not isinstance(cr, list):
            errors.append(
                f"charter_ref must be a list (per §6 Q-WL-14), got: "
                f"{type(cr).__name__}"
            )
    return errors


# ---------- artifact resolution ----------


def _artifact_resolved(
    entry: dict, repo_root: Path, key: str,
) -> tuple[bool, str | None]:
    """Return ``(resolved, why_not)`` for one ``required_artifacts`` entry.

    Resolution rules per sub-spec §3.2:

    - ``path``-keyed artifact: ``required: true`` AND ``path`` is non-null
      AND the resolved repo-relative path exists on disk.
    - ``parley_msg_id``-keyed artifact: ``required: true`` AND
      ``parley_msg_id`` is non-null AND non-empty string. (No parley
      shell-out at library layer per Hard Rule 1; presence of a non-empty
      msg-id string is treated as resolved. The skill layer is responsible
      for ``parley`` confirmation if that's desired.)
    """
    ref_kind = ARTIFACT_REF_KINDS.get(key, "path")
    if ref_kind == "path":
        path_val = entry.get("path")
        if path_val is None or path_val == "":
            return False, "path is null/empty"
        if not isinstance(path_val, str):
            return False, f"path must be string, got: {type(path_val).__name__}"
        resolved = (repo_root / path_val).exists()
        if not resolved:
            return False, f"path does not exist: {path_val}"
        return True, None
    if ref_kind == "parley_msg_id":
        mid = entry.get("parley_msg_id")
        if mid is None or mid == "":
            return False, "parley_msg_id is null/empty"
        if not isinstance(mid, str):
            return False, (
                f"parley_msg_id must be string, got: {type(mid).__name__}"
            )
        return True, None
    # Unknown ref-kind: treat as path with INFO-tinted skip; the V1 schema
    # check should have flagged this earlier, so default behavior is
    # permissive.
    return True, None


def _effective_required(
    entry: dict, key: str, has_user_journey: bool,
) -> bool:
    """Per sub-spec §3.3: ``has_user_journey: true`` auto-upgrades
    ``golden_path_verifier`` to ``required: true`` regardless of the
    declared value. All other keys use the declared ``required`` field.
    """
    declared = bool(entry.get("required", False))
    if key == "golden_path_verifier" and has_user_journey:
        return True
    return declared


# ---------- main check entrypoint ----------


def _find_active_sprint_specs(repo_root: Path) -> list[Path]:
    """Return paths of every ``spec.yaml`` under
    ``docs/sprints/active/sprint-*/``. Empty if none.
    """
    out: list[Path] = []
    base = ledger_paths.compat_sprints_dir(repo_root) / "active"
    if not base.is_dir():
        return out
    for sub in sorted(base.iterdir()):
        if not sub.is_dir() or not sub.name.startswith("sprint-"):
            continue
        spec = sub / "spec.yaml"
        if spec.is_file():
            out.append(spec)
    return out


def _doctrine_resolves(repo_root: Path, doctrine: str) -> bool:
    """Return True iff a doctrine slug/path resolves to an on-disk file.

    Per Q-SSY-2 implementation hint (deferred resolver index): for now,
    we accept either:

    - A repo-relative path ending in ``.md`` that exists.
    - A slug ``<name>`` that resolves to either
      ``docs/design/<NAME>-DOCTRINE.md`` (upper-case slug) or
      ``docs/design/<name>-doctrine.md`` (lower-case) on disk.

    Anything else INFO-logs (V4). No judgment surface (Hard Rule 7) —
    binary file-existence compare.
    """
    if not isinstance(doctrine, str) or not doctrine:
        return False
    if doctrine.endswith(".md"):
        return (repo_root / doctrine).exists()
    candidates = [
        repo_root / "docs" / "design" / f"{doctrine.upper()}-DOCTRINE.md",
        repo_root / "docs" / "design" / f"{doctrine.lower()}-doctrine.md",
        repo_root / "docs" / "design" / f"{doctrine}.md",
    ]
    return any(c.exists() for c in candidates)


def _charter_resolves(
    repo_root: Path, charter_ref: str,
) -> tuple[bool, str]:
    """Return (resolved, resolution_kind) for a single charter_ref entry.

    Resolution kinds: ``"local"`` | ``"parley_opaque"`` | ``"unresolved"``.

    Per D-WL-20 element 2: ``parley://charters/<id>`` is accepted as an
    opaque durable URI. The library does NOT shell out to parley; treats
    the URI as opaquely resolved (any non-empty id after the prefix
    counts). Skill-layer is responsible for full resolution per §7.1.
    """
    if not isinstance(charter_ref, str) or not charter_ref:
        return False, "unresolved"
    if charter_ref.startswith(_PARLEY_CHARTER_URI_PREFIX):
        rest = charter_ref[len(_PARLEY_CHARTER_URI_PREFIX):].strip()
        if rest:
            return True, "parley_opaque"
        return False, "unresolved"
    # Local markdown.
    if (repo_root / charter_ref).exists():
        return True, "local"
    return False, "unresolved"


def run_sprint_spec_checks(
    repo_root: str | Path,
    *,
    end_sprint_id: str | None = None,
) -> list[WarningRecord]:
    """Run V1-V8 spec.yaml validators against all active sprints.

    Returns a list of ``WarningRecord`` objects. The library layer never
    decides exit-code semantics; that's the caller's job. The severities
    are encoded into the ``category`` prefix per sub-spec §4.1.

    When ``end_sprint_id`` is set, that sprint's missing-required-artifact
    V3 warnings are upgraded to ERROR (the /end-sprint strict gate, per
    §4.2).
    """
    repo = Path(repo_root)
    warnings: list[WarningRecord] = []

    kinds = _registered_kinds(repo)

    for spec_path in _find_active_sprint_specs(repo):
        sprint_folder = spec_path.parent
        sprint_id = sprint_folder.name[len("sprint-"):]
        end_sprint_match = (
            end_sprint_id is not None and end_sprint_id == sprint_id
        )

        spec, parse_errors = load_spec_yaml(spec_path)
        # V1 — schema (ERROR; strict-exit YES).
        if spec is None:
            for msg in parse_errors:
                warnings.append(WarningRecord(
                    category="spec-yaml-schema",
                    path=str(spec_path),
                    message=msg,
                ))
            continue
        schema_errors = _validate_schema(spec, repo)
        for msg in schema_errors:
            warnings.append(WarningRecord(
                category="spec-yaml-schema",
                path=str(spec_path),
                message=msg,
            ))
        # If schema is busted enough that key fields are missing, skip
        # downstream checks for this spec.
        if "sprint_kind" not in spec or "required_artifacts" not in spec:
            continue

        # V2 — unknown sprint_kind (INFO).
        sprint_kind = spec.get("sprint_kind")
        if isinstance(sprint_kind, str) and sprint_kind not in kinds:
            warnings.append(WarningRecord(
                category="spec-yaml-unknown-kind",
                path=str(spec_path),
                message=(
                    f"sprint_kind {sprint_kind!r} not in registered enum "
                    f"({sorted(kinds.keys())}); treating as 'routine'"
                ),
            ))

        # has_user_journey for V3 + V5 auto-upgrade.
        has_user_journey = bool(spec.get("has_user_journey", False))

        # V3 — required-artifact-missing (WARN during; ERROR at /end-sprint).
        ra = spec.get("required_artifacts") or {}
        if isinstance(ra, dict):
            for key, entry in sorted(ra.items()):
                if not isinstance(entry, dict):
                    continue
                effective_required = _effective_required(
                    entry, key, has_user_journey,
                )
                if not effective_required:
                    continue
                resolved, why = _artifact_resolved(entry, repo, key)
                if resolved:
                    continue
                category = (
                    "spec-yaml-required-missing-error"
                    if end_sprint_match
                    else "spec-yaml-required-missing"
                )
                warnings.append(WarningRecord(
                    category=category,
                    path=str(spec_path),
                    message=(
                        f"required_artifacts[{key!r}] not resolved: {why}"
                    ),
                ))

        # V4 — binding-doctrine-unknown (INFO).
        bd = spec.get("binding_doctrines") or []
        if isinstance(bd, list):
            for doctrine in bd:
                if _doctrine_resolves(repo, doctrine):
                    continue
                warnings.append(WarningRecord(
                    category="spec-yaml-binding-doctrine-unknown",
                    path=str(spec_path),
                    message=(
                        f"binding_doctrines entry {doctrine!r} did not "
                        f"resolve to a doctrine file"
                    ),
                ))

        # V5 — golden-path required when has_user_journey (WARN; strict YES).
        if has_user_journey and isinstance(ra, dict):
            gpv = ra.get("golden_path_verifier")
            if isinstance(gpv, dict):
                declared = bool(gpv.get("required", False))
                if not declared:
                    warnings.append(WarningRecord(
                        category="spec-yaml-golden-path-required",
                        path=str(spec_path),
                        message=(
                            "has_user_journey: true requires "
                            "golden_path_verifier.required: true "
                            "(doctrine violation)"
                        ),
                    ))

        # V6 — ship-epic-missing (ERROR) — only at /end-sprint match.
        if end_sprint_match and isinstance(ra, dict):
            ship = ra.get("ship_epic_3step")
            if isinstance(ship, dict):
                # Only gate if it's effectively required (built-in registry
                # for kris-binding lists this artifact key; other kinds
                # may not).
                effective_required = _effective_required(
                    ship, "ship_epic_3step", has_user_journey,
                )
                if effective_required:
                    resolved, why = _artifact_resolved(
                        ship, repo, "ship_epic_3step",
                    )
                    if not resolved:
                        warnings.append(WarningRecord(
                            category="spec-yaml-ship-epic-missing",
                            path=str(spec_path),
                            message=(
                                "ship_epic_3step.parley_msg_id missing at "
                                f"/end-sprint: {why}"
                            ),
                        ))

        # V7 — charter-orphan (WARN).
        cr = spec.get("charter_ref") or []
        if isinstance(cr, list):
            for charter_ref in cr:
                if not isinstance(charter_ref, str) or not charter_ref:
                    continue
                resolved, kind_label = _charter_resolves(repo, charter_ref)
                if not resolved:
                    warnings.append(WarningRecord(
                        category="spec-yaml-charter-orphan",
                        path=str(spec_path),
                        message=(
                            f"charter_ref {charter_ref!r} did not resolve "
                            f"({kind_label})"
                        ),
                    ))

        # V8 — abandoned-charter (INFO). Heuristic per §6: a local
        # markdown charter referenced by a sprint that is ARCHIVED but
        # the charter file's frontmatter ``status`` is ``standing``.
        # At active-sprint scan we INFO-log if the charter status is
        # ``standing`` AND the sprint has all required artifacts resolved
        # (a "ready to close but charter still open" signal).
        # This is intentionally conservative — full abandoned detection
        # requires walking archived sprints which is out of scope for the
        # active-spec scan.

    # V8 — abandoned-charter scan across archived sprints (INFO).
    warnings.extend(_check_abandoned_charters(repo))

    return warnings


def _check_abandoned_charters(repo_root: Path) -> list[WarningRecord]:
    """V8: charters referenced by archived sprints but still ``status:
    standing`` in their own frontmatter.

    Walks ``docs/sprints/archive/*/spec.yaml`` (charters in inbox/design
    don't have a uniform location, so this is heuristic). INFO-only;
    never strict-exit.
    """
    out: list[WarningRecord] = []
    archive = ledger_paths.compat_sprints_dir(repo_root) / "archive"
    if not archive.is_dir():
        return out
    # Collect (charter_path -> [archived_sprint_specs]).
    archived_refs: dict[str, list[Path]] = {}
    for sub in archive.iterdir():
        if not sub.is_dir() or not sub.name.startswith("sprint-"):
            continue
        spec_path = sub / "spec.yaml"
        if not spec_path.is_file():
            continue
        spec, parse_errors = load_spec_yaml(spec_path)
        if spec is None:
            continue
        cr = spec.get("charter_ref") or []
        if not isinstance(cr, list):
            continue
        for ref in cr:
            if not isinstance(ref, str) or not ref:
                continue
            if ref.startswith(_PARLEY_CHARTER_URI_PREFIX):
                continue  # opaque; can't introspect status from library
            archived_refs.setdefault(ref, []).append(spec_path)
    for charter_ref, _refs in sorted(archived_refs.items()):
        charter_path = repo_root / charter_ref
        if not charter_path.is_file():
            continue
        # Read the frontmatter; if status==standing, INFO-log.
        try:
            import frontmatter as _fm
            fm, _body = _fm.parse(charter_path)
        except Exception:
            continue
        status = fm.get("status") if isinstance(fm, dict) else None
        if status == "standing":
            out.append(WarningRecord(
                category="spec-yaml-abandoned-charter",
                path=str(charter_path),
                message=(
                    f"charter referenced by archived sprints but "
                    f"status: standing — consider closing"
                ),
            ))
    return out


# ---------- spec.yaml writer (used by /start-sprint --spec) ----------


def write_initial_spec_yaml(
    *,
    repo_root: Path,
    sprint_id: str,
    sprint_kind: str,
    author: str,
    owner_user: str = "user/local",
    has_user_journey: bool = False,
    charter_ref: list[str] | None = None,
    created_at_iso: str | None = None,
) -> Path:
    """Write an initial ``spec.yaml`` for a sprint with role-kind defaults
    per sub-spec §8.1.

    Defaults by kind:
    - ``kris-binding``: every standard artifact key with ``required: true``.
    - ``autonomous-arc``: every standard artifact key with ``required: false``.
    - ``routine``: minimal — schema_version + sprint_id + sprint_kind +
      empty required_artifacts mapping.
    - other registered kinds: empty required_artifacts; SM populates.

    Returns the path written. Does NOT validate against schema (the
    caller is responsible for validating after write if desired); this
    keeps the writer deterministic for tests.
    """
    if created_at_iso is None:
        from datetime import datetime, timezone
        created_at_iso = (
            datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        )

    sprint_dir = (
        ledger_paths.compat_sprints_dir(repo_root) / "active" / f"sprint-{sprint_id}"
    )
    spec_path = sprint_dir / "spec.yaml"

    kinds = _registered_kinds(repo_root)
    kind_info = kinds.get(sprint_kind, {})
    if sprint_kind == "kris-binding":
        required_default = True
    else:
        required_default = False

    required_artifacts: dict[str, dict] = {}
    if sprint_kind == "routine":
        # Minimal: no artifact entries.
        pass
    else:
        # Build entries for either the kind's registered keys (per-repo
        # config) or the standard built-in keys.
        artifact_keys = (
            kind_info.get("required_artifact_keys")
            or list(ARTIFACT_REF_KINDS.keys())
        )
        for key in artifact_keys:
            ref_kind = ARTIFACT_REF_KINDS.get(key, "path")
            entry: dict[str, Any] = {"required": required_default}
            if ref_kind == "parley_msg_id":
                entry["parley_msg_id"] = None
            else:
                entry["path"] = None
            required_artifacts[key] = entry

    spec: dict[str, Any] = {
        "schema_version": 1,
        "sprint_id": sprint_id,
        "sprint_kind": sprint_kind,
        "required_artifacts": required_artifacts,
        "binding_doctrines": [],
        "charter_ref": list(charter_ref or []),
        "created_at": created_at_iso,
        "created_by": author,
        "owner_user": owner_user,
        "has_user_journey": has_user_journey,
    }

    sprint_dir.mkdir(parents=True, exist_ok=True)
    yaml_text = yaml.safe_dump(
        spec, sort_keys=False, allow_unicode=True, default_flow_style=False,
    )
    tmp = spec_path.with_suffix(spec_path.suffix + ".tmp")
    tmp.write_text(yaml_text, encoding="utf-8")
    tmp.replace(spec_path)
    return spec_path


# ---------- strict-error category set ----------

# Categories that contribute to ``--strict`` exit per sub-spec §4.1.
# V3 normally WARN; the /end-sprint gate upgrades to the
# ``spec-yaml-required-missing-error`` category which IS strict.
STRICT_CATEGORIES: set[str] = {
    "spec-yaml-schema",
    "spec-yaml-golden-path-required",
    "spec-yaml-ship-epic-missing",
    "spec-yaml-required-missing-error",
}


def is_strict_category(category: str) -> bool:
    """Return True iff the given category contributes to --strict exit."""
    return category in STRICT_CATEGORIES
