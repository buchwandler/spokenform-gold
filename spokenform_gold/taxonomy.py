from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PACKAGE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_ROOT.parent


def repo_root() -> Path:
    return REPO_ROOT


def _load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_categories(path: str | Path | None = None) -> dict[str, Any]:
    target = Path(path) if path else repo_root() / "taxonomy" / "categories.json"
    return _load_json(target)


def load_policies(path: str | Path | None = None) -> dict[str, Any]:
    target = Path(path) if path else repo_root() / "taxonomy" / "policies.json"
    return _load_json(target)


def load_ambiguity_families(path: str | Path | None = None) -> dict[str, Any]:
    target = (
        Path(path) if path else repo_root() / "taxonomy" / "ambiguity_families.json"
    )
    return _load_json(target)


def load_mapping(source_name: str, path: str | Path | None = None) -> dict[str, Any]:
    target = (
        Path(path)
        if path
        else repo_root() / "taxonomy" / "mappings" / f"{source_name}.json"
    )
    return _load_json(target)


def load_source_manifest(path: str | Path | None = None) -> dict[str, Any]:
    target = Path(path) if path else repo_root() / "sources" / "manifest.json"
    return _load_json(target)


def load_release_maturity_profiles(path: str | Path | None = None) -> dict[str, Any]:
    target = (
        Path(path)
        if path
        else repo_root() / "taxonomy" / "release_maturity_profiles.json"
    )
    return _load_json(target)


def categories_set(path: str | Path | None = None) -> set[str]:
    return set(load_categories(path).get("categories", []))


def policies_map(path: str | Path | None = None) -> dict[str, Any]:
    return load_policies(path).get("policies", {})


def ambiguity_map(path: str | Path | None = None) -> dict[str, Any]:
    return load_ambiguity_families(path).get("families", {})


def source_manifest_map(path: str | Path | None = None) -> dict[str, dict[str, Any]]:
    data = load_source_manifest(path)
    return {entry["name"]: entry for entry in data.get("sources", [])}


def taxonomy_version(path: str | Path | None = None) -> str:
    return str(load_categories(path).get("version", "0"))


def policy_version(path: str | Path | None = None) -> str:
    return str(load_policies(path).get("version", "0"))


def source_manifest_version(path: str | Path | None = None) -> str:
    return str(load_source_manifest(path).get("version", "0"))


def release_maturity_profiles(path: str | Path | None = None) -> dict[str, Any]:
    return load_release_maturity_profiles(path).get("profiles", {})
