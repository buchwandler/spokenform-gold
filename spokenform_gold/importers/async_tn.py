from __future__ import annotations

from pathlib import Path

from ..io import read_json, sha256_text
from ..taxonomy import load_mapping, source_manifest_map
from .common import ImportResult
from .projection import ProjectionRecord, ProjectionUnit

LANGUAGE_TO_LOCALE = {
    "en": "en-US",
    "de": "de-DE",
    "es": "es-ES",
    "fr": "fr-FR",
    "it": "it-IT",
    "pt": "pt-PT",
}


def detect_async_source_schema(payload: object, suite: str) -> str:
    if suite == "english":
        if not isinstance(payload, list):
            raise ValueError("english async_tn payload must be a JSON list")
        required = {"original_text", "normalized_text", "units"}
        for row in payload:
            if not isinstance(row, dict) or not required <= row.keys():
                raise ValueError(
                    "english async_tn rows must include original_text, normalized_text, and units"
                )
        return "async_tn_english_v1"
    if suite != "multilingual":
        raise ValueError("suite must be english or multilingual")
    if not isinstance(payload, list):
        raise TypeError("multilingual async_tn payload must be a JSON list")
    for row in payload:
        if not isinstance(row, dict) or not isinstance(row.get("languages"), dict):
            raise TypeError(
                "multilingual async_tn rows must include a languages object"
            )
    return "async_tn_multilingual_v1"


def _resolve_span(text: str, unit: dict) -> tuple[int, int, str] | None:
    surface = unit.get("text")
    if not isinstance(surface, str) or not surface:
        return None
    if isinstance(unit.get("start"), int) and isinstance(unit.get("end"), int):
        return unit["start"], unit["end"], "upstream"
    if isinstance(unit.get("source_start"), int) and isinstance(
        unit.get("source_end"), int
    ):
        return unit["source_start"], unit["source_end"], "source"
    first = text.find(surface)
    if first < 0:
        return None
    second = text.find(surface, first + 1)
    if second >= 0:
        return None
    return first, first + len(surface), "resolved-exact"


def _source_provenance(row: dict, manifest: dict) -> dict:
    original_text = row.get("original_text")
    return {
        "benchmark": "async_tn",
        "source_id": str(row.get("row_id", row.get("row_index", "unknown"))),
        "source_version": manifest["revision"],
        "source_url": manifest["source_url"],
        "license": manifest["license"],
        "source_hash": "sha256:"
        + sha256_text(original_text if isinstance(original_text, str) else str(row)),
        "importer_version": "1.0.0",
        "upstream_expected": row.get("normalized_text"),
        "source_bundle_schema": row.get("_source_bundle_schema"),
    }


def _make_unit(text: str, unit: dict, mapping: dict) -> dict | None:
    source_category = unit.get("norm_category")
    rule = mapping.get(source_category)
    if rule is None:
        return None
    resolved = _resolve_span(text, unit)
    if resolved is None:
        return None
    start, end, span_origin = resolved
    return ProjectionUnit(
        surface=unit["text"],
        start=start,
        end=end,
        category=rule["category"],
        source_category=source_category,
        mapping_status=rule["status"],
        surface_pattern=rule.get("surface_pattern", "imported"),
        span_origin=span_origin,
    ).to_candidate(import_format="bundle")


def _iter_rows(payload: object, suite: str):
    schema_name = detect_async_source_schema(payload, suite)
    if suite == "english":
        for row in payload:
            row["_source_bundle_schema"] = schema_name
            yield row
        return
    for base_row in payload:
        languages = base_row.get("languages", {})
        row_id = base_row.get("row_id", base_row.get("row_index", "unknown"))
        for language, localized in sorted(languages.items()):
            if not isinstance(localized, dict):
                continue
            row = dict(localized)
            row["row_id"] = f"{row_id}:{language}"
            row["language"] = language
            row["_source_bundle_schema"] = schema_name
            yield row


def import_async(path: str | Path, *, suite: str = "english") -> ImportResult:
    payload = read_json(path)
    manifests = source_manifest_map()
    manifest = manifests["async_tn"]
    mapping = load_mapping("async_tn").get("mappings", {})
    records: list[dict] = []
    exclusions: list[dict] = []

    source_rows = 0
    for index, row in enumerate(_iter_rows(payload, suite), 1):
        source_rows += 1
        if not isinstance(row, dict):
            exclusions.append(
                {
                    "source_id": str(index),
                    "reason": "malformed_row",
                    "detail": "row must be an object",
                }
            )
            continue
        language = row.get("language", "en")
        locale = row.get("locale") or LANGUAGE_TO_LOCALE.get(language)
        original_text = row.get("original_text")
        if language not in LANGUAGE_TO_LOCALE:
            exclusions.append(
                {
                    "source_id": str(row.get("row_id", index)),
                    "reason": "unsupported_language",
                    "detail": str(language),
                }
            )
            continue
        if not isinstance(original_text, str):
            exclusions.append(
                {
                    "source_id": str(row.get("row_id", index)),
                    "reason": "malformed_row",
                    "detail": "original_text must be a string",
                }
            )
            continue

        units = []
        unit_failure = None
        for unit in row.get("units", []):
            if not isinstance(unit, dict) or not unit.get("text"):
                unit_failure = {
                    "reason": "malformed_unit",
                    "detail": "unit must include text",
                }
                break
            mapped = _make_unit(original_text, unit, mapping)
            if mapped is None:
                unit_failure = {
                    "reason": "unmappable_or_unresolved_unit",
                    "detail": str(unit.get("norm_category")),
                }
                break
            units.append(mapped)
        if unit_failure:
            exclusions.append(
                {
                    "source_id": str(row.get("row_id", index)),
                    "reason": unit_failure["reason"],
                    "detail": unit_failure["detail"],
                }
            )
            continue

        source_id = str(row.get("row_id", row.get("row_index", index)))
        record = ProjectionRecord(
            benchmark="async_tn",
            source_id=source_id,
            source_version=manifest["revision"],
            source_url=manifest["source_url"],
            license=manifest["license"],
            language=language,
            locale=locale,
            input_text=original_text,
            source_file=Path(path).name,
            import_format="bundle",
            units=(),
            family_id=f"async-tn-{source_id}",
            upstream_expected=row.get("normalized_text"),
            notes="Imported from async_tn; adjudicate before promotion.",
            extra_source={
                "source_bundle_schema": row.get("_source_bundle_schema"),
            },
        ).to_candidate()
        record["id"] = f"async-tn-{language}-{source_id.replace(':', '-')}"
        record["source"] = _source_provenance(row, manifest)
        record["units"] = units
        records.append(record)

    return ImportResult(records=records, exclusions=exclusions, source_rows=source_rows)
