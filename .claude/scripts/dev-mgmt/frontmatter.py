"""YAML frontmatter parse and write for markdown entity files.

Files are expected to start with ``---\\n``, contain a YAML mapping, then
``\\n---\\n``, then the markdown body.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

_FM_RE = re.compile(r"\A---\n(.*?)\n---\n?(.*)\Z", re.DOTALL)


def parse(path: str | Path) -> tuple[dict, str]:
    """Parse a markdown file with YAML frontmatter.

    Returns ``(frontmatter_dict, body_string)``. Raises ``ValueError`` if the
    file is missing frontmatter delimiters or the YAML does not parse as a
    mapping.
    """
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    m = _FM_RE.match(text)
    if not m:
        raise ValueError(f"{path}: missing or malformed YAML frontmatter")
    fm = yaml.safe_load(m.group(1)) or {}
    if not isinstance(fm, dict):
        raise ValueError(f"{path}: frontmatter did not parse as a mapping")
    return fm, m.group(2)


def write(path: str | Path, fm: dict, body: str) -> None:
    """Write a markdown file with YAML frontmatter and body, atomically."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    yaml_text = yaml.safe_dump(
        fm, sort_keys=False, allow_unicode=True, default_flow_style=False
    )
    content = f"---\n{yaml_text}---\n{body}"
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)
