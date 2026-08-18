from __future__ import annotations

import hashlib
import json
import shutil
from collections import Counter
from pathlib import Path

from .conflicts import find_conflicts
from .coverage import build_coverage, load_targets
from .io import expand_jsonl_paths, read_records
from .taxonomy import (
    load_source_manifest,
    policy_version,
    repo_root,
    source_manifest_version,
    taxonomy_version,
)
from .validation import validate_records


RELEASE_FORBIDDEN_STATUSES = {"candidate", "quarantine"}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def build_release(*, version: str, data_paths: list[str], out_root: str | Path) -> dict:
    root = repo_root()
    output_root = Path(out_root)
    if output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True)

    record_files = expand_jsonl_paths(data_paths)
    records = read_records(record_files)
    validation_errors = validate_records(records)
    if validation_errors:
        raise ValueError("release validation failed: " + "; ".join(validation_errors))

    forbidden = sorted(
        {
            record.get("id")
            for record in records
            if record.get("status") in RELEASE_FORBIDDEN_STATUSES
            or record.get("split") in {"candidate", "judge_gold"}
        }
    )
    if forbidden:
        raise ValueError(f"release data contains non-release records: {forbidden}")

    conflicts = find_conflicts(records, mode="unit")
    if conflicts:
        raise ValueError("release data has unresolved conflicts")

    coverage = build_coverage(
        records, load_targets(root / "taxonomy" / "coverage_targets.json")
    )
    manifest_source = load_source_manifest()

    for relative in ("taxonomy", "schemas"):
        shutil.copytree(root / relative, output_root / relative)
    for jsonl_path in record_files:
        source = Path(jsonl_path)
        rel = source.relative_to(root)
        target = output_root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

    _write_json(output_root / "coverage.json", coverage)
    _write_json(output_root / "conflicts.json", conflicts)

    counts = {
        "records": len(records),
        "families": len({record.get("family_id") for record in records}),
        "languages": dict(
            sorted(Counter(record.get("language") for record in records).items())
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

    manifest = {
        "benchmark_version": version,
        "schema_version": records[0].get("schema_version") if records else "0",
        "taxonomy_version": taxonomy_version(),
        "policy_version": policy_version(),
        "source_manifest_version": source_manifest_version(),
        "source_manifest_revision": manifest_source.get("version"),
        "counts": counts,
        "file_hashes": {},
        "scoring_modes": ["canonical", "accepted"],
    }

    (output_root / "RELEASE.md").write_text(
        "# Spokenform Gold Release\n\n"
        f"- version: {version}\n"
        f"- records: {counts['records']}\n"
        f"- schema_version: {manifest['schema_version']}\n"
        f"- taxonomy_version: {manifest['taxonomy_version']}\n"
        f"- policy_version: {manifest['policy_version']}\n",
        encoding="utf-8",
    )

    manifest_path = output_root / "manifest.json"
    for _ in range(2):
        manifest["file_hashes"] = {}
        for path in sorted(output_root.rglob("*")):
            if path.is_file() and path != manifest_path and path.name != "SHA256SUMS":
                manifest["file_hashes"][str(path.relative_to(output_root))] = (
                    _sha256_file(path)
                )
        _write_json(manifest_path, manifest)

    checksum_lines = []
    for path in sorted(output_root.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS":
            checksum_lines.append(
                f"{_sha256_file(path)}  {path.relative_to(output_root)}"
            )
    sha_path = output_root / "SHA256SUMS"
    sha_path.write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")
    _write_json(output_root / "manifest.json", manifest)
    return manifest
