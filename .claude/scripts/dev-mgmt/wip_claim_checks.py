"""Advisory drift checks for WIP-claim entities (sub-spec §5).

Five rules, all ADVISORY (the same advisory-by-default convention as
``cross_links.py``):

  - V1 ORPHANED       — claimed claim with seat absent from roster.
  - V2 STALE          — claimed claim past expires_at.
  - V3 PATH-COLLISION — two claimed claims with overlapping paths
                        (exact-string match per Q-WL-4 default).
  - V4 UNRESOLVED-SCOPE — scope refers to a sprint/decision/design-doc
                        that doesn't exist in the entity index.
  - V5 PATH-NONEXISTENT — a claimed path doesn't exist on disk.

PARLEY-AGNOSTIC (CLAUDE.md Hard Rule 1): this module never imports
or shells out to parley. The optional roster set for V1 is supplied
by the caller (the validate-state hook script or test harness); when
absent, V1 is SKIPPED silently.

HOOKS-NEVER-BLOCK (Hard Rule 5 / D33): all warnings are advisory and
non-fatal; ``--strict`` upgrades V1-V4 to errors at the CLI layer.
V5 stays INFO regardless of strict.
"""
from __future__ import annotations

import os.path
from collections import namedtuple
from datetime import datetime, timezone
from pathlib import Path

import cross_links
import frontmatter
import ledger_paths

WarningRecord = namedtuple("WarningRecord", ("category", "path", "message"))


_ACTIVE_STATE = "claimed"


def _canonicalize_path(p: str) -> str:
    """Canonicalize a path string for V3 exact-string collision detection.

    Per verifier-α MED #2 closure: mirrors
    :func:`wip_claim._canonicalize_path` (kept duplicated to avoid a
    library cross-import; both call ``os.path.normpath`` deterministically
    so the normalize is identical-by-construction). ``./foo`` / ``foo`` /
    ``foo/`` all collapse to ``foo``; collisions previously hidden by
    surface-form divergence now register. Stays Hard-Rule-7-clean:
    structural normalize, not graded judgment.
    """
    if not isinstance(p, str) or not p:
        return p
    return os.path.normpath(p)


def _safe_parse(path: Path) -> dict | None:
    try:
        fm, _body = frontmatter.parse(path)
    except Exception:
        return None
    return fm if isinstance(fm, dict) else None


def _iter_wip_claims(repo_root: Path):
    """Yield ``(path, fm)`` for every wip_claim entity under
    ``docs/wip/``. Index files + parse failures are silently skipped.
    """
    wip_dir = ledger_paths.compat_kind_dir(repo_root, "wip")
    if not wip_dir.exists():
        return
    for path in sorted(wip_dir.glob("*.md")):
        if cross_links.is_index_file(path):
            continue
        fm = _safe_parse(path)
        if fm is None:
            continue
        if fm.get("type") != "wip_claim":
            continue
        yield path, fm


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso_utc(value: object) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _check_orphans(
    repo_root: Path,
    *,
    roster: set[str] | None,
) -> list[WarningRecord]:
    """V1 ORPHANED — claimed claim with seat absent from roster.

    ``roster`` is the set of FQID member strings believed to be live.
    When ``None`` (parley absent or roster not provided), V1 is
    silently SKIPPED — Hard Rule 1 parley-agnostic-at-base.
    """
    if roster is None:
        return []
    warnings: list[WarningRecord] = []
    for path, fm in _iter_wip_claims(repo_root):
        if fm.get("token_state") != _ACTIVE_STATE:
            continue
        seat = fm.get("seat")
        if not seat:
            continue
        if seat not in roster:
            warnings.append(WarningRecord(
                category="wip_claim_orphaned",
                path=str(path),
                message=(
                    f"wip_claim {fm.get('id')!r} orphaned — seat {seat!r} "
                    f"not in roster; recommend record-wip-release "
                    f"{fm.get('id')}"
                ),
            ))
    return warnings


def _check_stale(
    repo_root: Path,
    *,
    now: datetime | None = None,
) -> list[WarningRecord]:
    """V2 STALE — claimed claim past expires_at."""
    if now is None:
        now = _utc_now()
    warnings: list[WarningRecord] = []
    for path, fm in _iter_wip_claims(repo_root):
        if fm.get("token_state") != _ACTIVE_STATE:
            continue
        exp = _parse_iso_utc(fm.get("expires_at"))
        if exp is None:
            continue
        if now > exp:
            delta = now - exp
            secs = int(delta.total_seconds())
            hours, rem = divmod(secs, 3600)
            minutes = rem // 60
            if hours and minutes:
                ago = f"{hours}h {minutes}m"
            elif hours:
                ago = f"{hours}h"
            else:
                ago = f"{minutes}m"
            warnings.append(WarningRecord(
                category="wip_claim_stale",
                path=str(path),
                message=(
                    f"wip_claim {fm.get('id')!r} stale — past expires_at "
                    f"by {ago}; recommend record-wip-release "
                    f"{fm.get('id')}"
                ),
            ))
    return warnings


def _check_path_collisions(
    repo_root: Path,
) -> list[WarningRecord]:
    """V3 PATH-COLLISION — two claimed claims with overlapping paths.

    Q-WL-4 default: exact-string match (no glob expansion). Same-seat
    collisions are INFO not WARN (a single seat may legitimately refine
    its claim scope).
    """
    warnings: list[WarningRecord] = []
    claims: list[tuple[Path, dict]] = []
    for path, fm in _iter_wip_claims(repo_root):
        if fm.get("token_state") != _ACTIVE_STATE:
            continue
        claims.append((path, fm))

    # Build canonical-path -> [(claim_id, seat, path_to_file, raw_path)]
    # index. Per verifier-α MED #2 closure the key is the canonicalized
    # form (`os.path.normpath`); the raw surface-form is retained for
    # the warning message so the operator still sees the original
    # divergent strings in the cert.
    path_index: dict[str, list[tuple[str, str, Path, str]]] = {}
    for path, fm in claims:
        claim_id = str(fm.get("id") or path.stem)
        seat = str(fm.get("seat") or "?")
        for p in fm.get("paths") or []:
            if not isinstance(p, str):
                continue
            key = _canonicalize_path(p)
            path_index.setdefault(key, []).append((claim_id, seat, path, p))

    seen_pairs: set[tuple[str, str, str]] = set()
    for canonical, owners in path_index.items():
        if len(owners) < 2:
            continue
        for i in range(len(owners)):
            for j in range(i + 1, len(owners)):
                a_id, a_seat, a_path, a_raw = owners[i]
                b_id, b_seat, b_path, b_raw = owners[j]
                # Deterministic dedupe: order by claim_id.
                pair_key = tuple(sorted((a_id, b_id))) + (canonical,)
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)
                same_seat = (a_seat == b_seat)
                category = (
                    "wip_claim_path_collision_same_seat"
                    if same_seat else
                    "wip_claim_path_collision"
                )
                level = "INFO" if same_seat else "WARN"
                # Surface both raw forms if they diverge (post-MED-#2
                # normalize); otherwise a single form for readability.
                if a_raw == b_raw:
                    path_text = repr(a_raw)
                else:
                    path_text = (
                        f"{a_raw!r} ~ {b_raw!r} "
                        f"(canonical: {canonical!r})"
                    )
                warnings.append(WarningRecord(
                    category=category,
                    path=str(a_path),
                    message=(
                        f"{level}: wip_claim path collision — {a_id} and "
                        f"{b_id} both claim {path_text}"
                        + (" (same seat)" if same_seat else "")
                    ),
                ))
    return warnings


def _check_unresolved_scope(
    repo_root: Path,
) -> list[WarningRecord]:
    """V4 UNRESOLVED-SCOPE — scope refers to a non-existent entity.

    Scope tokens recognized:
      - ``sprint:<id>`` → checks docs/sprints/{active,archive}/sprint-<id>/
      - ``decision:<slug>`` → checks docs/decisions/<slug>.md
      - ``design:<doc-name>`` → checks docs/design/<doc-name>.md
      - ``arc:<id>`` → no resolution target yet; advisory-skip (arc
        entities aren't a substrate type per Phase-0 scope)
      - ``repo:<area>`` → no resolution target; skip.
    """
    warnings: list[WarningRecord] = []
    for path, fm in _iter_wip_claims(repo_root):
        scope = fm.get("scope")
        if not isinstance(scope, str) or ":" not in scope:
            continue
        prefix, _, body = scope.partition(":")
        body = body.strip()
        if not body:
            continue
        resolved = True
        if prefix == "sprint":
            sprints = ledger_paths.compat_sprints_dir(repo_root)
            active = sprints / "active" / f"sprint-{body}"
            archived = sprints / "archive" / f"sprint-{body}"
            resolved = active.exists() or archived.exists()
        elif prefix == "decision":
            resolved = (
                ledger_paths.compat_kind_dir(repo_root, "decisions")
                / f"{body}.md"
            ).exists()
        elif prefix == "design":
            # Tolerate both with and without the .md extension.
            d = ledger_paths.legacy_root(repo_root) / "design"
            resolved = (
                (d / f"{body}.md").exists()
                or (d / body).exists()
            )
        else:
            # arc:, repo:, or unknown prefix — not a resolution target.
            continue
        if not resolved:
            warnings.append(WarningRecord(
                category="wip_claim_unresolved_scope",
                path=str(path),
                message=(
                    f"wip_claim {fm.get('id')!r} scope {scope!r} unresolved"
                ),
            ))
    return warnings


def _check_path_nonexistent(
    repo_root: Path,
) -> list[WarningRecord]:
    """V5 PATH-NONEXISTENT — claimed path doesn't exist on disk.

    INFO-only (sub-spec §5.5): a claim may legitimately precede file
    creation, so this never WARNs and never blocks even under strict.
    """
    warnings: list[WarningRecord] = []
    for path, fm in _iter_wip_claims(repo_root):
        if fm.get("token_state") != _ACTIVE_STATE:
            continue
        for p in fm.get("paths") or []:
            if not isinstance(p, str) or not p:
                continue
            # Resolve relative to repo_root; tolerate '.' meaning root.
            rel = p
            full = repo_root / rel
            if not full.exists():
                warnings.append(WarningRecord(
                    category="wip_claim_path_nonexistent",
                    path=str(path),
                    message=(
                        f"INFO: wip_claim {fm.get('id')!r} path {p!r} "
                        "does not exist (yet)"
                    ),
                ))
    return warnings


def run_wip_claim_checks(
    repo_root: str | Path,
    *,
    roster: set[str] | None = None,
    now: datetime | None = None,
) -> list[WarningRecord]:
    """Run all five V1-V5 advisory checks against ``repo_root``.

    Returns a flat list of warnings; the caller concatenates with its
    own. Advisory-only; the ``--strict`` CLI flag is the only path to
    non-zero exit, and only V1-V4 promote under strict (V5 stays INFO).

    ``roster`` (optional): set of seat FQIDs believed live. When None,
    V1 is silently skipped (parley-absent or roster-unavailable). The
    skill / hook layer queries parley and passes the set in; the
    library never reaches for parley itself (Hard Rule 1).
    """
    repo_root = Path(repo_root)
    warnings: list[WarningRecord] = []
    warnings.extend(_check_orphans(repo_root, roster=roster))
    warnings.extend(_check_stale(repo_root, now=now))
    warnings.extend(_check_path_collisions(repo_root))
    warnings.extend(_check_unresolved_scope(repo_root))
    warnings.extend(_check_path_nonexistent(repo_root))
    return warnings


# Categories that --strict promotes to ERROR (V1-V4). V5 + same-seat
# collision stay advisory.
STRICT_PROMOTING_CATEGORIES: frozenset[str] = frozenset({
    "wip_claim_orphaned",
    "wip_claim_stale",
    "wip_claim_path_collision",
    "wip_claim_unresolved_scope",
})
