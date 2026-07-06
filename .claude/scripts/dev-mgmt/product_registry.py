"""Workshop Lite product-local registry and conformance records.

WL1-A keeps these records repo-local and file-backed. The helpers here validate
the product registry, generated consumer drops, optional aliases, and the
conformance record without importing or shelling to any live Parley runtime.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping


PRODUCT_ID = "workshop-lite"
REGISTRY_ROOT = Path(".workshop-lite") / "registry"
REGISTRY_RECORD = REGISTRY_ROOT / "registry.json"
STANDARDS_ROOT = Path(".workshop-lite") / "standards"
CONFORMANCE_RECORD = STANDARDS_ROOT / "conformance.json"
ASSERTED_NOT_MEASURED = "asserted-not-measured"
CONSUMER_CONTRACT = {
    "plan_of_record": REGISTRY_RECORD.as_posix(),
    "generated_drop_policy": "derived-only",
    "agents_skills_policy": "optional-secondary-named-consumers-only",
    "alias_policy": "gate-owner-plus-cto-cos",
}
_CONFORMANCE_STATUSES = {ASSERTED_NOT_MEASURED, "measured"}


class ProductRegistryError(ValueError):
    """Raised when a product-local registry record is incomplete or unsafe."""


def _rel_path(value: object, *, field: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ProductRegistryError(f"{field}: must be a non-empty relative path")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise ProductRegistryError(f"{field}: must stay inside the product repo")
    return path


def _non_empty_string(data: Mapping[str, object], field: str) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ProductRegistryError(f"{field}: required non-empty string")
    return value


def registry_record_path(repo_root: str | Path | None = None) -> Path:
    repo = Path(repo_root) if repo_root is not None else Path.cwd()
    return repo / REGISTRY_RECORD


def conformance_record_path(repo_root: str | Path | None = None) -> Path:
    repo = Path(repo_root) if repo_root is not None else Path.cwd()
    return repo / CONFORMANCE_RECORD


def read_json_record(path: str | Path) -> dict[str, object]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json_record(path: str | Path, data: Mapping[str, object]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target


def validate_registry_record(data: Mapping[str, object]) -> None:
    """Validate the WL product-local registry record.

    The registry source must be the canonical WL-local registry JSON. Generated
    consumer outputs are permitted only when each output is explicitly marked
    derived, so consumer drops cannot become the plan of record.
    """
    _require_product_identity(data)
    if data.get("registry_source") != REGISTRY_RECORD.as_posix():
        raise ProductRegistryError(
            f"registry_source: must be {REGISTRY_RECORD.as_posix()}"
        )
    _non_empty_string(data, "registry_owner")
    _non_empty_string(data, "evidence_ref")
    _validate_consumer_contract(data.get("consumer_contract"))
    _validate_generated_outputs(data.get("generated_outputs", []))
    _validate_aliases(data.get("aliases", []))


def validate_conformance_record(data: Mapping[str, object]) -> None:
    """Validate the product-local conformance record.

    Measured conformance is accepted only with an explicit product-local evidence
    gate, so the status cannot be flipped by label alone.
    """
    _require_product_identity(data)
    _non_empty_string(data, "standard_id")
    _non_empty_string(data, "conformed_standard_version")
    _non_empty_string(data, "source_ref")
    _non_empty_string(data, "evidence_ref")
    status = data.get("status")
    if status not in _CONFORMANCE_STATUSES:
        raise ProductRegistryError(f"status: unsupported conformance status {status!r}")
    if status == "measured" and not isinstance(data.get("evidence"), Mapping):
        raise ProductRegistryError(
            "evidence: measured conformance requires product-local evidence"
        )


def _require_product_identity(data: Mapping[str, object]) -> None:
    if data.get("product_id") != PRODUCT_ID:
        raise ProductRegistryError(f"product_id: must be {PRODUCT_ID}")
    _non_empty_string(data, "product_version")


def _validate_generated_outputs(outputs: object) -> None:
    if not isinstance(outputs, list):
        raise ProductRegistryError("generated_outputs: must be a list")
    for index, output in enumerate(outputs):
        if not isinstance(output, Mapping):
            raise ProductRegistryError(f"generated_outputs[{index}]: must be an object")
        path = _rel_path(output.get("path"), field=f"generated_outputs[{index}].path")
        if output.get("derived") is not True:
            raise ProductRegistryError(
                f"generated_outputs[{index}].derived: must be true"
            )
        if output.get("source") != REGISTRY_RECORD.as_posix():
            raise ProductRegistryError(
                f"generated_outputs[{index}].source: must be {REGISTRY_RECORD.as_posix()}"
            )
        _non_empty_string(output, "consumer")
        if output.get("mode") != "optional-secondary":
            raise ProductRegistryError(
                f"generated_outputs[{index}].mode: must be optional-secondary"
            )
        if path == REGISTRY_RECORD or path.is_relative_to(REGISTRY_ROOT):
            raise ProductRegistryError(
                f"generated_outputs[{index}].path: cannot be authoritative registry"
            )


def _validate_consumer_contract(contract: object) -> None:
    if not isinstance(contract, Mapping):
        raise ProductRegistryError("consumer_contract: must be an object")
    for field, expected in CONSUMER_CONTRACT.items():
        if contract.get(field) != expected:
            raise ProductRegistryError(
                f"consumer_contract.{field}: must be {expected}"
            )


def _validate_aliases(aliases: object) -> None:
    if not isinstance(aliases, list):
        raise ProductRegistryError("aliases: must be a list")
    for index, alias in enumerate(aliases):
        if not isinstance(alias, Mapping):
            raise ProductRegistryError(f"aliases[{index}]: must be an object")
        alias_path = _rel_path(alias.get("path"), field=f"aliases[{index}].path")
        if alias_path == REGISTRY_RECORD or alias_path.is_relative_to(REGISTRY_ROOT):
            raise ProductRegistryError(
                f"aliases[{index}].path: cannot alias the authoritative registry"
            )
        _non_empty_string(alias, "purpose")
        _non_empty_string(alias, "gate_owner_acceptance_ref")
        _non_empty_string(alias, "cto_cos_acceptance_ref")


def load_and_validate_registry(repo_root: str | Path | None = None) -> dict[str, object]:
    data = read_json_record(registry_record_path(repo_root))
    validate_registry_record(data)
    return data


def load_and_validate_conformance(repo_root: str | Path | None = None) -> dict[str, object]:
    data = read_json_record(conformance_record_path(repo_root))
    validate_conformance_record(data)
    return data
