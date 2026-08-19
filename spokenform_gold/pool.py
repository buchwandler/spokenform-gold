from __future__ import annotations

from collections import Counter
from collections.abc import Iterable

from .exclusions import build_exclusion_analysis
from .merge import merge_candidates


def build_candidate_pool_summary(
    records: Iterable[dict],
    *,
    exclusions: Iterable[dict] = (),
    conflicts: Iterable[dict] = (),
    import_reports: Iterable[dict] = (),
) -> dict:
    record_list = list(records)
    exclusion_list = list(exclusions)
    source_counts = Counter()
    language_counts = Counter()
    category_counts = Counter()
    pattern_counts = Counter()
    mapping_counts = Counter()
    inputs: set[str] = set()
    metadata_only = 0
    multi_unit = 0
    for record in record_list:
        source = record.get("source") or {}
        source_counts[source.get("benchmark", "unknown")] += 1
        language_counts[record.get("language", "unknown")] += 1
        inputs.add(" ".join(str(record.get("input", "")).split()).casefold())
        units = record.get("units", [])
        if not units:
            metadata_only += 1
        if len(units) > 1:
            multi_unit += 1
        for unit in units:
            category_counts[unit.get("category", "unknown")] += 1
            features = unit.get("features", {})
            pattern_counts[features.get("surface_pattern", "unresolved")] += 1
            mapping_counts[unit.get("mapping_status", "unmapped")] += 1

    reports = list(import_reports)
    source_yields = {}
    for report in reports:
        source = report.get("source") or report.get("benchmark") or "unknown"
        source_rows = int(report.get("source_rows", 0))
        created = int(report.get("records_created", 0))
        excluded = int(report.get("exclusions", 0))
        source_yields[source] = {
            "source_rows": source_rows,
            "records_created": created,
            "exclusions": excluded,
            "metadata_only_records": int(report.get("metadata_only_records", 0)),
            "row_accounting_ok": bool(report.get("row_accounting_ok", False)),
            "yield": created / source_rows if source_rows else 0.0,
        }

    merged = merge_candidates(record_list) if record_list else []
    exclusion_analysis = build_exclusion_analysis(exclusion_list)
    summary = {
        "records": len(merged),
        "unique_inputs": len(inputs),
        "sources": dict(sorted(source_counts.items())),
        "languages": dict(sorted(language_counts.items())),
        "categories": dict(sorted(category_counts.items())),
        "surface_patterns": dict(sorted(pattern_counts.items())),
        "mapping_status": dict(sorted(mapping_counts.items())),
        "exclusions": len(exclusion_list),
        "exclusions_by_source": exclusion_analysis["sources"],
        "exclusions_by_reason": exclusion_analysis["reasons"],
        "conflicting_output_groups": sum(1 for _ in conflicts),
        "metadata_only_records": metadata_only,
        "multi_unit_records": multi_unit,
        "source_yields": dict(sorted(source_yields.items())),
        "exclusion_analysis": exclusion_analysis,
    }
    return summary
