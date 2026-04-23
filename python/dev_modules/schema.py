"""Schema types and validation for dev-modules manifests."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ModuleInfo:
    """Validated view of a ``.modules/<name>/module.toml`` manifest."""

    name: str
    version: str
    description: str = ""
    capabilities: tuple[str, ...] = ()
    config: dict[str, Any] = field(default_factory=dict)

    def has_capability(self, capability: str) -> bool:
        return capability in self.capabilities


class ManifestError(ValueError):
    """Raised when a module.toml is structurally invalid or incompatible."""


def parse_manifest(data: dict[str, Any], *, expected_name: str) -> ModuleInfo:
    """Validate a parsed TOML dict against the schema and return a ModuleInfo.

    Raises ManifestError on any validation failure. Silently-lenient parsing
    (for the ``installed_modules`` enumeration path) is handled by callers.
    """
    schema_version = data.get("schema_version")
    if schema_version != SCHEMA_VERSION:
        raise ManifestError(
            f"unsupported schema_version {schema_version!r} "
            f"(expected {SCHEMA_VERSION})"
        )

    name = data.get("name")
    if not isinstance(name, str) or not name:
        raise ManifestError("missing or invalid 'name'")
    if name != expected_name:
        raise ManifestError(
            f"'name' field {name!r} does not match directory name "
            f"{expected_name!r}"
        )

    version = data.get("version")
    if not isinstance(version, str) or not version:
        raise ManifestError("missing or invalid 'version'")

    description = data.get("description", "")
    if not isinstance(description, str):
        description = ""

    caps_raw = data.get("capabilities", [])
    if not isinstance(caps_raw, list):
        raise ManifestError("'capabilities' must be a list of strings")
    capabilities = tuple(c for c in caps_raw if isinstance(c, str))

    config = data.get("config", {})
    if not isinstance(config, dict):
        config = {}

    return ModuleInfo(
        name=name,
        version=version,
        description=description,
        capabilities=capabilities,
        config=config,
    )
