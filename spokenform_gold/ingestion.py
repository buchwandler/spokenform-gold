from __future__ import annotations

import subprocess
from collections.abc import Iterable
from pathlib import Path

from .conflicts import find_conflicts
from .coverage import build_coverage, load_targets
from .deduplication import deduplicate_candidates
from .exclusions import build_exclusion_analysis
from .families import suggest_families
from .importers import import_async, import_polynorm, import_proteno
from .io import read_records, write_json, write_jsonl
from .merge import merge_candidates
from .pool import build_candidate_pool_summary
from .ranking import build_candidate_ranking, export_review_batch
from .taxonomy import repo_root, source_manifest_map
from .validation import validate_records

SUPPORTED_SOURCES = ("async_tn", "polynorm", "proteno")
SUPPORTED_LANGUAGES = ("en", "de", "es", "fr", "it", "pt")


def _git_revision(path: Path) -> str | None:
    git_path = path / ".git"
    if not git_path.exists():
        return None
    try:
        completed = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ValueError(f"could not read Git revision for {path}: {exc}") from exc
    return completed.stdout.strip()


def _verify_checkout(path: Path, source_name: str, expected_revision: str) -> dict:
    if not path.is_dir():
        raise ValueError(f"missing source checkout: {path}")
    observed = _git_revision(path)
    if observed is not None and observed != expected_revision:
        raise ValueError(
            f"source {source_name} revision mismatch: expected {expected_revision}, got {observed}"
        )
    return {
        "source": source_name,
        "path": str(path),
        "expected_revision": expected_revision,
        "observed_revision": observed,
        "revision_verified": observed is None or observed == expected_revision,
        "git_metadata_available": observed is not None,
    }


def _write_shard(
    *,
    name: str,
    result,
    candidate_dir: Path,
    exclusion_dir: Path,
    report_dir: Path,
) -> tuple[Path, Path, dict, list[dict]]:
    candidate_path = candidate_dir / f"{name}.jsonl"
    exclusions_path = exclusion_dir / f"{name}.json"
    report_path = report_dir / f"{name}.json"
    write_jsonl(candidate_path, result.records)
    exclusions = []
    for item in result.exclusions:
        copied = dict(item)
        copied.setdefault("source", name)
        exclusions.append(copied)
    report = dict(result.diagnostics)
    report["source"] = name
    report["candidate_path"] = str(candidate_path)
    report["exclusions_path"] = str(exclusions_path)
    report["report_path"] = str(report_path)
    write_json(exclusions_path, exclusions)
    write_json(report_path, report)
    errors = validate_records(result.records)
    if errors:
        raise ValueError(f"generated {name} candidates are invalid: {'; '.join(errors)}")
    if not report.get("row_accounting_ok"):
        raise ValueError(f"{name} import failed row accounting")
    return candidate_path, exclusions_path, report, exclusions


def run_upstream_ingestion(
    source_cache: str | Path,
    work_root: str | Path,
    *,
    sources: Iterable[str] = SUPPORTED_SOURCES,
    languages: Iterable[str] = SUPPORTED_LANGUAGES,
    reviewed_paths: Iterable[str | Path] | None = None,
    targets_path: str | Path | None = None,
    batch_limit: int = 100,
) -> dict:
    source_cache = Path(source_cache)
    work_root = Path(work_root)
    requested_sources = set(sources)
    selected_sources = tuple(
        source for source in SUPPORTED_SOURCES if source in requested_sources
    )
    unknown_sources = sorted(requested_sources - set(SUPPORTED_SOURCES))
    if unknown_sources:
        raise ValueError(f"unsupported ingestion sources: {unknown_sources}")
    selected_languages = set(languages)
    unknown_languages = sorted(selected_languages - set(SUPPORTED_LANGUAGES))
    if unknown_languages:
        raise ValueError(f"unsupported ingestion languages: {unknown_languages}")

    manifests = source_manifest_map()
    checkouts: dict[str, dict] = {}
    source_paths = {
        "async_tn": source_cache / "async_tn",
        "polynorm": source_cache / "polynorm",
        "proteno": source_cache / "proteno",
    }
    for source_name in selected_sources:
        checkouts[source_name] = _verify_checkout(
            source_paths[source_name], source_name, manifests[source_name]["revision"]
        )

    candidate_dir = work_root / "candidates"
    exclusion_dir = work_root / "exclusions"
    report_dir = work_root / "reports" / "imports"
    report_root = work_root / "reports"
    for directory in (candidate_dir, exclusion_dir, report_dir, report_root):
        directory.mkdir(parents=True, exist_ok=True)

    shard_paths: list[Path] = []
    all_exclusions: list[dict] = []
    import_reports: list[dict] = []

    def add_shard(name: str, result):
        nonlocal shard_paths, all_exclusions, import_reports
        candidate_path, _, report, exclusions = _write_shard(
            name=name,
            result=result,
            candidate_dir=candidate_dir,
            exclusion_dir=exclusion_dir,
            report_dir=report_dir,
        )
        shard_paths.append(candidate_path)
        all_exclusions.extend(exclusions)
        import_reports.append(report)

    async_root = source_paths["async_tn"]
    if "async_tn" in selected_sources:
        english_path = async_root / "data" / "sentences.json"
        multilingual_path = async_root / "data" / "multilingual-sentences.json"
        if "en" in selected_languages:
            if not english_path.is_file():
                raise ValueError(f"missing Async English source file: {english_path}")
            add_shard("async_en", import_async(english_path, suite="english"))
        if selected_languages & set(SUPPORTED_LANGUAGES):
            if not multilingual_path.is_file():
                raise ValueError(
                    f"missing Async multilingual source file: {multilingual_path}"
                )
            add_shard(
                "async_multilingual",
                import_async(multilingual_path, suite="multilingual"),
            )

    if "polynorm" in selected_sources:
        official_root = source_paths["polynorm"] / "polynorm_bench"
        if not official_root.is_dir():
            raise ValueError(f"missing PolyNorm official tree: {official_root}")
        add_shard("polynorm", import_polynorm(official_root, format="official"))

    if "proteno" in selected_sources:
        for language_name, language_code in (("English", "en"), ("Spanish", "es")):
            if language_code not in selected_languages:
                continue
            language_root = source_paths["proteno"] / "data" / language_name
            if not language_root.is_dir():
                raise ValueError(f"missing Proteno {language_name} directory: {language_root}")
            add_shard(
                f"proteno_{language_code}",
                import_proteno(language_root, format="official"),
            )

    candidates = merge_candidates(read_records(shard_paths)) if shard_paths else []
    merged_path = candidate_dir / "all.jsonl"
    write_jsonl(merged_path, candidates)

    dedupe = deduplicate_candidates(candidates)
    conflicts = find_conflicts(candidates, mode="unit")
    families = suggest_families(candidates)
    write_json(report_root / "dedupe.json", dedupe)
    write_json(report_root / "conflicts.json", conflicts)
    write_json(report_root / "families.json", families)

    reviewed_paths = list(reviewed_paths or [
        repo_root() / "data" / "dev",
        repo_root() / "data" / "test",
    ])
    reviewed = read_records(reviewed_paths)
    targets = load_targets(targets_path or repo_root() / "taxonomy" / "coverage_targets.json")
    coverage = build_coverage(reviewed, targets)
    write_json(report_root / "coverage-reviewed.json", coverage)

    ranked = build_candidate_ranking(
        candidates,
        reviewed,
        targets=targets,
        dedupe=dedupe,
        conflicts=conflicts,
    )
    ranked_path = report_root / "ranked_candidates.jsonl"
    write_jsonl(ranked_path, ranked)
    batch = export_review_batch(ranked, limit=batch_limit)
    write_jsonl(work_root / "review_batches" / "batch-0001.jsonl", batch)

    exclusion_analysis = build_exclusion_analysis(all_exclusions)
    write_json(report_root / "exclusions.json", exclusion_analysis)
    pool_summary = build_candidate_pool_summary(
        candidates,
        exclusions=all_exclusions,
        conflicts=dedupe.get("conflicting_output_groups", []),
        import_reports=import_reports,
    )
    write_json(report_root / "upstream_pool_summary.json", pool_summary)

    summary = {
        "source_cache": str(source_cache),
        "work_root": str(work_root),
        "sources": list(selected_sources),
        "languages": sorted(selected_languages),
        "checkouts": checkouts,
        "shards": [
            {
                "name": report["source"],
                "source_rows": report["source_rows"],
                "records_created": report["records_created"],
                "exclusions": report["exclusions"],
                "row_accounting_ok": report["row_accounting_ok"],
            }
            for report in import_reports
        ],
        "records": len(candidates),
        "exclusions": len(all_exclusions),
        "conflicting_output_groups": len(dedupe.get("conflicting_output_groups", [])),
        "review_batch_records": len(batch),
        "artifacts": {
            "merged_candidates": str(merged_path),
            "ranked_candidates": str(ranked_path),
            "review_batch": str(work_root / "review_batches" / "batch-0001.jsonl"),
            "pool_summary": str(report_root / "upstream_pool_summary.json"),
        },
    }
    write_json(report_root / "ingestion-summary.json", summary)
    return summary
