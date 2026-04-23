"""Discovery: enumerate installed modules and query capabilities."""

from __future__ import annotations

import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore[no-redef]

from .schema import ManifestError, ModuleInfo, parse_manifest


def find_modules_root(start: Path | str | None = None) -> Path | None:
    """Walk up from ``start`` (default cwd) looking for a ``.modules/`` dir.

    Returns the path to the ``.modules/`` directory or None if none found.
    """
    here = Path(start or Path.cwd()).resolve()
    for candidate in (here, *here.parents):
        d = candidate / ".modules"
        if d.is_dir():
            return d
    return None


def load_module(dir_path: Path) -> ModuleInfo:
    """Load a single module from its ``.modules/<name>/`` directory.

    Raises ManifestError / OSError / tomllib.TOMLDecodeError on failure.
    For silent enumeration use ``installed_modules()`` instead.
    """
    manifest = dir_path / "module.toml"
    with manifest.open("rb") as f:
        data = tomllib.load(f)
    return parse_manifest(data, expected_name=dir_path.name)


def installed_modules(start: Path | str | None = None) -> dict[str, ModuleInfo]:
    """Enumerate all installed modules under the nearest ``.modules/`` directory.

    Returns a dict keyed by module name. Invalid or incompatible manifests
    are silently skipped; use ``load_module()`` directly if you need errors.
    """
    root = find_modules_root(start)
    if root is None:
        return {}

    mods: dict[str, ModuleInfo] = {}
    try:
        entries = sorted(root.iterdir())
    except OSError:
        return mods

    for entry in entries:
        if not entry.is_dir():
            continue
        try:
            info = load_module(entry)
        except (ManifestError, OSError, tomllib.TOMLDecodeError):
            continue
        mods[info.name] = info
    return mods


def is_installed(name: str, start: Path | str | None = None) -> bool:
    """True if module ``name`` has a valid manifest in the nearest .modules/."""
    return name in installed_modules(start)


def has_capability(
    name: str, capability: str, start: Path | str | None = None
) -> bool:
    """True if module ``name`` is installed AND advertises ``capability``."""
    info = installed_modules(start).get(name)
    return info is not None and capability in info.capabilities
