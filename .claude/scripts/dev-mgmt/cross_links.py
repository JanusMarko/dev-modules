"""Cross-link discovery + advisory checks (Sprint 7, D43).

Single-pass walk of the entity directories (decisions/, issues/,
reviews/, handoffs/, conversations/) plus the per-sprint plan.md /
retro.md, builds a graph of declared cross-links (each ``linked_*``
field on an entity becomes a directed edge entity -> target), then
emits advisory warnings for three drift categories:

1. ``cross_link_unresolved`` — the source declares a ``linked_<kind>``
   reference to a target slug that does not exist on disk under
   ``docs/<kind>/`` (or, for ``linked_handoffs``, doesn't exist in
   ``docs/handoffs/``). This is the most common drift signal in
   practice (rename, delete, or typo).

2. ``cross_link_unidirectional`` — **RETIRED (#16, Kris-decided
   forward-only CANONICAL model).** Cross-links are forward-only:
   the author links FORWARD; the target carries NO stored reciprocal
   and is NEVER expected to back-link. A missing reciprocal is
   therefore NOT a finding by construction — the old stored-reciprocity
   drift check (and its date-keyed/accepted forward-only suppression
   heuristic) is removed entirely. The forward-link-target-RESOLVABLE
   integrity guarantee is Check #1 (the target must resolve on disk).
   The REVERSE direction is a DERIVED projection — see
   ``derived_reverse_links()``: reverse adjacency is maintained in the
   ledger link index from canonical forward links, never duplicated on
   target entity frontmatter, so it cannot drift as stored reciprocal
   fields (the same eliminate-by-construction principle as 4.6i
   dual-recording: one canonical source, derived views never hand-authored).

3. ``msg_id_not_captured`` — the source declares a ``linked_msg_ids``
   reference to a msg-id that does not appear inside any captured
   Conversation entity's ``verbatim_msg_range`` (start, end). This
   catches "decision references parley msg-X but no Conversation
   entity preserves the conversation" gaps — the §D43 explicit
   second-bucket check.

The module is parley-agnostic (per CLAUDE.md Hard Rule 5): it reads
markdown + parses frontmatter only. The Conversation entity's
captured ``verbatim_msg_range`` is the sole source of truth for
which msg-ids are "captured"; reaching out to a live parley CLI is
explicitly NOT done here.

Advisory-only per D33 (hooks never block) + D44 (advisory validator).
The Stop hook's fast-subset SKIPS this module (D34 — too expensive
for every-Stop); only the on-demand ``dev-mgmt validate`` CLI path
runs cross-link checks.
"""
from __future__ import annotations

import datetime
import json
from collections import namedtuple
from pathlib import Path
from typing import Iterable

import frontmatter
import id_resolver
import ledger_paths

# (#16 forward-only canonical: the former S-B D3/R-C date-keyed
# forward-only SUPPRESSION heuristic + its ``_DATE_NN_HEAD`` regex are
# RETIRED with Check #2 — a missing reciprocal is no longer a finding
# at all, so there is nothing to suppress.)


WarningRecord = namedtuple("WarningRecord", ("category", "path", "message"))


LINK_INDEX_FILENAME = "link-index.json"
LINK_INDEX_SCHEMA_VERSION = 1


# Entity kinds discoverable as flat ``docs/<kind>/<slug>.md`` files.
# Order matters only for deterministic iteration in tests.
_FLAT_KINDS: tuple[str, ...] = (
    "decisions",
    "issues",
    "reviews",
    "handoffs",
    "conversations",
    # Phase 1 of re-arch arc: WIP-claim joins the flat-layout entities
    # so linked_decisions / linked_msg_ids carried in wip_claim
    # frontmatter participate in cross-link discovery.
    "wip",
    # PRD (charter docs/inbox/2026-06-02-prd-entity-cross-repo-pm-bridge-
    # charter.md): PRDs carry linked_decisions + linked_msg_ids that
    # participate in same-repo cross-link discovery. NOTE the cross-repo
    # cross_repo_prds field (charter AXIS-13) is intentionally NOT a
    # linked_* family member — it carries <repo>:<id> refs with no
    # in-repo resolution target (chunk-0 PG-5 ratify).
    "prds",
)


# Reverse-field naming convention: a ``linked_<kind>`` edge on a source
# of kind X is "satisfied" if the target's frontmatter contains a
# ``linked_<source-kind>`` field that includes the source's slug.
# ``_FIELD_TO_KIND`` lets us walk arbitrary linked_* fields and map
# them to the directory we should look the target up in.
_FIELD_TO_KIND: dict[str, str] = {
    "linked_decisions":     "decisions",
    "linked_issues":        "issues",
    "linked_reviews":       "reviews",
    "linked_handoffs":      "handoffs",
    "linked_conversations": "conversations",
}


# Inverse: given a SOURCE kind, what's the reverse field name that a
# TARGET of any other kind would use to backreference this source?
# Used by the unidirectional check (sub-check #2 above).
_KIND_TO_REVERSE_FIELD: dict[str, str] = {
    "decisions":     "linked_decisions",
    "issues":        "linked_issues",
    "reviews":       "linked_reviews",
    "handoffs":      "linked_handoffs",
    "conversations": "linked_conversations",
}


def _safe_parse(path: Path) -> dict | None:
    """Best-effort frontmatter parse — returns ``None`` on any failure.

    Cross-link checks are an outer layer; frontmatter-parse drift is
    already covered by ``validate.py``'s D35.3 check, so silent skip
    here keeps the cross-link warning channel uncluttered with parse
    noise that's already surfaced by a sibling check.
    """
    try:
        fm, _body = frontmatter.parse(path)
    except Exception:
        return None
    return fm if isinstance(fm, dict) else None


def is_index_file(path: Path | str) -> bool:
    """THE single index-exclusion predicate (B1-F1 / issue-2026-05-14-08).

    True for an entity-directory index file that MUST be excluded from
    entity/slug discovery: the canonical ``INDEX.md`` **and** any
    ``INDEX-*`` sibling (e.g. a real ``INDEX-prose-legacy.md`` archive).

    Eliminate-by-construction: this is the ONE definition of the
    exclusion contract — every discovery site in this module *and* in
    ``validate.py`` calls it, so the contract cannot drift across the
    sites again. The B1-F1 root cause was exactly that drift:
    ``validate.py`` carried the ``INDEX-*`` parity (issue-2026-05-14-08)
    but the delegated ``cross_links.py`` discovery path did not, so an
    ``INDEX-*`` stem leaked into the resolution-target universe and a
    dangling cross-link colliding with it silently FALSE-resolved —
    weakening reference integrity in the very guarantor the post-net
    cross-check trusts. Semantics are byte-identical to ``validate.py``'s
    prior inline contract (``name == "INDEX.md" or
    name.startswith("INDEX-")``) so consolidating it is behavior-
    preserving for ``validate.py`` and parity-restoring for this module.
    """
    name = path.name if isinstance(path, Path) else str(path)
    return name == "INDEX.md" or name.startswith("INDEX-")


def _iter_entities(
    repo_root: Path,
) -> Iterable[tuple[str, str, Path, dict]]:
    """Yield ``(kind, slug, path, frontmatter_dict)`` for every entity
    file under the discoverable directories.

    "kind" is the flat-dir name (decisions / issues / reviews / handoffs
    / conversations) OR ``"sprint-plan"`` / ``"retrospective"`` for the
    nested sprint files. The slug is the file stem (e.g.
    ``2026-05-14-07-...`` or ``sprint-dev-mgmt.7-plan``).
    """
    for kind in _FLAT_KINDS:
        d = ledger_paths.compat_kind_dir(repo_root, kind)
        if not d.exists():
            continue
        for path in sorted(d.glob("*.md")):
            if is_index_file(path):
                continue
            fm = _safe_parse(path)
            if fm is None:
                continue
            yield kind, path.stem, path, fm

    sprints = ledger_paths.compat_sprints_dir(repo_root)
    if not sprints.exists():
        return
    for sub in ("active", "archive"):
        sub_dir = sprints / sub
        if not sub_dir.exists():
            continue
        for sprint_dir in sorted(sub_dir.iterdir()):
            if not sprint_dir.is_dir():
                continue
            for fname, sub_kind in (("plan.md", "sprint-plan"),
                                    ("retro.md", "retrospective")):
                p = sprint_dir / fname
                if not p.exists():
                    continue
                fm = _safe_parse(p)
                if fm is None:
                    continue
                slug = str(fm.get("id") or f"{sub_kind}:{sprint_dir.name}")
                yield sub_kind, slug, p, fm


def _disk_slugs_for(repo_root: Path, kind: str) -> set[str]:
    """Return the set of slugs (file stems) present on disk for a kind."""
    d = ledger_paths.compat_kind_dir(repo_root, kind)
    if not d.exists():
        return set()
    return {p.stem for p in d.glob("*.md") if not is_index_file(p)}


def _load_cross_substrate_roots(repo_root: Path) -> list[Path]:
    """Read `[cross_links].cross_substrate_roots` from
    `.claude/workshop-lite-config.toml`.

    Issue 2026-05-15-06 / Sprint wl.13: when entities migrate to a
    parley dev-track substrate (Gate-3 Shape-A split), the canonical
    target for a `linked_<kind>` field may live in the other
    substrate. Operator (or installer) configures this list so
    Check #1 resolution unions the cross-substrate `docs/<kind>/`
    directories with the local one.

    Parley-agnostic by construction (CLAUDE.md Hard Rule 1): pure
    file I/O via tomllib + path validation. The SKILL/hook layer is
    where parley substrate discovery happens; the result lands here
    as a configured path.

    Returns empty list when:
    - the config file is absent (most repos won't have one),
    - the file is malformed,
    - the `[cross_links]` section is missing,
    - `cross_substrate_roots` is absent / not a list,
    - any individual entry isn't a string.

    Silently skips entries that don't resolve to existing directories
    (a stale path shouldn't crash the validator — issue surfaces as
    targets-still-unresolved warnings, which is the right user signal).
    """
    cfg_path = repo_root / ".claude" / "workshop-lite-config.toml"
    if not cfg_path.is_file():
        return []
    try:
        import tomllib
    except ImportError:
        return []
    try:
        with open(cfg_path, "rb") as fh:
            data = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return []
    section = data.get("cross_links") if isinstance(data, dict) else None
    if not isinstance(section, dict):
        return []
    raw = section.get("cross_substrate_roots")
    if not isinstance(raw, list):
        return []
    out: list[Path] = []
    for entry in raw:
        if not isinstance(entry, str) or not entry:
            continue
        p = Path(entry).expanduser()
        if p.is_dir():
            out.append(p)
    return out


def _load_msg_id_not_captured_cutoff_date(
    repo_root: Path,
) -> "datetime.date | None":
    """Read `[cross_links].msg_id_not_captured_cutoff_date` from
    `.claude/workshop-lite-config.toml`.

    Sprint wl.24 / issue 2026-05-31-03: when set, entities with
    `created_at` strictly BEFORE the cutoff date are exempted from
    Check #3 (`msg_id_not_captured`) even when corpus_present is True.
    This is the OPT-(b) "pre-conversation-capture-era entity-class
    grandfather suppression with explicit date-cutoff" mechanism per
    @user RATIFY msg-dd5c9deb97eb / Decision 2026-05-31-01.

    Default (None) = no cutoff filter = OPT-(c) accept-as-informational
    standing disposition operationally unchanged. Opt-in per repo via
    setting the cutoff string in TOML (any ISO-8601 YYYY-MM-DD parses).

    Parley-agnostic by construction (CLAUDE.md Hard Rule 1): pure
    file I/O via tomllib + date parsing.

    Returns None when:
    - the config file is absent,
    - the file is malformed,
    - the `[cross_links]` section is missing,
    - `msg_id_not_captured_cutoff_date` is absent / not a string,
    - the string doesn't parse as ISO date.
    """
    import datetime
    cfg_path = repo_root / ".claude" / "workshop-lite-config.toml"
    if not cfg_path.is_file():
        return None
    try:
        import tomllib
    except ImportError:
        return None
    try:
        with open(cfg_path, "rb") as fh:
            data = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return None
    section = data.get("cross_links") if isinstance(data, dict) else None
    if not isinstance(section, dict):
        return None
    raw = section.get("msg_id_not_captured_cutoff_date")
    if not isinstance(raw, str) or not raw:
        return None
    try:
        return datetime.date.fromisoformat(raw)
    except ValueError:
        return None


def _entity_created_date(fm: dict) -> "datetime.date | None":
    """Parse the entity's `created_at` frontmatter field to a date.

    Tolerates both string and datetime-ish forms produced by yaml.
    Returns None on absence or unparseable input. Used by Check #3's
    cutoff filter (wl.24); conservative on missing/malformed →
    caller treats None as "don't exempt" so bad-frontmatter entities
    still see the check.
    """
    import datetime
    raw = fm.get("created_at")
    if raw is None:
        return None
    if isinstance(raw, datetime.date) and not isinstance(raw, datetime.datetime):
        return raw
    if isinstance(raw, datetime.datetime):
        return raw.date()
    if isinstance(raw, str):
        # Tolerate "YYYY-MM-DD" and "YYYY-MM-DDTHH:MM:SSZ"-ish forms.
        s = raw.strip()
        if not s:
            return None
        try:
            return datetime.date.fromisoformat(s[:10])
        except ValueError:
            return None
    return None


def _unioned_disk_slugs_for(
    repo_root: Path, kind: str, cross_substrate_roots: list[Path],
) -> set[str]:
    """Return slugs present on disk for a kind, unioned across the
    local repo and any configured cross-substrate roots.

    Issue 2026-05-15-06 fix path (a): teach Check #1 to also resolve
    against the parley dev-track substrate when one is configured.
    """
    slugs = _disk_slugs_for(repo_root, kind)
    for root in cross_substrate_roots:
        slugs |= _disk_slugs_for(root, kind)
    return slugs


def _handoff_slugs_including_archive(repo_root: Path) -> set[str]:
    """Return handoff slugs present at `docs/handoffs/` OR
    `docs/handoffs/archive/`.

    Sprint workshop-lite.17 / issue 2026-05-15-07 Q-A: handoff
    `since_handoff_id` cursors may legitimately point at archived
    targets. `_disk_slugs_for("handoffs")` only sees the active dir,
    so cursors into `archive/` would silently dangle. This helper
    extends the lookup to both — used by Check #4 (the new
    since_handoff_id resolvability advisory).
    """
    slugs = _disk_slugs_for(repo_root, "handoffs")
    archive = ledger_paths.compat_kind_dir(repo_root, "handoffs") / "archive"
    if archive.exists():
        slugs |= {p.stem for p in archive.glob("*.md") if not is_index_file(p)}
    return slugs


def _captured_msg_id_set_from_root(root: Path) -> set[str]:
    """Per-root primitive: collect captured msg-ids from one repo's
    ``docs/conversations/``. Shared by local + cross-substrate scans.
    """
    captured: set[str] = set()
    conversations_dir = ledger_paths.compat_kind_dir(root, "conversations")
    if not conversations_dir.exists():
        return captured
    for path in conversations_dir.glob("*.md"):
        if is_index_file(path):
            continue
        fm = _safe_parse(path)
        if fm is None:
            continue
        rng = fm.get("verbatim_msg_range") or []
        if isinstance(rng, (list, tuple)):
            for mid in rng:
                if isinstance(mid, str) and mid.startswith("msg-"):
                    captured.add(mid)
        own = fm.get("linked_msg_ids") or []
        if isinstance(own, (list, tuple)):
            for mid in own:
                if isinstance(mid, str) and mid.startswith("msg-"):
                    captured.add(mid)
    return captured


def _captured_msg_id_set(
    repo_root: Path,
    cross_substrate_roots: list[Path] | None = None,
) -> set[str]:
    """Union of every msg-id that falls "inside" some captured
    Conversation's ``verbatim_msg_range``, scanned across the local
    repo AND any configured cross-substrate roots.

    The range is a 2-element list ``[first_msg_id, last_msg_id]`` (D27);
    we don't know the parley monotonic ordering between arbitrary
    msg-ids without consulting parley itself (forbidden — CLAUDE.md
    Hard Rule 5), so we approximate "captured" as: the msg-id appears
    EXACTLY at one of the endpoints, OR appears as the source-of-truth
    ``linked_msg_ids`` of the same Conversation entity. This is a
    deliberate undercount on a parley-agnostic basis; future work can
    expand it once parley exposes an ordering API.

    Empty-range captures (``[null, null]``) contribute nothing.

    Sprint wl.21 / issue 2026-05-16-01 fold-in: when
    ``cross_substrate_roots`` is non-empty, also scan each root's
    ``docs/conversations/`` and union those captures. Parallels the
    wl.13 ``_unioned_disk_slugs_for`` cross-substrate awareness on
    Check #1; pre-implements the Q8=a corpus_present transition
    mechanism so when the first workshop-lite Conversation capture
    lands (locally OR cross-substrate), Check #3 behaves correctly.
    """
    captured = _captured_msg_id_set_from_root(repo_root)
    if cross_substrate_roots:
        for root in cross_substrate_roots:
            captured |= _captured_msg_id_set_from_root(root)
    return captured


def _string_list(fm: dict, key: str) -> list[str]:
    """Coerce a frontmatter field to a list of non-empty strings.

    Defensive: tolerates None / single-string / non-list inputs so a
    typo in one entity's frontmatter doesn't crash the whole walk.
    Empty list when the key is absent or the value isn't list-like.
    """
    v = fm.get(key)
    if v is None:
        return []
    if isinstance(v, str):
        v = [v]
    if not isinstance(v, (list, tuple)):
        return []
    return [s for s in v if isinstance(s, str) and s]


def _link_index_path(repo_root: Path) -> Path:
    """Return the maintained reverse-link index path for this repo shape.

    WL2-initialized repos keep framework-owned derived indexes under the
    canonical ledger. Legacy tmp fixtures without a ``.workshop-lite`` marker
    use ``docs/`` so reading a fixture never creates the marker that would flip
    the compat resolver to ledger mode.
    """
    if (repo_root / ".workshop-lite").exists():
        return ledger_paths.ledger_root(repo_root) / LINK_INDEX_FILENAME
    return ledger_paths.legacy_root(repo_root) / LINK_INDEX_FILENAME


def _utc_now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).replace(
        microsecond=0,
    ).strftime("%Y-%m-%dT%H:%M:%SZ")


def _edge_type(field_name: str) -> str:
    """Convert a ``linked_*`` field name into the typed graph edge label."""
    if field_name.startswith("linked_"):
        return field_name[len("linked_"):].replace("_", "-")
    return field_name.replace("_", "-")


def _normalize_link_slug(value: str, kind: str) -> str:
    """Normalize a `linked_<kind>` value to a bare slug.

    Sprint workshop-lite.18 / issue 2026-05-31-02: the wl-rearch arc
    encoded many `linked_reviews` values as full paths
    (`docs/reviews/<slug>.md`) rather than bare slugs. Cross-link
    Check #1 was matching against bare-slug `disk_slugs`, so the
    full-path entries surfaced as `cross_link_unresolved` even when
    the target file existed.

    Forward-compatible normalization: strip a leading `docs/<kind>/`
    prefix + a trailing `.md` suffix if present. Bare slugs are
    returned unchanged. Cross-host `<host>:<id>` refs are unchanged
    (the cross-host check runs upstream and short-circuits before this).
    """
    s = value.strip()
    prefix = f"docs/{kind}/"
    if s.startswith(prefix):
        s = s[len(prefix):]
    if s.endswith(".md"):
        s = s[:-3]
    return s


def _normalized_target_slug(target_ref: str, target_kind: str) -> str:
    """Normalize a graph target ref for local reverse-index lookup."""
    try:
        _host, bare = id_resolver.resolve_id(target_ref)
    except id_resolver.IdResolverError:
        bare = target_ref
    if id_resolver.is_cross_host(target_ref):
        return target_ref
    return _normalize_link_slug(bare, target_kind)


def _forward_link_edges(repo_root: Path) -> list[dict]:
    """Materialize canonical forward ``linked_*`` fields as typed edges."""
    edges: list[dict] = []
    for source_kind, source_slug, source_path, fm in _iter_entities(repo_root):
        for field_name, target_kind in _FIELD_TO_KIND.items():
            for target_ref in _string_list(fm, field_name):
                edges.append({
                    "source_kind": source_kind,
                    "source_slug": source_slug,
                    "source_path": ledger_paths.display_path(
                        source_path, repo_root,
                    ),
                    "target_kind": target_kind,
                    "target_slug": _normalized_target_slug(
                        target_ref, target_kind,
                    ),
                    "target_ref": target_ref,
                    "via_field": field_name,
                    "edge_type": _edge_type(field_name),
                })
    edges.sort(
        key=lambda e: (
            e["target_kind"], e["target_slug"], e["source_kind"],
            e["source_slug"], e["via_field"], e["target_ref"],
        ),
    )
    return edges


def _reverse_entries_from_edges(edges: list[dict]) -> dict[str, list[dict]]:
    reverse: dict[str, list[dict]] = {}
    for edge in edges:
        key = f"{edge['target_kind']}/{edge['target_slug']}"
        reverse.setdefault(key, []).append({
            "source_kind": edge["source_kind"],
            "source_slug": edge["source_slug"],
            "via_field": edge["via_field"],
            "reverse_field": _KIND_TO_REVERSE_FIELD.get(
                edge["source_kind"],
            ),
            "edge_type": edge["edge_type"],
            "target_ref": edge["target_ref"],
        })
    for key in reverse:
        reverse[key].sort(
            key=lambda r: (
                r["source_kind"], r["source_slug"], r["via_field"],
                r["target_ref"],
            ),
        )
    return reverse


def rebuild_link_index(repo_root: str | Path) -> Path:
    """Refresh the maintained typed link graph + derived reverse index.

    The forward ``linked_*`` fields remain the source of truth. This function
    materializes their typed edges and the reverse projection into a ledger
    index so reverse queries can load a maintained structure instead of
    re-parsing every entity at query time. Entity writers call this after a
    successful write; callers may also run it explicitly after bulk/manual
    edits.
    """
    repo_root = Path(repo_root)
    edges = _forward_link_edges(repo_root)
    payload = {
        "schema_version": LINK_INDEX_SCHEMA_VERSION,
        "generated_at": _utc_now_iso(),
        "index_path": ledger_paths.display_path(
            _link_index_path(repo_root), repo_root,
        ),
        "forward_edges": edges,
        "reverse_edges": _reverse_entries_from_edges(edges),
    }
    path = _link_index_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)
    return path


def _load_link_index(repo_root: Path) -> dict:
    path = _link_index_path(repo_root)
    if not path.exists():
        rebuild_link_index(repo_root)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        rebuild_link_index(repo_root)
        data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != LINK_INDEX_SCHEMA_VERSION:
        rebuild_link_index(repo_root)
        data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data.get("reverse_edges"), dict):
        rebuild_link_index(repo_root)
        data = json.loads(path.read_text(encoding="utf-8"))
    return data


def _decode_reverse_key(key: str) -> tuple[str, str] | None:
    kind, sep, slug = key.partition("/")
    if not sep or not kind or not slug:
        return None
    return kind, slug


def run_cross_link_checks(repo_root: str | Path) -> list[WarningRecord]:
    """Run all three D43 cross-link checks against ``repo_root``.

    Returns a flat list of warnings; the caller (typically
    ``validate.run_checks``) concatenates with its own.

    Always advisory: no exception is raised regardless of how many
    warnings are emitted. The CLI's ``--strict`` flag is the only path
    to a non-zero process exit (D44.A / Q5 resolution).
    """
    repo_root = Path(repo_root)
    warnings: list[WarningRecord] = []

    # Issue 2026-05-15-06 / Sprint wl.13: load configured cross-
    # substrate roots so Check #1 can resolve forward-links to entities
    # migrated to a parley dev-track substrate (Gate-3 Shape-A split).
    # Empty list when not configured — preserves single-substrate
    # behavior for the common case.
    cross_substrate_roots = _load_cross_substrate_roots(repo_root)

    # Pre-compute target lookup tables for cheap repeated probes.
    # Union local + each configured cross-substrate root per kind.
    disk_slugs: dict[str, set[str]] = {
        kind: _unioned_disk_slugs_for(repo_root, kind, cross_substrate_roots)
        for kind in _FLAT_KINDS
    }
    captured_msg_ids = _captured_msg_id_set(repo_root, cross_substrate_roots)
    # Sprint wl.24 / issue 2026-05-31-03: optional pre-conversation-
    # capture-era cutoff (OPT-(b) per @user RATIFY msg-dd5c9deb97eb,
    # Decision 2026-05-31-01). Default None = OPT-(c) standing
    # accept-as-informational behavior unchanged. When set, entities
    # with created_at strictly < cutoff are exempted from Check #3.
    msg_id_not_captured_cutoff = _load_msg_id_not_captured_cutoff_date(
        repo_root,
    )
    # §12 Q8=a (LOCKED (a), @plan msg-686b28d4b319): grandfather the
    # msg_id_not_captured advisory by ABSENCE-OF-CAPTURE-CORPUS. When
    # captured_msg_ids is empty there is no Conversation source-of-truth
    # to validate against, so check #3 is structurally vacuous — it would
    # fire for EVERY entity with any linked_msg_ids. This is the post-
    # Gate-3 reality for a repo whose Conversation entities were migrated
    # out (e.g. workshop-lite → parley dev-track substrate): suppressing
    # the check here fulfils kris's actual Q8=a intent ("validate
    # --strict clean for CI") with the correct mechanism. Self-correcting:
    # the moment any Conversation entity contributes a captured msg-id the
    # corpus is non-empty again and the check regains its full teeth
    # (corpus-bearing repos are unaffected). (b) date-cutoff + (c)
    # advisory-only were rejected — see the locked decision.
    #
    # OPERATIONAL CAVEAT (forward-condition, tracked: issue 2026-05-16-01
    # "Q8=a absence-of-corpus grandfather is a CONDITIONAL strict-clean";
    # per @plan msg-8ac397503c1a directive 2(b) + @modules msg-149ad82815e3):
    # this is a CONDITIONAL strict-clean, NOT permanent. The grandfather
    # suppresses ONLY while captured_msg_ids is empty; the first real
    # workshop-lite Conversation capture flips corpus_present True and
    # re-fires msg_id_not_captured for every pre-existing entity with
    # legitimately-uncaptured linked_msg_ids. At that point the grandfather
    # mechanism must be revisited (date-cutoff or cross-substrate/dev-track
    # -aware) — same single-substrate-root as issue 2026-05-15-06 (which
    # is the DISTINCT check #1 cross_link_unresolved, not this check #3).
    # Do not let the conditional-clean be silently forgotten when corpus
    # state changes.
    corpus_present = bool(captured_msg_ids)

    # Index parsed entities so we can do reverse-field lookups without
    # re-reading each file.
    parsed: list[tuple[str, str, Path, dict]] = list(_iter_entities(repo_root))
    # (#16: the by_path reverse-lookup index is retired with Check #2 —
    # no reverse-field reciprocity is checked anymore.)

    for source_kind, _source_slug, source_path, fm in parsed:
        # #16 (Kris-decided, forward-only CANONICAL model): a forward
        # linked_<kind> edge carries NO stored reciprocal — the target
        # is NEVER expected to back-link. The sole forward-link
        # integrity guarantee is Check #1 (the target must RESOLVE).
        # The reverse direction is a DERIVED projection
        # (derived_reverse_links()), maintained from canonical forward
        # links in the ledger link index and never stored as reciprocal
        # target frontmatter => cannot drift as a hand-authored back-ref
        # (same eliminate-by-construction principle as 4.6i).

        for field_name, target_kind in _FIELD_TO_KIND.items():
            for target_slug in _string_list(fm, field_name):
                # Phase 4 (master §3.1 + D-WL-9 + D-RA-7): cross-host
                # `<host>:<id>` refs are VALID by construction — the
                # target lives on another host's filesystem and is
                # unreachable here. Resolve via id_resolver:
                #   - Bare id            → check current host on disk
                #   - `<current>:<id>`   → strip prefix, check on disk
                #   - `<other>:<id>`     → cross-host valid, NO warning
                #   - `org:<id>`         → placeholder, NO warning
                #     (deferred to multi-host gateway, master §8.2)
                try:
                    host, bare = id_resolver.resolve_id(target_slug)
                except id_resolver.IdResolverError:
                    # Malformed id string — surface as unresolved per
                    # the existing behavior (the original check matched
                    # the full string against disk slugs, which would
                    # have missed for any colon-bearing input anyway).
                    warnings.append(WarningRecord(
                        category="cross_link_unresolved",
                        path=str(source_path),
                        message=(
                            f"{field_name} -> {target_slug}: "
                            f"target file missing in docs/{target_kind}/"
                        ),
                    ))
                    continue
                if id_resolver.is_cross_host(target_slug):
                    # Cross-host (including org:) — never warn; deferred
                    # to the multi-host gateway primitive.
                    continue
                # Check #1 == the forward-link-target-RESOLVABLE
                # integrity check (#16, Kris-decided): a forward
                # linked_<kind> edge MUST resolve to an existing
                # target of that kind. (The retired Check #2
                # stored-reciprocity drift check is gone — forward-only
                # is canonical; reverse is derived, never stored.)
                # Sprint wl.18: normalize full-path form
                # (`docs/<kind>/<slug>.md`) to bare slug before lookup
                # — wl-rearch arc encoded many linked_reviews this way.
                bare = _normalize_link_slug(bare, target_kind)
                if bare not in disk_slugs.get(target_kind, set()):
                    warnings.append(WarningRecord(
                        category="cross_link_unresolved",
                        path=str(source_path),
                        message=(
                            f"{field_name} -> {target_slug}: "
                            f"target file missing in docs/{target_kind}/"
                        ),
                    ))

        # Check #4 (Sprint workshop-lite.17 / issue 2026-05-15-07 Q-A):
        # handoff `since_handoff_id` cursors must resolve to a handoff
        # that exists in EITHER `docs/handoffs/` (active) OR
        # `docs/handoffs/archive/` (so cursors into archived handoffs
        # don't silently dangle when handoffs are moved). Advisory
        # category `since_handoff_id_unresolved` — distinct from Check
        # #1's `cross_link_unresolved` because `since_handoff_id` is a
        # cursor field, not a `linked_*` list. Skipped for non-handoff
        # source kinds (the field is handoff-specific).
        if source_kind == "handoffs":
            cursor = fm.get("since_handoff_id")
            if isinstance(cursor, str) and cursor:
                try:
                    _host, bare_cursor = id_resolver.resolve_id(cursor)
                except id_resolver.IdResolverError:
                    bare_cursor = cursor
                if (not id_resolver.is_cross_host(cursor)
                        and bare_cursor not in _handoff_slugs_including_archive(
                            repo_root)):
                    warnings.append(WarningRecord(
                        category="since_handoff_id_unresolved",
                        path=str(source_path),
                        message=(
                            f"since_handoff_id -> {cursor}: target file "
                            f"missing in docs/handoffs/ AND "
                            f"docs/handoffs/archive/"
                        ),
                    ))

        # Check #3: linked_msg_ids not captured in any Conversation range.
        # Conversation entities are themselves the source-of-truth for
        # what's "captured", so we skip the check for the Conversation's
        # OWN linked_msg_ids field (the conversation IS the capture).
        if source_kind == "conversations":
            continue
        # Q8=a grandfather: no capture corpus → check is vacuous, skip.
        if not corpus_present:
            continue
        # Sprint wl.24 / issue 2026-05-31-03 OPT-(b): pre-conversation-
        # capture-era cutoff. When configured AND entity's created_at
        # strictly < cutoff, exempt this entity from Check #3. Conservative
        # on missing/unparseable created_at (no exemption — ambiguity
        # defaults to checking, per design Case C4).
        if msg_id_not_captured_cutoff is not None:
            entity_date = _entity_created_date(fm)
            if entity_date is not None and entity_date < msg_id_not_captured_cutoff:
                continue
        for mid in _string_list(fm, "linked_msg_ids"):
            if id_resolver.is_cross_host(mid):
                continue
            if mid not in captured_msg_ids:
                warnings.append(WarningRecord(
                    category="msg_id_not_captured",
                    path=str(source_path),
                    message=(
                        f"linked_msg_ids -> {mid}: msg-id not captured "
                        f"in any Conversation entity's verbatim_msg_range"
                    ),
                ))

    return warnings


def derived_reverse_links(
    repo_root: str | Path,
) -> dict[tuple[str, str], list[dict]]:
    """#16 — the maintained DERIVED reverse-link projection.

    The canonical truth is the FORWARD ``linked_<kind>`` edges on each
    entity. The reverse direction is NEVER stored on target entities (no
    reciprocal back-ref field). Instead, BC0.4 materializes a maintained
    ledger index of typed forward edges plus their reverse projection.
    Writers refresh that index after successful entity writes; this reader
    loads the maintained structure and only rebuilds for absent/malformed
    index recovery.

    Returns ``{(target_kind, target_slug): [ {source_kind, source_slug,
    via_field, reverse_field}, ... ]}`` — every entity that
    forward-links a given target, i.e. the "what points AT me" view a
    stored reciprocal would have carried, derived instead.
    """
    repo_root = Path(repo_root)
    data = _load_link_index(repo_root)
    reverse: dict[tuple[str, str], list[dict]] = {}
    for encoded_key, entries in data.get("reverse_edges", {}).items():
        key = _decode_reverse_key(encoded_key)
        if key is None or not isinstance(entries, list):
            continue
        clean_entries = [e for e in entries if isinstance(e, dict)]
        clean_entries.sort(
            key=lambda r: (
                str(r.get("source_kind") or ""),
                str(r.get("source_slug") or ""),
                str(r.get("via_field") or ""),
                str(r.get("target_ref") or ""),
            ),
        )
        reverse[key] = clean_entries
    return reverse
