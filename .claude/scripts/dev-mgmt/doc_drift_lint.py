"""Doc-drift lint — detect spec-doc enumeration tags that have diverged
from the matching code-dir layout.

Charter (`docs/inbox/2026-05-23-stop-stopping-priority-backlog.md` item 3):
catch the F1-spec-§6 class-mismatch pattern (where a spec doc enumerates
structure that the actual code has diverged from) before a human reviewer
has to surface it as drift.

Opt-in by mere presence of ``<repo>/.claude/doc-drift-lint.toml``. No file
=> silent skip (zero overhead, charter "opt-in via repo config" satisfied).

PARLEY-AGNOSTIC (CLAUDE.md Hard Rule 1): never imports or shells parley.
ADVISORY-BY-DEFAULT (Hard Rule 6 / D43): emits WarningRecord triples,
never raises — a malformed config produces ``doc_drift_lint_config``
warnings rather than an exception.

Config schema (``.claude/doc-drift-lint.toml``)::

    schema_version = 1

    [[rules]]
    name = "maxai-F-screens"
    spec_glob = "docs/design/F*-spec*.md"
    identifier_pattern = '^F(\\d+)\\b'
    code_dir_template = "web/components/screens/F{n}/"
    mode = "bidirectional"   # default; or spec_only | code_only | report_only

The ``{n}`` token in ``code_dir_template`` is substituted with the matched
tag. If the regex has a capture group, group(1) is the tag; otherwise the
entire match is the tag.
"""
from __future__ import annotations

import re
import tomllib
from collections import namedtuple
from pathlib import Path

WarningRecord = namedtuple("WarningRecord", ("category", "path", "message"))

CONFIG_REL_PATH = ".claude/doc-drift-lint.toml"
_VALID_MODES = ("bidirectional", "spec_only", "code_only", "report_only")
_PLACEHOLDER = "{n}"


def _load_config(repo_root: Path) -> dict | None:
    """Parse the config file. Absent => None. Malformed => None (graceful).

    A malformed file is reported as a ``doc_drift_lint_config`` warning by
    the public entry; this loader's only job is the raw parse.
    """
    cfg_path = repo_root / CONFIG_REL_PATH
    if not cfg_path.exists():
        return None
    try:
        with open(cfg_path, "rb") as fh:
            return tomllib.load(fh)
    except (tomllib.TOMLDecodeError, OSError):
        return {"_malformed": True}


def _extract_tag(match: re.Match) -> str:
    """First capture group if present, else the whole match."""
    if match.lastindex:
        return match.group(1)
    return match.group(0)


def _scan_spec_tags(
    repo_root: Path, spec_glob: str, pattern: re.Pattern,
) -> dict[str, tuple[Path, int]]:
    """Scan spec_glob-matched files for ``pattern``.

    Returns ``{tag: (path, line_no)}`` recording the FIRST occurrence's
    provenance per tag (used for warning location).
    """
    found: dict[str, tuple[Path, int]] = {}
    for path in sorted(repo_root.glob(spec_glob)):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for line_no, line in enumerate(text.splitlines(), 1):
            m = pattern.search(line)
            if not m:
                continue
            tag = _extract_tag(m)
            if tag not in found:
                found[tag] = (path, line_no)
    return found


def _parent_dir_of_template(code_dir_template: str) -> str:
    """Return the parent directory of the basename slot in the template.

    Example: ``"src/screens/F{n}/"`` => ``"src/screens"``. The basename
    portion is ``"F{n}"`` (everything after the last ``/`` before ``{n}``,
    minus the trailing slash) — that's where the tag lives and where the
    identifier_pattern is run for the code-side scan.

    The split is done at the last ``/`` BEFORE the placeholder, so a
    template like ``"foo/{n}/bar/"`` correctly resolves to ``"foo"`` and
    NOT ``"foo/{n}/bar"`` (which would have us look for children named
    "bar/" — meaningless).
    """
    cut = code_dir_template.find(_PLACEHOLDER)
    if cut == -1:
        return code_dir_template.rstrip("/")
    head = code_dir_template[:cut]
    last_slash = head.rfind("/")
    if last_slash == -1:
        return ""
    return head[:last_slash]


def _scan_code_dirs(
    repo_root: Path, code_dir_template: str, pattern: re.Pattern,
) -> dict[str, Path]:
    """Collect immediate child subdirs of the template's parent whose
    basename matches ``pattern``.

    Absent parent dir => empty dict (the spec side will then report all
    spec tags as missing — that IS the drift signal: code dirs ABSENT).
    """
    if _PLACEHOLDER not in code_dir_template:
        return {}
    parent_rel = _parent_dir_of_template(code_dir_template)
    parent_path = repo_root / parent_rel if parent_rel else repo_root
    if not parent_path.exists() or not parent_path.is_dir():
        return {}
    found: dict[str, Path] = {}
    for child in sorted(parent_path.iterdir()):
        if not child.is_dir():
            continue
        m = pattern.search(child.name)
        if not m:
            continue
        tag = _extract_tag(m)
        found[tag] = child  # last-writer-wins; tags should be unique in practice
    return found


def _expand_code_path(template: str, tag: str) -> str:
    return template.replace(_PLACEHOLDER, tag)


_ValidatedRule = tuple[str, str, "re.Pattern[str]", str | None, str]


def _validate_rule(rule: dict) -> _ValidatedRule | str:
    """Validate a single rule table.

    Returns either a 5-tuple ``(name, spec_glob, pattern, code_dir_template,
    mode)`` or an error-message string describing what's wrong. The caller
    converts the string into a config-warning.
    """
    name = str(rule.get("name") or "<unnamed>")
    spec_glob = rule.get("spec_glob")
    pat = rule.get("identifier_pattern")
    if not isinstance(spec_glob, str) or not spec_glob:
        return f"rule {name!r}: missing or empty spec_glob"
    if not isinstance(pat, str) or not pat:
        return f"rule {name!r}: missing or empty identifier_pattern"
    try:
        pattern = re.compile(pat)
    except re.error as exc:
        return f"rule {name!r}: invalid identifier_pattern regex: {exc}"
    code_dir_template = rule.get("code_dir_template")
    if code_dir_template is not None and not isinstance(code_dir_template, str):
        return f"rule {name!r}: code_dir_template must be a string or absent"
    mode = rule.get("mode", "bidirectional")
    if mode not in _VALID_MODES:
        return (
            f"rule {name!r}: mode must be one of "
            f"{_VALID_MODES}, got {mode!r}"
        )
    if mode != "report_only" and not code_dir_template:
        return f"rule {name!r}: mode={mode} requires code_dir_template"
    if code_dir_template and _PLACEHOLDER not in code_dir_template and mode != "report_only":
        return (
            f"rule {name!r}: code_dir_template must contain "
            f"{_PLACEHOLDER!r} (the tag-substitution slot)"
        )
    return (name, spec_glob, pattern, code_dir_template, mode)


def _check_rule(
    repo_root: Path,
    name: str,
    spec_glob: str,
    pattern: "re.Pattern[str]",
    code_dir_template: str | None,
    mode: str,
) -> list[WarningRecord]:
    spec_tags = _scan_spec_tags(repo_root, spec_glob, pattern)

    if mode == "report_only":
        # Don't enumerate every tag as a warning — that'd be noise. But warn
        # if the glob matched zero tags (likely misconfig — pattern/glob drift).
        if not spec_tags:
            return [WarningRecord(
                category="doc_drift_lint",
                path=str((repo_root / CONFIG_REL_PATH).relative_to(repo_root)),
                message=(
                    f"rule {name!r} (report_only): spec_glob "
                    f"{spec_glob!r} matched no tags"
                ),
            )]
        return []

    assert code_dir_template is not None  # _validate_rule guarantees this
    code_tags = _scan_code_dirs(repo_root, code_dir_template, pattern)

    warnings: list[WarningRecord] = []
    spec_set = set(spec_tags.keys())
    code_set = set(code_tags.keys())

    if mode in ("bidirectional", "spec_only"):
        for tag in sorted(spec_set - code_set):
            src_path, src_line = spec_tags[tag]
            try:
                rel_src = src_path.relative_to(repo_root)
            except ValueError:
                rel_src = src_path
            expected = _expand_code_path(code_dir_template, tag)
            warnings.append(WarningRecord(
                category="doc_drift_lint",
                path=f"{rel_src}:{src_line}",
                message=(
                    f"rule {name!r}: spec tag {tag!r} has no matching "
                    f"code dir at {expected}"
                ),
            ))

    if mode in ("bidirectional", "code_only"):
        for tag in sorted(code_set - spec_set):
            code_path = code_tags[tag]
            try:
                rel_code = code_path.relative_to(repo_root)
            except ValueError:
                rel_code = code_path
            warnings.append(WarningRecord(
                category="doc_drift_lint",
                path=str(rel_code),
                message=(
                    f"rule {name!r}: code dir {code_path.name!r} (tag "
                    f"{tag!r}) has no matching spec tag in {spec_glob}"
                ),
            ))

    return warnings


def run_doc_drift_checks(repo_root: str | Path) -> list[WarningRecord]:
    """Public entry. Returns advisory warning list; never raises.

    - No config file => ``[]`` (silent skip; charter opt-in).
    - Malformed TOML => one ``doc_drift_lint_config`` warning.
    - Each invalid rule => one ``doc_drift_lint_config`` warning (rule
      skipped; other rules still run — eliminate-by-construction: a single
      typo can't blind the rest).
    """
    repo_root = Path(repo_root)
    cfg = _load_config(repo_root)
    if cfg is None:
        return []
    if cfg.get("_malformed"):
        return [WarningRecord(
            category="doc_drift_lint_config",
            path=str((repo_root / CONFIG_REL_PATH).relative_to(repo_root)),
            message="config file present but failed to parse as TOML",
        )]

    rules = cfg.get("rules")
    if not isinstance(rules, list):
        return [WarningRecord(
            category="doc_drift_lint_config",
            path=str((repo_root / CONFIG_REL_PATH).relative_to(repo_root)),
            message="config has no `rules` array; nothing to check",
        )]

    warnings: list[WarningRecord] = []
    for raw_rule in rules:
        if not isinstance(raw_rule, dict):
            warnings.append(WarningRecord(
                category="doc_drift_lint_config",
                path=str((repo_root / CONFIG_REL_PATH).relative_to(repo_root)),
                message=f"rule entry is not a table: {raw_rule!r}",
            ))
            continue
        validated = _validate_rule(raw_rule)
        if isinstance(validated, str):
            warnings.append(WarningRecord(
                category="doc_drift_lint_config",
                path=str((repo_root / CONFIG_REL_PATH).relative_to(repo_root)),
                message=validated,
            ))
            continue
        name, spec_glob, pattern, code_dir_template, mode = validated
        warnings.extend(_check_rule(
            repo_root, name, spec_glob, pattern, code_dir_template, mode,
        ))
    return warnings
