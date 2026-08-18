from __future__ import annotations

import json
import shutil
from collections import Counter
from pathlib import Path

from .conflicts import find_conflicts
from .coverage import build_coverage, load_targets
from .io import expand_jsonl_paths, read_records, sha256_file
from .source_manifest import load_and_validate_source_manifest
from .taxonomy import policy_version, repo_root, taxonomy_version
from .validation import validate_records


RELEASE_FORBIDDEN_STATUSES = {"quarantine"}
RELEASE_MATURITIES = {"experimental", "candidate", "stable"}


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
) -> dict:
    if maturity not in RELEASE_MATURITIES:
        raise ValueError(
            f"release maturity must be one of {sorted(RELEASE_MATURITIES)}"
        )

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
    manifest_source_path = (
        Path(source_manifest_path)
        if source_manifest_path
        else root / "sources" / "manifest.json"
    )
    manifest_source = load_and_validate_source_manifest(
        manifest_source_path,
        repo_root=root,
        require_release_ready=maturity == "stable",
    )

    record_files = expand_jsonl_paths(data_paths)
    records = read_records(record_files)
    validation_errors = validate_records(records)
    if validation_errors:
        raise ValueError("release validation failed: " + "; ".join(validation_errors))

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

    coverage = build_coverage(
        records, load_targets(root / "taxonomy" / "coverage_targets.json")
    )
    if maturity == "stable" and coverage_profile == "stable":
        blocking = [
            gap
            for gap in coverage.get("gaps", [])
            if gap.get("category")
            in {
                "date",
                "time",
                "decimal",
                "fraction",
                "currency",
                "identifier",
                "version",
                "ip_address",
            }
        ]
        if blocking:
            raise ValueError("stable release coverage gate failed")

    for relative in ("taxonomy", "schemas"):
        shutil.copytree(root / relative, output_root / relative)
    shutil.copytree(root / "sources", output_root / "sources")
    (output_root / "splits").mkdir(parents=True, exist_ok=True)
    shutil.copy2(registry_source, output_root / "splits" / registry_source.name)
    for jsonl_path in record_files:
        _copy_file(root, output_root, Path(jsonl_path))

    _write_json(output_root / "coverage.json", coverage)
    _write_json(output_root / "conflicts.json", conflicts)

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
        "counts": counts,
        "split_registry": f"splits/{registry_source.name}",
        "source_manifest": "sources/manifest.json",
        "source_integrity": {
            "release_ready": all(
                source.get("release_ready", False)
                for source in manifest_source.get("sources", [])
            ),
            "source_count": len(manifest_source.get("sources", [])),
        },
        "scoring_modes": ["canonical", "accepted"],
        "file_hashes": {},
    }

    manifest_path = output_root / "manifest.json"
    for _ in range(2):
        manifest["file_hashes"] = {}
        for path in sorted(output_root.rglob("*")):
            if path.is_file() and path.name not in {"manifest.json", "SHA256SUMS"}:
                manifest["file_hashes"][str(path.relative_to(output_root))] = (
                    sha256_file(path)
                )
        _write_json(manifest_path, manifest)

    checksum_lines = []
    for path in sorted(output_root.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS":
            checksum_lines.append(
                f"{sha256_file(path)}  {path.relative_to(output_root)}"
            )
    (output_root / "SHA256SUMS").write_text(
        "\n".join(checksum_lines) + "\n", encoding="utf-8"
    )
    return manifest
