from __future__ import annotations

import json
import shutil
from collections import Counter
from pathlib import Path

from .conflicts import find_conflicts
from .control_validation import validate_control_records
from .coverage import build_control_coverage, build_coverage, load_targets
from .evaluation_profiles import load_registry, registry_hash
from .gold_audit import audit_records
from .io import expand_jsonl_paths, read_records, sha256_file
from .source_manifest import (
    load_and_validate_source_manifest,
    normalize_materialization_policy,
    referenced_source_names,
)
from .splitting import load_split_registry
from .taxonomy import (
    policy_version,
    release_maturity_profiles,
    repo_root,
    taxonomy_version,
)
from .validation import validate_records

RELEASE_FORBIDDEN_STATUSES = {"quarantine"}
RELEASE_MATURITIES = frozenset(release_maturity_profiles())


def _write_json(path: Path, payload: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _copy_file(root: Path, output_root: Path, file_path: Path) -> None:
    rel = file_path.relative_to(root)
    target = output_root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(file_path, target)



def _repository_local_jsonl_files(
    root: Path, paths: list[str] | None, *, label: str
 ) -> list[Path]:
    files = expand_jsonl_paths(paths or [])
    root = root.resolve()
    for file_path in files:
        try:
            file_path.resolve().relative_to(root)
        except ValueError as exc:
            raise ValueError(
                f"{label} must be repository-local canonical data; "
                f"got {file_path}"
            ) from exc
    return files


def validate_release_split_registry(records: list[dict], registry: dict) -> list[str]:
    assignments = registry.get("families", {})
    if not isinstance(assignments, dict):
        return ["split registry families must be an object"]
    errors = []
    supported_splits = {"train", "dev", "test"}
    for record in records:
        record_id = record.get("id", "?")
        family_id = record.get("family_id")
        assigned = assignments.get(family_id)
        if not family_id or assigned is None:
            errors.append(f"record {record_id} family {family_id!r} is missing from split registry")
            continue
        if assigned not in supported_splits:
            errors.append(
                f"family {family_id!r} has unsupported registry split {assigned!r}"
            )
        if record.get("split") != assigned:
            errors.append(
                f"record {record_id} split {record.get('split')!r} does not match "
                f"registry assignment {assigned!r} for family {family_id!r}"
            )
    return errors


def _profile(name: str) -> dict:
    try:
        return release_maturity_profiles()[name]
    except KeyError as exc:
        raise ValueError(
            f"release maturity must be one of {sorted(RELEASE_MATURITIES)}"
        ) from exc


def _coverage_index(coverage: dict) -> dict[str, dict]:
    return {
        item["category"]: item
        for item in coverage.get("coverage", [])
        if isinstance(item, dict) and isinstance(item.get("category"), str)
    }


def _record_materialization(record: dict) -> str:
    materialization = record.get("materialization", "embedded")
    if materialization not in {"embedded", "external_ref"}:
        raise ValueError(
            f"release record {record.get('id', '?')} has invalid materialization {materialization!r}"
        )
    return materialization


def _enforce_source_materialization(records: list[dict], source_manifest: dict) -> None:
    source_map = {
        entry["name"]: entry
        for entry in source_manifest.get("sources", [])
        if isinstance(entry, dict) and isinstance(entry.get("name"), str)
    }
    errors: list[str] = []
    for record in records:
        source = record.get("source", {})
        benchmark = source.get("benchmark")
        if benchmark not in source_map:
            continue
        policy = normalize_materialization_policy(source_map[benchmark])
        materialization = _record_materialization(record)
        if materialization == "embedded" and policy != "embedded_public":
            errors.append(
                f"record {record.get('id', '?')} embeds source {benchmark!r} with policy {policy}"
            )
        if materialization == "external_ref" and policy not in {
            "embedded_public",
            "external_ref_only",
        }:
            errors.append(
                f"record {record.get('id', '?')} uses external_ref for source {benchmark!r} with policy {policy}"
            )
    if errors:
        raise ValueError("; ".join(errors))


def _enforce_maturity(
    *,
    profile_name: str,
    records: list[dict],
    coverage: dict,
    source_manifest: dict,
    control_coverage: dict | None = None,
) -> None:
    profile = _profile(profile_name)
    errors: list[str] = []
    required_controls = set(profile.get("required_control_suites", []))
    if required_controls:
        observed_controls = {
            item.get("control")
            for item in (control_coverage or {}).get("coverage", [])
        }
        missing_controls = sorted(required_controls - observed_controls)
        if missing_controls:
            errors.append(
                f"{profile_name} release is missing required control suites: {missing_controls}"
            )
        required_languages = set(profile.get("required_control_languages", []))
        observed_languages = {
            language
            for item in (control_coverage or {}).get("coverage", [])
            for language in item.get("languages", [])
        }
        missing_languages = sorted(required_languages - observed_languages)
        if missing_languages:
            errors.append(
                f"{profile_name} release is missing required control languages: {missing_languages}"
            )
    if profile.get("require_source_release_ready") and not all(
        source.get("release_ready", False)
        for source in source_manifest.get("sources", [])
    ):
        errors.append("release sources are not all marked release_ready")

    minimum_records = int(profile.get("minimum_records", 0))
    if len(records) < minimum_records:
        errors.append(
            f"{profile_name} release requires at least {minimum_records} records"
        )

    languages = {record.get("language") for record in records if record.get("language")}
    minimum_languages = int(profile.get("minimum_reviewed_languages", 0))
    if len(languages) < minimum_languages:
        errors.append(
            f"{profile_name} release requires at least {minimum_languages} languages"
        )

    negative_controls = sum(
        1 for record in records if record.get("status") == "no_change"
    )
    minimum_negatives = int(profile.get("minimum_negative_controls", 0))
    if negative_controls < minimum_negatives:
        errors.append(
            f"{profile_name} release requires at least {minimum_negatives} negative controls"
        )

    coverage_by_category = _coverage_index(coverage)
    observed_categories = {
        unit.get("category")
        for record in records
        for unit in record.get("units", [])
        if isinstance(unit, dict) and unit.get("category")
    }
    required_categories = set(profile.get("required_categories", []))
    missing_categories = sorted(required_categories - observed_categories)
    if missing_categories:
        errors.append(
            f"{profile_name} release is missing required categories: {missing_categories}"
        )

    for category, required_patterns in sorted(
        profile.get("required_patterns", {}).items()
    ):
        coverage_entry = coverage_by_category.get(category, {})
        patterns = coverage_entry.get("patterns", {})
        missing_patterns = [
            pattern
            for pattern in required_patterns
            if int(patterns.get(pattern, 0)) <= 0
        ]
        if missing_patterns:
            errors.append(
                f"{profile_name} release is missing required patterns for "
                f"{category}: {missing_patterns}"
            )

    if not profile.get("allow_coverage_gaps", True):
        allowed_gap_kinds = set(profile.get("allowed_gap_kinds", []))
        allowed_gap_categories = set(profile.get("allowed_gap_categories", []))
        blocking = [
            gap
            for gap in coverage.get("gaps", [])
            if not (
                gap.get("kind") in allowed_gap_kinds
                and (
                    not allowed_gap_categories
                    or gap.get("category") in allowed_gap_categories
                )
            )
        ]
        if blocking:
            errors.append(f"{profile_name} release does not allow coverage gaps")

    if errors:
        raise ValueError("; ".join(errors))


def _tracked_release_files(output_root: Path):
    for path in sorted(output_root.rglob("*")):
        if not path.is_file():
            continue
        relative = str(path.relative_to(output_root))
        if relative in {"manifest.json", "SHA256SUMS"}:
            continue
        yield relative, path


def _build_release_notes(
    *,
    version: str,
    maturity: str,
    counts: dict,
    source_manifest: dict,
) -> str:
    source_lines = [
        f"- {entry['name']}: {entry['revision']} ({entry['license']}, {entry['redistribution_status']})"
        for entry in source_manifest.get("sources", [])
    ]
    return (
        "# Spokenform Gold Release Notes\n\n"
        f"- version: {version}\n"
        f"- maturity: {maturity}\n"
        f"- records: {counts['records']}\n"
        f"- families: {counts['families']}\n"
        f"- languages: {', '.join(sorted(counts['languages'])) or 'none'}\n"
        f"- locales: {', '.join(sorted(counts['locales'])) or 'none'}\n\n"
        "## Source Manifest\n\n" + "\n".join(source_lines) + "\n"
    )


def build_release(
    *,
    version: str,
    data_paths: list[str],
    out_root: str | Path,
    maturity: str = "experimental",
    registry_path: str | Path | None = None,
    source_manifest_path: str | Path | None = None,
    coverage_profile: str = "none",
    control_paths: list[str] | None = None,
) -> dict:
    _profile(maturity)

    root = repo_root()
    output_root = Path(out_root)
    if output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True)

    registry_source = (
        Path(registry_path)
        if registry_path
        else root / "splits" / "family_assignments.json"
    )
    if not registry_source.exists():
        raise ValueError(f"missing split registry: {registry_source}")
    profile_registry_source = root / "taxonomy" / "evaluation_profiles.json"
    profile_registry = load_registry(profile_registry_source)
    record_files = _repository_local_jsonl_files(
        root, data_paths, label="release data"
    )
    records = read_records(record_files)
    validation_errors = validate_records(records)
    if validation_errors:
        raise ValueError("release validation failed: " + "; ".join(validation_errors))
    oracle_audit = audit_records(records, strict=maturity == "stable")
    if oracle_audit["errors"]:
        raise ValueError("release oracle audit failed: " + "; ".join(oracle_audit["errors"]))
    split_errors = validate_release_split_registry(
        records, load_split_registry(registry_source)
    )
    if split_errors:
        raise ValueError(
            "release split registry validation failed: " + "; ".join(split_errors)
        )
    control_files = _repository_local_jsonl_files(
        root, control_paths, label="release controls"
    )
    control_records = read_records(control_files)
    control_errors = validate_control_records(control_records) if control_records else []
    if control_errors:
        raise ValueError("control validation failed: " + "; ".join(control_errors))
    targets = load_targets(root / "taxonomy" / "coverage_targets.json")
    control_coverage = build_control_coverage(control_records, targets)

    forbidden = sorted(
        record.get("id")
        for record in records
        if record.get("status") in RELEASE_FORBIDDEN_STATUSES
        or record.get("split") in {"candidate", "judge_gold"}
    )
    if forbidden:
        raise ValueError(f"release data contains non-release records: {forbidden}")

    conflicts = find_conflicts(records, mode="unit")
    if conflicts:
        raise ValueError("release data has unresolved conflicts")

    manifest_source_path = (
        Path(source_manifest_path)
        if source_manifest_path
        else root / "sources" / "manifest.json"
    )
    referenced_sources = referenced_source_names(records)
    manifest_source = load_and_validate_source_manifest(
        manifest_source_path,
        repo_root=root,
        require_release_ready=maturity == "stable",
        source_names=referenced_sources,
        filter_to_source_names=True,
    )
    _enforce_source_materialization(records, manifest_source)

    coverage = build_coverage(records, targets)
    _enforce_maturity(
        profile_name=maturity,
        records=records,
        coverage=coverage,
        source_manifest=manifest_source,
        control_coverage=control_coverage,
    )

    for relative in ("taxonomy", "schemas"):
        shutil.copytree(root / relative, output_root / relative)
    (output_root / "sources").mkdir(parents=True, exist_ok=True)
    _write_json(output_root / "sources" / "manifest.json", manifest_source)
    (output_root / "splits").mkdir(parents=True, exist_ok=True)
    shutil.copy2(registry_source, output_root / "splits" / registry_source.name)
    for jsonl_path in record_files:
        _copy_file(root, output_root, Path(jsonl_path))
    for jsonl_path in control_files:
        _copy_file(root, output_root, Path(jsonl_path))

    _write_json(output_root / "coverage.json", coverage)
    _write_json(output_root / "control_coverage.json", control_coverage)
    _write_json(output_root / "conflicts.json", conflicts)
    _write_json(output_root / "oracle_audit.json", oracle_audit)

    counts = {
        "records": len(records),
        "families": len({record.get("family_id") for record in records}),
        "languages": dict(
            sorted(Counter(record.get("language") for record in records).items())
        ),
        "locales": dict(
            sorted(Counter(record.get("locale") for record in records).items())
        ),
        "statuses": dict(
            sorted(Counter(record.get("status") for record in records).items())
        ),
        "sources": dict(
            sorted(
                Counter(
                    record.get("source", {}).get("benchmark") for record in records
                ).items()
            )
        ),
    }

    notes = _build_release_notes(
        version=version,
        maturity=maturity,
        counts=counts,
        source_manifest=manifest_source,
    )
    (output_root / "RELEASE_NOTES.md").write_text(notes, encoding="utf-8")

    manifest = {
        "benchmark_version": version,
        "maturity": maturity,
        "schema_version": records[0].get("schema_version") if records else "0",
        "taxonomy_version": taxonomy_version(),
        "policy_version": policy_version(),
        "coverage_profile": coverage_profile,
        "source_manifest_version": manifest_source.get("version"),
        "profile_registry_version": profile_registry["version"],
        "profile_registry_hash": registry_hash(profile_registry),
        "counts": counts,
        "record_files": [str(path.relative_to(root)) for path in record_files],
        "control_files": [str(path.relative_to(root)) for path in control_files],
        "control_records": len(control_records),
        "split_registry": f"splits/{registry_source.name}",
        "source_manifest": "sources/manifest.json",
        "evaluation_profiles": "taxonomy/evaluation_profiles.json",
        "source_integrity": {
            "release_ready": all(
                source.get("release_ready", False)
                for source in manifest_source.get("sources", [])
            ),
            "source_count": len(manifest_source.get("sources", [])),
            "referenced_sources": sorted(referenced_sources),
        },
        "maturity_profile": _profile(maturity),
        "scoring_modes": ["canonical", "accepted"],
        "control_scoring": "control_coverage.json",
        "oracle_schema_version": "1.0.0",
        "comparison_profile": "sentence-exact-v1",
        "oracle_complete": oracle_audit["oracle_complete"],
        "oracle_audit": "oracle_audit.json",
        "legacy_oracle_records": oracle_audit["legacy_oracle_records"],
        "review_complete_records": oracle_audit["review_complete_records"],
        "file_hashes": {},
    }

    manifest_path = output_root / "manifest.json"
    for _ in range(2):
        manifest["file_hashes"] = {}
        for relative, path in _tracked_release_files(output_root):
            manifest["file_hashes"][relative] = sha256_file(path)
        _write_json(manifest_path, manifest)

    checksum_lines = []
    for relative, path in _tracked_release_files(output_root):
        checksum_lines.append(f"{sha256_file(path)}  {relative}")
    checksum_lines.append(
        f"{sha256_file(manifest_path)}  {manifest_path.relative_to(output_root)}"
    )
    (output_root / "SHA256SUMS").write_text(
        "\n".join(checksum_lines) + "\n", encoding="utf-8"
    )
    return manifest
