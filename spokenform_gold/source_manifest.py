from __future__ import annotations

from pathlib import Path

from .io import read_json, sha256_file

SOURCE_KINDS = {"curated", "upstream", "projection_cache"}
REDISTRIBUTION_STATUSES = {
    "allowed",
    "metadata_only",
    "importer_only",
    "review_required",
    "not_redistributable",
}
MATERIALIZATION_POLICIES = {
    "embedded_public",
    "external_ref_only",
    "importer_only",
    "review_required",
}
PLACEHOLDER_MARKERS = ("example.invalid", "fixture-managed", "-fixture")


def has_placeholder_metadata(value: object) -> bool:
    if not isinstance(value, str):
        return False
    lowered = value.casefold()
    return any(marker in lowered for marker in PLACEHOLDER_MARKERS)


def normalize_materialization_policy(source: dict) -> str:
    policy = source.get("materialization_policy")
    if policy in MATERIALIZATION_POLICIES:
        return str(policy)
    redistribution_status = source.get("redistribution_status")
    if redistribution_status == "allowed":
        return "embedded_public"
    if redistribution_status in {"metadata_only", "not_redistributable"}:
        return "external_ref_only"
    if redistribution_status == "importer_only":
        return "importer_only"
    return "review_required"


def filter_source_manifest(manifest: dict, source_names: set[str] | None) -> dict:
    if not source_names:
        return manifest
    return {
        **manifest,
        "sources": [
            entry
            for entry in manifest.get("sources", [])
            if entry.get("name") in source_names
        ],
    }


def referenced_source_names(records: list[dict]) -> set[str]:
    names: set[str] = set()
    for record in records:
        source = record.get("source")
        if isinstance(source, dict):
            benchmark = source.get("benchmark")
            if isinstance(benchmark, str) and benchmark:
                names.add(benchmark)
    return names


def validate_source_manifest(
    manifest: dict,
    *,
    repo_root: str | Path,
    require_release_ready: bool = False,
    source_names: set[str] | None = None,
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
        if source_names is not None and name not in source_names:
            continue

        for key in ("revision", "source_url", "license"):
            value = source.get(key)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"{prefix}: {key} is required")
        license_id = source.get("license_id")
        if not isinstance(license_id, str) or not license_id.strip():
            errors.append(f"{prefix}: license_id is required")
        license_scope = source.get("license_scope")
        if not isinstance(license_scope, str) or not license_scope.strip():
            errors.append(f"{prefix}: license_scope is required")
        kind = source.get("kind")
        if kind is not None and kind not in SOURCE_KINDS:
            errors.append(f"{prefix}: invalid kind")
        redistribution_status = source.get("redistribution_status")
        if redistribution_status not in REDISTRIBUTION_STATUSES:
            errors.append(f"{prefix}: invalid redistribution_status")
        materialization_policy = source.get("materialization_policy")
        if (
            materialization_policy is not None
            and materialization_policy not in MATERIALIZATION_POLICIES
        ):
            errors.append(f"{prefix}: invalid materialization_policy")
        release_ready = source.get("release_ready")
        if not isinstance(release_ready, bool):
            errors.append(f"{prefix}: release_ready must be boolean")
        elif require_release_ready and not release_ready:
            errors.append(f"{prefix}: release_ready must be true")

        for key in ("revision", "source_url"):
            value = source.get(key)
            if has_placeholder_metadata(value):
                errors.append(f"{prefix}: {key} contains placeholder metadata")

        parent_source = source.get("parent_source")
        if parent_source is not None and (
            not isinstance(parent_source, str) or not parent_source.strip()
        ):
            errors.append(
                f"{prefix}: parent_source must be non-empty string when present"
            )

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

        upstream_files = source.get("upstream_files")
        if upstream_files is not None:
            if not isinstance(upstream_files, list) or not upstream_files:
                errors.append(
                    f"{prefix}: upstream_files must be a non-empty list when present"
                )
            else:
                for file_index, entry in enumerate(upstream_files, 1):
                    file_prefix = f"{prefix} upstream_files[{file_index}]"
                    if not isinstance(entry, dict):
                        errors.append(f"{file_prefix}: entry must be an object")
                        continue
                    file_path = entry.get("path")
                    if not isinstance(file_path, str) or not file_path.strip():
                        errors.append(f"{file_prefix}: path is required")
                    role = entry.get("role")
                    if role is not None and (
                        not isinstance(role, str) or not role.strip()
                    ):
                        errors.append(
                            f"{file_prefix}: role must be non-empty string when present"
                        )

        policy = normalize_materialization_policy(source)
        if redistribution_status == "allowed" and policy != "embedded_public":
            errors.append(
                f"{prefix}: allowed redistribution requires embedded_public materialization_policy"
            )
        if (
            redistribution_status in {"metadata_only", "not_redistributable"}
            and policy == "embedded_public"
        ):
            errors.append(
                f"{prefix}: restricted redistribution cannot use embedded_public materialization_policy"
            )
        if redistribution_status == "importer_only" and policy != "importer_only":
            errors.append(
                f"{prefix}: importer_only redistribution requires importer_only materialization_policy"
            )

    if source_names is not None:
        missing = sorted(source_names - seen_names)
        if missing:
            errors.append(f"source manifest: missing referenced sources {missing}")

    return errors


def load_and_validate_source_manifest(
    path: str | Path,
    *,
    repo_root: str | Path,
    require_release_ready: bool = False,
    source_names: set[str] | None = None,
    filter_to_source_names: bool = False,
) -> dict:
    manifest = read_json(path)
    errors = validate_source_manifest(
        manifest,
        repo_root=repo_root,
        require_release_ready=require_release_ready,
        source_names=source_names,
    )
    if errors:
        raise ValueError("; ".join(errors))
    if filter_to_source_names:
        return filter_source_manifest(manifest, source_names)
    return manifest
