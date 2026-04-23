"""Smoke tests for the dev-modules reader."""

from __future__ import annotations

from pathlib import Path

import pytest

from dev_modules import (
    ModuleInfo,
    has_capability,
    installed_modules,
    is_installed,
    load_module,
)
from dev_modules.schema import ManifestError, parse_manifest


def _write_module(root: Path, name: str, body: str) -> None:
    d = root / ".modules" / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "module.toml").write_text(body)


def test_installed_modules_enumerates(tmp_path: Path) -> None:
    _write_module(
        tmp_path,
        "workshop",
        """
schema_version = 1
name = "workshop"
version = "0.3.1"
capabilities = ["workshop.journal.read"]
""",
    )
    _write_module(
        tmp_path,
        "telegram",
        """
schema_version = 1
name = "telegram"
version = "1.2.0"
""",
    )

    mods = installed_modules(tmp_path)
    assert set(mods.keys()) == {"workshop", "telegram"}
    assert mods["workshop"].version == "0.3.1"
    assert "workshop.journal.read" in mods["workshop"].capabilities


def test_is_installed_and_has_capability(tmp_path: Path) -> None:
    _write_module(
        tmp_path,
        "telegram",
        """
schema_version = 1
name = "telegram"
version = "1.2.0"
capabilities = ["telegram.notify"]
""",
    )

    assert is_installed("telegram", tmp_path)
    assert not is_installed("nope", tmp_path)

    assert has_capability("telegram", "telegram.notify", tmp_path)
    assert not has_capability("telegram", "telegram.inline", tmp_path)
    assert not has_capability("nope", "anything", tmp_path)


def test_invalid_manifest_skipped(tmp_path: Path) -> None:
    # Valid module
    _write_module(
        tmp_path,
        "good",
        """
schema_version = 1
name = "good"
version = "0.1.0"
""",
    )
    # Wrong schema version — should be skipped
    _write_module(
        tmp_path,
        "bad_version",
        """
schema_version = 99
name = "bad_version"
version = "0.1.0"
""",
    )
    # Name mismatch — should be skipped
    _write_module(
        tmp_path,
        "bad_name",
        """
schema_version = 1
name = "something_else"
version = "0.1.0"
""",
    )
    # Malformed TOML — should be skipped
    (tmp_path / ".modules" / "bad_toml").mkdir(parents=True)
    (tmp_path / ".modules" / "bad_toml" / "module.toml").write_text(
        "not valid [[[ toml"
    )

    mods = installed_modules(tmp_path)
    assert set(mods.keys()) == {"good"}


def test_directory_without_manifest_skipped(tmp_path: Path) -> None:
    (tmp_path / ".modules" / "stale").mkdir(parents=True)
    assert installed_modules(tmp_path) == {}


def test_no_modules_dir_returns_empty(tmp_path: Path) -> None:
    assert installed_modules(tmp_path) == {}
    assert not is_installed("anything", tmp_path)


def test_walks_up_to_find_modules_dir(tmp_path: Path) -> None:
    _write_module(
        tmp_path,
        "workshop",
        """
schema_version = 1
name = "workshop"
version = "0.1.0"
""",
    )
    deep = tmp_path / "a" / "b" / "c"
    deep.mkdir(parents=True)

    mods = installed_modules(deep)
    assert "workshop" in mods


def test_load_module_raises_on_invalid(tmp_path: Path) -> None:
    _write_module(
        tmp_path,
        "bad",
        """
schema_version = 99
name = "bad"
version = "0.1.0"
""",
    )
    with pytest.raises(ManifestError):
        load_module(tmp_path / ".modules" / "bad")


def test_parse_manifest_validates_name() -> None:
    with pytest.raises(ManifestError):
        parse_manifest(
            {"schema_version": 1, "name": "a", "version": "0.1.0"},
            expected_name="b",
        )


def test_module_info_has_capability() -> None:
    info = ModuleInfo(
        name="x",
        version="0.1.0",
        capabilities=("x.a", "x.b"),
    )
    assert info.has_capability("x.a")
    assert not info.has_capability("x.c")
