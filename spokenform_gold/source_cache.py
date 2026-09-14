"""Shared acquisition and verification for pinned Gold upstream sources."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SourceDefinition:
    name: str
    source_url: str
    revision: str
    license: str
    source_names: tuple[str, ...]
    expected_paths: tuple[str, ...]

    @property
    def restricted(self) -> bool:
        return not self.license.casefold().startswith(("apache", "mit", "bsd", "cc0"))

    def path(self, cache_root: str | Path) -> Path:
        return Path(cache_root) / self.name / self.revision


def load_source_definitions(
    repo_root: str | Path, *, source_names: set[str] | None = None
) -> tuple[SourceDefinition, ...]:
    manifest_path = Path(repo_root) / "sources" / "manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    grouped: dict[tuple[str, str], dict[str, object]] = {}
    for entry in payload.get("sources", []):
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        url = entry.get("source_url")
        revision = entry.get("revision")
        if not all(isinstance(value, str) and value for value in (name, url, revision)):
            continue
        if entry.get("materialization_policy") not in {
            "external_ref_only",
            "review_required",
        }:
            continue
        parent = entry.get("parent_source")
        canonical = parent if isinstance(parent, str) and parent else name
        key = (url, revision)
        group = grouped.setdefault(
            key,
            {
                "name": canonical,
                "source_url": url,
                "revision": revision,
                "license": entry.get("license", ""),
                "source_names": set(),
                "expected_paths": set(),
            },
        )
        group["source_names"].add(name)
        group["source_names"].add(canonical)
        if isinstance(entry.get("license"), str) and entry["license"]:
            group["license"] = entry["license"]
        for upstream_file in entry.get("upstream_files", []):
            if isinstance(upstream_file, dict) and isinstance(
                upstream_file.get("path"), str
            ):
                group["expected_paths"].add(upstream_file["path"])
    definitions = tuple(
        SourceDefinition(
            name=str(group["name"]),
            source_url=str(group["source_url"]),
            revision=str(group["revision"]),
            license=str(group["license"]),
            source_names=tuple(sorted(group["source_names"])),
            expected_paths=tuple(sorted(group["expected_paths"])),
        )
        for group in sorted(grouped.values(), key=lambda value: str(value["name"]))
        if source_names is None or set(group["source_names"]) & source_names
    )
    return definitions


def _run_git(*args: str, cwd: Path | None = None) -> str:
    completed = subprocess.run(
        ("git", *args), cwd=cwd, check=True, capture_output=True, text=True
    )
    return completed.stdout.strip()


def verify_source(definition: SourceDefinition, checkout: str | Path) -> None:
    root = Path(checkout)
    if not (root / ".git").is_dir():
        raise ValueError(f"source cache is not a Git checkout: {root}")
    actual = _run_git("rev-parse", "HEAD", cwd=root)
    if actual != definition.revision:
        raise ValueError(
            f"source cache revision mismatch for {definition.name}: "
            f"expected {definition.revision}, got {actual}"
        )
    missing = []
    for relative in definition.expected_paths:
        matches = list(root.glob(relative)) if "*" in relative else [root / relative]
        if not matches or not any(path.exists() for path in matches):
            missing.append(relative)
    if missing:
        raise ValueError(
            f"source cache is missing {definition.name} files: {', '.join(missing)}"
        )


def _clone(definition: SourceDefinition, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{definition.name}-", dir=destination.parent)
    )
    try:
        _run_git("clone", definition.source_url, str(temporary))
        _run_git("checkout", definition.revision, cwd=temporary)
        verify_source(definition, temporary)
        if destination.exists():
            backup = destination.with_name(f".{destination.name}.previous")
            shutil.rmtree(backup, ignore_errors=True)
            destination.replace(backup)
            temporary.replace(destination)
            shutil.rmtree(backup, ignore_errors=True)
        else:
            temporary.replace(destination)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def ensure_source(
    definition: SourceDefinition,
    cache_root: str | Path,
    *,
    offline: bool = False,
    refresh: bool = False,
    accept_upstream_licenses: bool = False,
) -> Path:
    """Return a verified revision-scoped checkout, acquiring it when allowed."""
    destination = definition.path(cache_root)
    candidates = (destination, Path(cache_root) / definition.name)
    if not refresh:
        for candidate in candidates:
            if candidate.is_dir():
                try:
                    verify_source(definition, candidate)
                    return candidate
                except (OSError, ValueError):
                    continue
    if offline:
        raise FileNotFoundError(
            f"Offline source cache is missing or invalid for {definition.name}@{definition.revision}"
        )
    if definition.restricted and not accept_upstream_licenses:
        license_url = definition.source_url
        raise PermissionError(
            f"{definition.name} data is licensed {definition.license}; "
            f"pass --accept-upstream-licenses before downloading {license_url}."
        )
    _clone(definition, destination)
    return destination


def source_for_name(
    repo_root: str | Path, source_name: str, *, cache_root: str | Path
) -> SourceDefinition:
    for definition in load_source_definitions(repo_root, source_names={source_name}):
        if source_name in definition.source_names:
            return definition
    raise KeyError(f"source is not present in the release manifest: {source_name}")


__all__ = [
    "SourceDefinition",
    "ensure_source",
    "load_source_definitions",
    "source_for_name",
    "verify_source",
]
