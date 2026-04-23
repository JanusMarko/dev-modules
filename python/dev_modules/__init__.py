"""dev-modules: per-repo service discovery for dev-tool integrations.

Each module drops a manifest at ``<repo>/.modules/<name>/module.toml``.
Consumers call ``installed_modules()`` / ``is_installed(name)`` /
``has_capability(name, cap)`` to adapt their behavior.

See SPEC.md for the manifest schema.
"""

from .reader import has_capability, installed_modules, is_installed, load_module
from .schema import SCHEMA_VERSION, ModuleInfo

__all__ = [
    "SCHEMA_VERSION",
    "ModuleInfo",
    "has_capability",
    "installed_modules",
    "is_installed",
    "load_module",
]

__version__ = "0.1.0"
