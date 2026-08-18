from __future__ import annotations

from pathlib import Path

from .io import read_json, sha256_file


REDISTRIBUTION_STATUSES = {
    "allowed",
    "metadata_only",
    "importer_only",
    "review_required",
    "not_redistributable",
}
PLACEHOLDER_MARKERS = ("example.invalid", "fixture-managed", "-fixture")


def has_placeholder_metadata(value: object) -> bool:
    if not isinstance(value, str):
        return False
    lowered = value.casefold()
    return any(marker in lowered for marker in PLACEHOLDER_MARKERS)


def validate_source_manifest(
    manifest: dict,
    *,
    repo_root: str | Path,
    require_release_ready: bool = False,
) -> list[str]:
    errors: list[str] = []
    version = manifest.get("version")
    if not isinstance(version, str) or not version.strip():
        errors.append("source manifest: version is required")

    sources = manifest.get("sources")
    if not isinstance(sources, list) or not sources:
        errors.append("source manifest: sources must be a non-empty list")
        return errors

    root = Path(repo_root)
    seen_names: set[str] = set()
    for index, source in enumerate(sources, 1):
        prefix = f"source manifest source[{index}]"
        if not isinstance(source, dict):
            errors.append(f"{prefix}: entry must be an object")
            continue
        name = source.get("name")
        if not isinstance(name, str) or not name.strip():
            errors.append(f"{prefix}: name is required")
            continue
        prefix = f"source manifest {name}"
        if name in seen_names:
            errors.append(f"{prefix}: duplicate source entry")
        seen_names.add(name)

        for key in ("revision", "source_url", "license"):
            value = source.get(key)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"{prefix}: {key} is required")
        redistribution_status = source.get("redistribution_status")
        if redistribution_status not in REDISTRIBUTION_STATUSES:
            errors.append(f"{prefix}: invalid redistribution_status")
        release_ready = source.get("release_ready")
        if not isinstance(release_ready, bool):
            errors.append(f"{prefix}: release_ready must be boolean")
        elif require_release_ready and not release_ready:
            errors.append(f"{prefix}: release_ready must be true")

        for key in ("revision", "source_url"):
            value = source.get(key)
            if has_placeholder_metadata(value):
                errors.append(f"{prefix}: {key} contains placeholder metadata")

        files = source.get("files")
        if not isinstance(files, list) or not files:
            errors.append(f"{prefix}: files must be a non-empty list")
            continue
        for file_index, entry in enumerate(files, 1):
            file_prefix = f"{prefix} file[{file_index}]"
            if not isinstance(entry, dict):
                errors.append(f"{file_prefix}: entry must be an object")
                continue
            file_path = entry.get("path")
            expected_hash = entry.get("sha256")
            if not isinstance(file_path, str) or not file_path.strip():
                errors.append(f"{file_prefix}: path is required")
                continue
            if not isinstance(expected_hash, str) or len(expected_hash) != 64:
                errors.append(
                    f"{file_prefix}: sha256 must be a 64-character hex digest"
                )
                continue
            if has_placeholder_metadata(expected_hash):
                errors.append(f"{file_prefix}: sha256 contains placeholder metadata")
                continue
            target = root / file_path
            if not target.exists():
                errors.append(f"{file_prefix}: path does not exist: {file_path}")
                continue
            actual_hash = sha256_file(target)
            if actual_hash != expected_hash:
                errors.append(
                    f"{file_prefix}: sha256 mismatch for {file_path}: expected {expected_hash} got {actual_hash}"
                )

    return errors


def load_and_validate_source_manifest(
    path: str | Path,
    *,
    repo_root: str | Path,
    require_release_ready: bool = False,
) -> dict:
    manifest = read_json(path)
    errors = validate_source_manifest(
        manifest, repo_root=repo_root, require_release_ready=require_release_ready
    )
    if errors:
        raise ValueError("; ".join(errors))
    return manifest
