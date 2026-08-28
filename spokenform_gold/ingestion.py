from __future__ import annotations

import re
import subprocess
import tempfile
from collections.abc import Iterable
from pathlib import Path

from .census import build_upstream_census, write_census_artifacts
from .conflicts import find_conflicts
from .coverage import build_coverage, load_targets
from .deduplication import deduplicate_candidates
from .exclusions import build_exclusion_analysis, infer_surface_shape
from .families import suggest_families
from .importers import import_async, import_polynorm, import_proteno
from .importers.common import ImportResult, build_import_diagnostics
from .io import read_json, read_records, write_json, write_jsonl
from .merge import merge_candidates
from .pool import build_candidate_pool_summary
from .ranking import build_candidate_ranking, export_review_batch
from .taxonomy import repo_root, source_manifest_map
from .validation import validate_records

SUPPORTED_SOURCES = ("async_tn", "polynorm", "proteno")
DEFAULT_INGEST_LANGUAGES = ("en", "de", "es", "fr", "it", "pt")
SOURCE_LANGUAGE_CAPABILITIES = {
    "async_tn": frozenset(DEFAULT_INGEST_LANGUAGES),
    "polynorm": frozenset({"en", "de", "es", "fr", "it", "lt", "ja", "zh"}),
    "proteno": frozenset({"en", "es"}),
}
SUPPORTED_LANGUAGES = tuple(sorted(set().union(*SOURCE_LANGUAGE_CAPABILITIES.values())))


def _filter_result_languages(
    result: ImportResult, selected_languages: set[str]
) -> ImportResult:
    records = []
    exclusions = list(result.exclusions)
    for record in result.records:
        language = record.get("language")
        if language in selected_languages:
            records.append(record)
            continue
        source = record.get("source", {})
        exclusions.append(
            {
                "source_id": source.get("source_id", record.get("id", "unknown")),
                "source": source.get("benchmark", "unknown"),
                "language": language or "unknown",
                "reason": "language_not_selected",
                "detail": f"language {language!r} was not requested",
                "surface_shape": infer_surface_shape(record.get("input")),
            }
        )
    diagnostics = build_import_diagnostics(
        records=records,
        exclusions=exclusions,
        source_rows=result.source_rows,
        source_hashes=result.diagnostics.get("source_hashes", []),
    )
    return ImportResult(
        records=records,
        exclusions=exclusions,
        source_rows=result.source_rows,
        diagnostics=diagnostics,
    )


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


def _validate_source_language_request(
    source: str, languages: set[str], *, strict: bool
) -> None:
    unsupported = sorted(languages - SOURCE_LANGUAGE_CAPABILITIES[source])
    if unsupported and strict:
        supported = sorted(SOURCE_LANGUAGE_CAPABILITIES[source])
        raise ValueError(
            f"source {source!r} does not support requested languages {unsupported}; "
            f"supported languages: {supported}"
        )


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
        raise ValueError(
            f"generated {name} candidates are invalid: {'; '.join(errors)}"
        )
    if not report.get("row_accounting_ok"):
        raise ValueError(f"{name} import failed row accounting")
    return candidate_path, exclusions_path, report, exclusions


def run_upstream_ingestion(
    source_cache: str | Path,
    work_root: str | Path,
    *,
    sources: Iterable[str] = SUPPORTED_SOURCES,
    languages: Iterable[str] = DEFAULT_INGEST_LANGUAGES,
    reviewed_paths: Iterable[str | Path] | None = None,
    targets_path: str | Path | None = None,
    batch_limit: int = 100,
    batch_name: str = "batch-0001",
) -> dict:
    source_cache = Path(source_cache)
    work_root = Path(work_root)
    if not re.fullmatch(r"batch-(?:[0-9]{4}|[a-z][a-z0-9-]*)", batch_name):
        raise ValueError("batch_name must match batch-NNNN")
    requested_sources = set(sources)
    selected_sources = tuple(
        source for source in SUPPORTED_SOURCES if source in requested_sources
    )
    unknown_sources = sorted(requested_sources - set(SUPPORTED_SOURCES))
    if unknown_sources:
        raise ValueError(f"unsupported ingestion sources: {unknown_sources}")
    strict_source_language_selection = len(selected_sources) == 1
    selected_languages = set(languages)
    unknown_languages = sorted(selected_languages - set(SUPPORTED_LANGUAGES))
    if unknown_languages:
        raise ValueError(f"unsupported ingestion languages: {unknown_languages}")
    for source in selected_sources:
        _validate_source_language_request(
            source, selected_languages, strict=strict_source_language_selection
        )

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
        filtered_result = _filter_result_languages(result, selected_languages)
        if strict_source_language_selection:
            requested_rows = [
                record
                for record in result.records
                if record.get("language") in selected_languages
            ]
            requested_exclusions = [
                item
                for item in result.exclusions
                if item.get("language") in selected_languages
            ]
            if not requested_rows and not requested_exclusions:
                raise ValueError(
                    f"source {selected_sources[0]!r} has no rows for requested "
                    f"languages {sorted(selected_languages)}"
                )
        candidate_path, _, report, exclusions = _write_shard(
            name=name,
            result=filtered_result,
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
                raise ValueError(
                    f"missing Proteno {language_name} directory: {language_root}"
                )
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

    reviewed_paths = list(
        reviewed_paths
        or [
            repo_root() / "data" / "dev",
            repo_root() / "data" / "test",
        ]
    )
    reviewed = read_records(reviewed_paths)
    targets = load_targets(
        targets_path or repo_root() / "taxonomy" / "coverage_targets.json"
    )
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
    review_batch_path = work_root / "review_batches" / f"{batch_name}.jsonl"
    review_batch_path.parent.mkdir(parents=True, exist_ok=True)
    write_jsonl(review_batch_path, batch)

    census = build_upstream_census(candidates, all_exclusions, import_reports)
    if not census["summary"]["row_accounting_ok"]:
        raise ValueError("upstream census failed row accounting")
    census_artifacts = write_census_artifacts(work_root, census)

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
        "batch_name": batch_name,
        "census": census["summary"],
        "artifacts": {
            "merged_candidates": str(merged_path),
            "ranked_candidates": str(ranked_path),
            "review_batch": str(review_batch_path),
            "pool_summary": str(report_root / "upstream_pool_summary.json"),
            "census_rows": census_artifacts["rows"],
            "sentence_clusters": census_artifacts["sentence_clusters"],
            "census_summary": census_artifacts["summary"],
        },
    }
    write_json(report_root / "ingestion-summary.json", summary)
    return summary


def prepare_observations(
    source_cache: str | Path,
    out_dir: str | Path,
    *,
    reviewed_paths: Iterable[str | Path] | None = None,
    languages: Iterable[str] = DEFAULT_INGEST_LANGUAGES,
    sources: Iterable[str] = SUPPORTED_SOURCES,
    targets_path: str | Path | None = None,
    batch_name: str = "batch-0001",
) -> dict:
    """Import pinned upstream data into a batch-owned normalized source area."""
    destination = Path(out_dir)
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="spokenform-gold-import-") as temporary:
        summary = run_upstream_ingestion(
            source_cache,
            temporary,
            sources=sources,
            languages=languages,
            reviewed_paths=reviewed_paths,
            targets_path=targets_path,
            batch_name=batch_name,
        )
        observations = read_records([Path(temporary) / "candidates" / "all.jsonl"])
        exclusions = []
        for path in sorted((Path(temporary) / "exclusions").glob("*.json")):
            exclusions.extend(read_json(path))
        write_jsonl(destination / "observations.jsonl", observations)
        write_json(destination / "exclusions.json", exclusions)
        write_json(destination / "import-summary.json", summary)
        accounting = {
            "input_observations": len(observations) + len(exclusions),
            "invalid_observations": 0,
            "excluded_observations": len(exclusions),
            "candidate_observations": len(observations),
        }
        write_json(destination / "accounting.json", accounting)
    return {
        "observations": destination / "observations.jsonl",
        "exclusions": destination / "exclusions.json",
        "import_summary": destination / "import-summary.json",
        "accounting": destination / "accounting.json",
        "summary": summary,
    }
