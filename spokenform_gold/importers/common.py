from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ImportResult:
    records: list[dict]
    exclusions: list[dict]
    source_rows: int
    diagnostics: dict[str, Any] = field(default_factory=dict)


def build_import_diagnostics(
    *,
    records: list[dict],
    exclusions: list[dict],
    source_rows: int,
    source_hashes: list[str] | None = None,
) -> dict[str, Any]:
    categories = Counter()
    patterns = Counter()
    languages = Counter()
    locales = Counter()
    mappings = Counter()
    source_splits = Counter()
    exclusion_reasons = Counter(item.get("reason", "unknown") for item in exclusions)
    multi_unit_records = 0
    records_with_units = 0
    for record in records:
        languages[record.get("language", "")] += 1
        locales[record.get("locale", "")] += 1
        source = record.get("source", {})
        source_splits[source.get("source_split") or "unspecified"] += 1
        units = record.get("units", [])
        if units:
            records_with_units += 1
        if len(units) > 1:
            multi_unit_records += 1
        for unit in units:
            categories[unit.get("category", "")] += 1
            features = unit.get("features", {})
            patterns[features.get("surface_pattern", "unresolved")] += 1
            mappings[unit.get("mapping_status", "unmapped")] += 1

    hashes = sorted(set(source_hashes or []))
    accounted_rows = len(records) + len(exclusions)
    return {
        "source_rows": source_rows,
        "records_created": len(records),
        "records_with_units": records_with_units,
        "records_without_units": len(records) - records_with_units,
        "metadata_only_records": sum(not record.get("units") for record in records),
        "multi_unit_records": multi_unit_records,
        "units": sum(len(record.get("units", [])) for record in records),
        "exclusions": len(exclusions),
        "span_alignment_failures": sum(
            count
            for reason, count in exclusion_reasons.items()
            if "span" in reason or "alignment" in reason or "unresolved" in reason
        ),
        "unknown_category_counts": {
            reason: count
            for reason, count in sorted(exclusion_reasons.items())
            if "category" in reason or "unmappable" in reason
        },
        "exclusion_reason_counts": dict(sorted(exclusion_reasons.items())),
        "languages": dict(sorted(languages.items())),
        "locales": dict(sorted(locales.items())),
        "categories": dict(sorted(categories.items())),
        "surface_patterns": dict(sorted(patterns.items())),
        "mapping_status": dict(sorted(mappings.items())),
        "source_splits": dict(sorted(source_splits.items())),
        "source_hashes": hashes,
        "accounted_rows": accounted_rows,
        "row_accounting_ok": accounted_rows == source_rows,
    }
