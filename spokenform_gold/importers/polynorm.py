from __future__ import annotations

import re
from pathlib import Path

from ..io import read_json, read_jsonl, sha256_text
from ..taxonomy import load_mapping, source_manifest_map
from .common import ImportResult

OFFICIAL_GLOB = "*_groundtruth.jsonl"
LOCALE_PATTERN = re.compile(r"([a-z]{2}-[A-Z]{2})")
MONTH_PATTERN = (
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|"
    r"Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|"
    r"Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
)
SPAN_PATTERNS: dict[str, tuple[str, ...]] = {
    "abbreviation": (r"\b[A-Za-z]{1,6}\.",),
    "acronym": (r"\b[A-Z]{2,}(?:s)?\b",),
    "address": (r"\b\d+\s+[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)*\b",),
    "biology": (r"\b[A-Z][a-z]+\s+[a-z]{2,}\b",),
    "cardinal": (r"\b\d+\b",),
    "chemical": (r"\b(?:[A-Z][a-z]?\d*)+\b",),
    "coordinates": (
        r"\b-?\d{1,3}\.\d+\s*,\s*-?\d{1,3}\.\d+\b",
        r"\b\d{1,3}°\s*\d{1,2}'?\s*\d{1,2}(?:\.\d+)?\"?\s*[NSEW]\b",
    ),
    "currency": (
        r"(?:[$€£¥]\s?\d[\d,]*(?:\.\d+)?|\b\d[\d,]*(?:\.\d+)?\s?(?:USD|EUR|GBP|JPY)\b)",
    ),
    "date": (
        r"\b\d{4}-\d{2}-\d{2}\b",
        r"\b\d{1,2}/\d{1,2}/\d{2,4}\b",
        rf"\b{MONTH_PATTERN}\s+\d{{1,2}},?\s+\d{{4}}\b",
    ),
    "decimal": (r"\b-?\d[\d,]*\.\d+\b",),
    "fraction": (r"\b\d+/\d+\b",),
    "identifier": (r"\b[A-Za-z]+[A-Za-z0-9-]*\d+[A-Za-z0-9-]*\b",),
    "isbn": (r"\b97[89][-\d]{10,16}\b",),
    "legal_citation": (r"\b(?:§|Art\.?|Rule)\s*\d+[A-Za-z0-9.-]*\b",),
    "math_expression": (
        r"\b\d+\s*[-+/*^=]\s*\d+(?:\s*[-+/*^=]\s*\d+)*\b",
        r"\b[A-Za-z]\d+\b",
    ),
    "measurement_unit": (
        r"\b\d+(?:\.\d+)?\s?(?:kg|g|mg|lb|km|m|cm|mm|L|mL|°C|°F|%)\b",
    ),
    "music": (r"\b[A-G](?:#|b)?(?:maj|min|m|sus|dim|aug)?\b",),
    "ordinal": (r"\b\d+(?:st|nd|rd|th)\b",),
    "phone": (r"\b(?:\+\d{1,3}\s*)?(?:\d[\s-]?){7,}\d\b",),
    "product_code": (r"\b[A-Z0-9]+(?:-[A-Z0-9]+)+\b",),
    "roman_numeral": (r"\b[IVXLCDM]+\b",),
    "score_or_range": (r"\b\d+\s*-\s*\d+\b",),
    "serial_or_plate": (r"\b[A-Z0-9]{2,}(?:-[A-Z0-9]{2,})+\b",),
    "ticker": (r"\b[A-Z]{1,5}(?:\.[A-Z])?\b",),
    "time": (r"\b\d{1,2}:\d{2}(?:\s?[AP]M)?\b",),
    "url_or_email": (
        r"\bhttps?://\S+\b",
        r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b",
    ),
    "version": (r"\bv?\d+(?:\.\d+)+(?:-[A-Za-z0-9.]+)?\b",),
}


def _infer_official_locale(path: Path) -> str:
    for candidate in (path.parent.name, path.stem):
        match = LOCALE_PATTERN.search(candidate)
        if match:
            return match.group(1)
    raise ValueError(f"could not infer PolyNorm locale from {path}")


def _official_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    files = sorted(path.rglob(OFFICIAL_GLOB))
    if not files:
        raise ValueError(f"no PolyNorm official files found under {path}")
    return files


def _iter_rows(path: str | Path, fmt: str) -> tuple[list[tuple[dict, Path, str]], str]:
    target = Path(path)
    if fmt == "auto":
        if target.is_dir() or target.name.endswith("_groundtruth.jsonl"):
            fmt = "official"
        elif target.suffix == ".jsonl":
            fmt = "projection"
        else:
            fmt = "raw"
    if fmt == "projection":
        return [
            (row, target, row.get("locale", "en-US")) for row in read_jsonl(target)
        ], "projection"
    if fmt == "raw":
        payload = read_json(target)
        if not isinstance(payload, dict) or not isinstance(
            payload.get("records"), list
        ):
            raise ValueError(
                "polynorm raw bundle must be an object with a records list"
            )
        locale = payload.get("locale", "en-US")
        return [(row, target, locale) for row in payload["records"]], "raw"
    if fmt != "official":
        raise ValueError("polynorm format must be auto, raw, projection, or official")

    rows: list[tuple[dict, Path, str]] = []
    for official_file in _official_files(target):
        locale = _infer_official_locale(official_file)
        for row in read_jsonl(official_file):
            rows.append((row, official_file, locale))
    return rows, "official"


def _find_unique_span(text: str, category: str) -> tuple[int, int, str] | None:
    patterns = SPAN_PATTERNS.get(category, ())
    matches: list[tuple[int, int]] = []
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            span = match.span()
            if span not in matches:
                matches.append(span)
    if len(matches) != 1:
        return None
    start, end = matches[0]
    return start, end, text[start:end]


def _explicit_unit(
    *,
    text: str,
    surface: object,
    start: object,
    end: object,
    rule: dict,
    category: str,
    format_name: str,
) -> dict | tuple[str, str]:
    if not isinstance(surface, str) or not surface:
        return "malformed_row", "surface must be a string"
    if not isinstance(start, int) or not isinstance(end, int):
        return "missing_explicit_span", "start/end are required"
    if text[start:end] != surface:
        return "span_mismatch", surface
    return {
        "surface": surface,
        "start": start,
        "end": end,
        "category": rule["category"],
        "source_category": category,
        "mapping_status": rule["status"],
        "semantic": {},
        "policy": "unadjudicated-upstream",
        "canonical": None,
        "accepted": [],
        "rejected": [],
        "features": {
            "surface_pattern": rule.get("surface_pattern", "imported"),
            "span_origin": "explicit",
            "import_format": format_name,
        },
    }


def _official_units(text: str, category: str, rule: dict) -> tuple[list[dict], str]:
    if rule.get("status") == "unsupported" or not isinstance(rule.get("category"), str):
        return [], f"category {category} is explicitly unsupported"
    resolved = _find_unique_span(text, rule["category"])
    if resolved is None:
        return [], "span_unresolved"
    start, end, surface = resolved
    return (
        [
            {
                "surface": surface,
                "start": start,
                "end": end,
                "category": rule["category"],
                "source_category": category,
                "mapping_status": rule["status"],
                "semantic": {},
                "policy": "unadjudicated-upstream",
                "canonical": None,
                "accepted": [],
                "rejected": [],
                "features": {
                    "surface_pattern": rule.get("surface_pattern", "imported"),
                    "span_origin": "projected-category-rule",
                    "import_format": "official",
                },
            }
        ],
        "",
    )


def _record_id(locale: str, source_id: str) -> str:
    return f"polynorm-{locale.lower()}-{source_id.replace(':', '-')}"


def _make_record(
    row: dict,
    *,
    source_path: Path,
    locale: str,
    manifest: dict,
    mapping: dict,
    format_name: str,
) -> dict | tuple[str, str]:
    category = row.get("category")
    rule = mapping.get(category)
    if rule is None:
        return "unsupported_category", str(category)

    if format_name == "official":
        text = row.get("original_text")
        upstream_expected = row.get("normalized_text")
        source_id = str(row.get("index") or row.get("source_id") or "")
        if source_id:
            source_id = f"{locale}:{source_id}"
    else:
        text = row.get("input")
        upstream_expected = row.get("expected")
        source_id = str(row.get("source_id") or row.get("upstream_id") or "")

    if not isinstance(text, str):
        return "malformed_row", "input must be a string"
    if not source_id:
        return "malformed_row", "source_id is required"
    if upstream_expected is not None and not isinstance(upstream_expected, str):
        return "malformed_row", "expected must be a string when present"

    language = row.get("language", locale.split("-", 1)[0].lower())
    notes = row.get("note") or row.get("projection_notes") or ""
    units: list[dict]
    unit_note = ""
    if format_name == "official":
        units, unit_note = _official_units(text, str(category), rule)
    else:
        created_unit = _explicit_unit(
            text=text,
            surface=row.get("surface"),
            start=row.get("start"),
            end=row.get("end"),
            rule=rule,
            category=str(category),
            format_name=format_name,
        )
        if isinstance(created_unit, tuple):
            return created_unit
        units = [created_unit]

    payload_hash = sha256_text(
        "\n".join(
            [
                source_id,
                text,
                upstream_expected or "",
                str(category),
                format_name,
            ]
        )
    )
    note_text = notes or "Imported from PolyNorm; adjudicate before promotion."
    if unit_note:
        note_text = f"{note_text} [{unit_note}]"
    return {
        "id": _record_id(locale, source_id),
        "schema_version": "1.0.0",
        "taxonomy_version": "1.0.0",
        "policy_version": "1.0.0",
        "language": language,
        "locale": locale,
        "split": "candidate",
        "family_id": f"polynorm-{source_id.replace(':', '-')}",
        "status": "quarantine",
        "input": text,
        "expected_output": None,
        "source": {
            "benchmark": "polynorm",
            "source_id": source_id,
            "source_version": manifest["revision"],
            "source_url": manifest["source_url"],
            "license": manifest["license"],
            "upstream_expected": upstream_expected,
            "source_category": category,
            "source_hash": f"sha256:{payload_hash}",
            "source_file": str(source_path.name),
            "source_split": row.get("source_split"),
            "projection_notes": row.get("projection_notes", ""),
            "import_format": format_name,
            "importer_version": "1.0.0",
        },
        "units": units,
        "negative_for": [],
        "notes": note_text,
    }


def import_polynorm(path: str | Path, *, format: str = "auto") -> ImportResult:
    manifest = source_manifest_map()["polynorm"]
    mapping = load_mapping("polynorm").get("mappings", {})
    rows, format_name = _iter_rows(path, format)

    records: list[dict] = []
    exclusions: list[dict] = []
    for index, (row, source_path, locale) in enumerate(rows, 1):
        if not isinstance(row, dict):
            exclusions.append(
                {
                    "source_id": str(index),
                    "reason": "malformed_row",
                    "detail": "row must be an object",
                }
            )
            continue
        created = _make_record(
            row,
            source_path=source_path,
            locale=locale,
            manifest=manifest,
            mapping=mapping,
            format_name=format_name,
        )
        if isinstance(created, tuple):
            reason, detail = created
            source_id = row.get("source_id") or row.get("index") or index
            exclusions.append(
                {
                    "source_id": str(source_id),
                    "reason": reason,
                    "detail": detail,
                }
            )
            continue
        records.append(created)
    return ImportResult(records=records, exclusions=exclusions, source_rows=len(rows))
