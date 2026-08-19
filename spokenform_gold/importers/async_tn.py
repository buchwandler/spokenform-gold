from __future__ import annotations

from pathlib import Path

from ..exclusions import infer_surface_shape
from ..io import read_json, sha256_file, sha256_text
from ..taxonomy import load_mapping, source_manifest_map
from .common import ImportResult, build_import_diagnostics
from .projection import ProjectionRecord, ProjectionUnit
from .surface_patterns import infer_surface_pattern

LANGUAGE_TO_LOCALE = {
    "en": "en-US",
    "de": "de-DE",
    "es": "es-ES",
    "fr": "fr-FR",
    "it": "it-IT",
    "pt": "pt-PT",
}


def detect_async_source_schema(payload: object, suite: str) -> str:
    if not isinstance(payload, list):
        raise TypeError(f"{suite} async_tn payload must be a JSON list")
    if suite == "english":
        for row in payload:
            if not isinstance(row, dict):
                raise TypeError("english async_tn rows must be objects")
            required = {"original_text", "normalized_text", "units"}
            if not required <= row.keys():
                raise ValueError(
                    "english async_tn rows must include original_text, normalized_text, and units"
                )
        if any("categories" in row or "row_index" in row for row in payload):
            return "async_tn_english_v2"
        return "async_tn_english_v1"
    if suite != "multilingual":
        raise ValueError("suite must be english or multilingual")
    for row in payload:
        if not isinstance(row, dict) or not isinstance(row.get("languages"), dict):
            raise TypeError(
                "multilingual async_tn rows must include a languages object"
            )
    if any(
        isinstance(localized, dict) and "language_code" in localized
        for row in payload
        for localized in row.get("languages", {}).values()
    ):
        return "async_tn_multilingual_v2"
    return "async_tn_multilingual_v1"


def _resolve_mapping(mapping: dict[str, dict], source_category: object) -> dict | None:
    if not isinstance(source_category, str):
        return None
    if source_category in mapping:
        return mapping[source_category]
    folded = source_category.casefold()
    for name, rule in mapping.items():
        if name.casefold() == folded:
            return rule
    return None


def _resolve_span(text: str, unit: dict) -> tuple[int, int, str] | None:
    surface = unit.get("text")
    if not isinstance(surface, str) or not surface:
        return None
    if isinstance(unit.get("start"), int) and isinstance(unit.get("end"), int):
        start, end = unit["start"], unit["end"]
        if text[start:end] != surface:
            return None
        return start, end, "upstream"
    if isinstance(unit.get("source_start"), int) and isinstance(
        unit.get("source_end"), int
    ):
        start, end = unit["source_start"], unit["source_end"]
        if text[start:end] != surface:
            return None
        return start, end, "source"
    candidates = []
    start = 0
    while True:
        found = text.find(surface, start)
        if found < 0:
            break
        end = found + len(surface)
        token_boundary = (
            not surface[0].isalnum() or found == 0 or not text[found - 1].isalnum()
        ) and (not surface[-1].isalnum() or end == len(text) or not text[end].isalnum())
        if token_boundary:
            candidates.append((found, end))
        start = end
    if len(candidates) != 1:
        return None
    first, end = candidates[0]
    return first, end, "resolved-exact"


def _source_provenance(
    row: dict,
    manifest: dict,
    *,
    source_file: Path,
    artifact_hash: str,
) -> dict:
    original_text = row.get("original_text")
    return {
        "benchmark": "async_tn",
        "source_id": str(row.get("row_id", row.get("row_index", "unknown"))),
        "source_version": manifest["revision"],
        "source_url": manifest["source_url"],
        "license": manifest["license"],
        "source_hash": "sha256:"
        + sha256_text(original_text if isinstance(original_text, str) else str(row)),
        "source_artifact_hash": artifact_hash,
        "source_file": source_file.name,
        "importer_version": "1.1.0",
        "upstream_expected": row.get("normalized_text"),
        "source_bundle_schema": row.get("_source_bundle_schema"),
        "source_category_list": row.get("categories", []),
    }


def _make_unit(
    text: str,
    unit: dict,
    mapping: dict[str, dict],
) -> dict | None:
    source_category = unit.get("norm_category")
    rule = _resolve_mapping(mapping, source_category)
    if rule is None:
        return None
    resolved = _resolve_span(text, unit)
    if resolved is None:
        return None
    start, end, span_origin = resolved
    category = rule["category"]
    surface_pattern = infer_surface_pattern(
        category=category,
        surface=unit["text"],
        text=text,
        source_category=str(source_category),
    ) or rule.get("surface_pattern", "imported")
    return ProjectionUnit(
        surface=unit["text"],
        start=start,
        end=end,
        category=category,
        source_category=str(source_category),
        mapping_status=rule["status"],
        surface_pattern=surface_pattern,
        span_origin=span_origin,
        features={"source_unit_index": unit.get("unit_index")}
        if unit.get("unit_index") is not None
        else {},
    ).to_candidate(import_format="bundle")


def _iter_rows(payload: object, suite: str):
    schema_name = detect_async_source_schema(payload, suite)
    if suite == "english":
        for row in payload:
            copied = dict(row)
            copied["_source_bundle_schema"] = schema_name
            yield copied
        return
    for base_row in payload:
        languages = base_row.get("languages", {})
        row_id = base_row.get(
            "row_id", base_row.get("sentence_id", base_row.get("row_index", "unknown"))
        )
        for language, localized in sorted(languages.items()):
            if not isinstance(localized, dict):
                yield {
                    "row_id": f"{row_id}:{language}",
                    "language": language,
                    "_invalid_localized": True,
                }
                continue
            row = dict(localized)
            row["row_id"] = f"{row_id}:{language}"
            row["language"] = localized.get("language_code", language)
            row["locale"] = localized.get("locale")
            row["_source_bundle_schema"] = schema_name
            yield row


def import_async(path: str | Path, *, suite: str = "english") -> ImportResult:
    source_path = Path(path)
    payload = read_json(source_path)
    manifests = source_manifest_map()
    manifest = manifests["async_tn"]
    mapping = load_mapping("async_tn").get("mappings", {})
    artifact_hash = "sha256:" + sha256_file(source_path)
    records: list[dict] = []
    exclusions: list[dict] = []

    source_rows = 0
    for index, row in enumerate(_iter_rows(payload, suite), 1):
        source_rows += 1
        source_id = str(row.get("row_id", row.get("row_index", index)))
        if row.get("_invalid_localized"):
            exclusions.append(
                {
                    "source_id": source_id,
                    "source": "async_tn",
                    "language": row.get("language", "unknown"),
                    "reason": "malformed_row",
                    "detail": "localized row must be an object",
                    "surface_shape": "unknown",
                }
            )
            continue
        language = row.get("language", "en")
        locale = row.get("locale") or LANGUAGE_TO_LOCALE.get(language)
        original_text = row.get("original_text")
        if language not in LANGUAGE_TO_LOCALE:
            exclusions.append(
                {
                    "source_id": source_id,
                    "source": "async_tn",
                    "language": language,
                    "reason": "unsupported_language",
                    "detail": str(language),
                    "surface_shape": infer_surface_shape(row.get("original_text")),
                }
            )
            continue
        if not isinstance(original_text, str):
            exclusions.append(
                {
                    "source_id": source_id,
                    "source": "async_tn",
                    "language": language,
                    "reason": "malformed_row",
                    "detail": "original_text must be a string",
                    "surface_shape": "unknown",
                }
            )
            continue

        raw_units = row.get("units", [])
        if raw_units is None:
            raw_units = []
        if not isinstance(raw_units, list):
            exclusions.append(
                {
                    "source_id": source_id,
                    "source": "async_tn",
                    "language": language,
                    "reason": "malformed_row",
                    "detail": "units must be a list",
                    "surface_shape": infer_surface_shape(original_text),
                }
            )
            continue
        units = []
        unit_failure = None
        for unit_index, unit in enumerate(raw_units):
            if not isinstance(unit, dict) or not unit.get("text"):
                unit_failure = {
                    "source": "async_tn",
                    "reason": "malformed_unit",
                    "detail": "unit must include text",
                    "source_category": "unknown",
                    "language": language,
                    "surface_shape": "unknown",
                }
                break
            unit = dict(unit)
            unit["unit_index"] = unit_index
            mapped = _make_unit(original_text, unit, mapping)
            if mapped is None:
                unit_failure = {
                    "source": "async_tn",
                    "reason": "unmappable_or_unresolved_unit",
                    "detail": str(unit.get("norm_category")),
                    "source_category": str(unit.get("norm_category")),
                    "language": language,
                    "surface": unit.get("text", ""),
                    "surface_shape": infer_surface_shape(unit.get("text")),
                }
                break
            units.append(mapped)
        if unit_failure:
            exclusions.append({"source_id": source_id, **unit_failure})
            continue

        record = ProjectionRecord(
            benchmark="async_tn",
            source_id=source_id,
            source_version=manifest["revision"],
            source_url=manifest["source_url"],
            license=manifest["license"],
            language=language,
            locale=locale,
            input_text=original_text,
            source_file=source_path.name,
            import_format="bundle",
            units=(),
            family_id=f"async-tn-{source_id}",
            upstream_expected=row.get("normalized_text"),
            notes="Imported from async_tn; adjudicate before promotion.",
            extra_source={"source_bundle_schema": row.get("_source_bundle_schema")},
        ).to_candidate()
        record["id"] = f"async-tn-{language}-{source_id.replace(':', '-')}"
        record["source"] = _source_provenance(
            row, manifest, source_file=source_path, artifact_hash=artifact_hash
        )
        record["units"] = units
        records.append(record)

    diagnostics = build_import_diagnostics(
        records=records,
        exclusions=exclusions,
        source_rows=source_rows,
        source_hashes=[artifact_hash],
    )
    diagnostics["suite"] = suite
    diagnostics["source_bundle_schema"] = detect_async_source_schema(payload, suite)
    diagnostics["source_file"] = source_path.name
    return ImportResult(
        records=records,
        exclusions=exclusions,
        source_rows=source_rows,
        diagnostics=diagnostics,
    )
