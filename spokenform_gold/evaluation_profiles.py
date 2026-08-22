from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from .taxonomy import repo_root

DEFAULT_REGISTRY_PATH = repo_root() / "taxonomy" / "evaluation_profiles.json"


def _canonical_json(payload: Any) -> bytes:
    return json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def registry_hash(registry: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(registry)).hexdigest()


def profile_hash(profile: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(profile)).hexdigest()


def load_registry(path: str | Path | None = None) -> dict[str, Any]:
    target = Path(path) if path else DEFAULT_REGISTRY_PATH
    registry = json.loads(target.read_text(encoding="utf-8"))
    validate_registry(registry)
    return registry


def validate_registry(registry: dict[str, Any]) -> None:
    if not isinstance(registry, dict):
        raise TypeError("evaluation profile registry must be an object")
    version = registry.get("version")
    profiles = registry.get("profiles")
    if not isinstance(version, str) or not version.strip():
        raise ValueError("evaluation profile registry requires a version")
    if not isinstance(profiles, dict) or not profiles:
        raise ValueError("evaluation profile registry requires profiles")
    for name, profile in profiles.items():
        if not isinstance(name, str) or not name:
            raise ValueError("evaluation profile names must be non-empty strings")
        if not isinstance(profile, dict):
            raise TypeError(f"profile {name!r} must be an object")
        if profile.get("kind") not in {"canonical", "control"}:
            raise ValueError(f"profile {name!r} has invalid kind")
        if not isinstance(profile.get("policy_expansion"), bool):
            raise TypeError(f"profile {name!r} requires policy_expansion")
        if not isinstance(profile.get("prepare_kwargs"), dict):
            raise TypeError(f"profile {name!r} requires prepare_kwargs")
        parent = profile.get("extends")
        if parent is not None and (
            not isinstance(parent, str) or parent not in profiles
        ):
            raise ValueError(f"profile {name!r} extends unknown profile {parent!r}")
    for name in profiles:
        _resolve_profile(registry, name, stack=[])


def _resolve_profile(
    registry: dict[str, Any], name: str, *, stack: list[str]
) -> dict[str, Any]:
    if name in stack:
        cycle = " -> ".join([*stack, name])
        raise ValueError(f"evaluation profile inheritance cycle: {cycle}")
    raw = registry["profiles"][name]
    parent_name = raw.get("extends")
    if parent_name is None:
        resolved: dict[str, Any] = {}
    else:
        resolved = _resolve_profile(registry, parent_name, stack=[*stack, name])
    resolved = copy.deepcopy(resolved)
    resolved.update(
        {key: value for key, value in raw.items() if key != "prepare_kwargs"}
    )
    kwargs = dict(resolved.get("prepare_kwargs", {}))
    kwargs.update(raw.get("prepare_kwargs", {}))
    resolved["prepare_kwargs"] = kwargs
    resolved["name"] = name
    return resolved


def resolve_profile(name: str, path: str | Path | None = None) -> dict[str, Any]:
    registry = load_registry(path)
    try:
        resolved = _resolve_profile(registry, name, stack=[])
    except KeyError as exc:
        raise ValueError(f"unsupported profile {name!r}") from exc
    return resolved


def profile_metadata(name: str, path: str | Path | None = None) -> dict[str, Any]:
    registry = load_registry(path)
    profile = resolve_profile(name, path)
    return {
        "profile_id": name,
        "profile_hash": profile_hash(profile),
        "registry_version": registry["version"],
        "registry_hash": registry_hash(registry),
        "policy_expansion": profile["policy_expansion"],
    }
