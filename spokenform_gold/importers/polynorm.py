from __future__ import annotations

from pathlib import Path

from ..io import read_json, read_jsonl, sha256_text
from ..taxonomy import load_mapping, source_manifest_map
from .common import ImportResult


def _iter_rows(path: str | Path, fmt: str) -> tuple[list[dict], str]:
    target = Path(path)
    if fmt == "auto":
        fmt = "projection" if target.suffix == ".jsonl" else "raw"
    if fmt == "projection":
        return read_jsonl(target), "projection"
    if fmt != "raw":
        raise ValueError("polynorm format must be auto, raw, or projection")
    payload = read_json(target)
    if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
        raise ValueError("polynorm raw bundle must be an object with a records list")
    return payload["records"], "raw"


def _make_record(
    row: dict,
    *,
    source_path: Path,
    manifest: dict,
    mapping: dict,
    format_name: str,
) -> dict | tuple[str, str]:
    category = row.get("category")
    rule = mapping.get(category)
    if rule is None:
        return "unsupported_category", str(category)

    surface = row.get("surface")
    start = row.get("start")
    end = row.get("end")
    text = row.get("input")
    if not isinstance(text, str):
        return "malformed_row", "input must be a string"
    if not isinstance(surface, str) or not surface:
        return "malformed_row", "surface must be a string"
    if not isinstance(start, int) or not isinstance(end, int):
        return "missing_explicit_span", "start/end are required"
    if text[start:end] != surface:
        return "span_mismatch", surface

    locale = row.get("locale", "en-US")
    language = row.get("language", locale.split("-", 1)[0].lower())
    source_id = str(row.get("source_id") or row.get("upstream_id") or "")
    if not source_id:
        return "malformed_row", "source_id is required"

    notes = row.get("note") or row.get("projection_notes") or ""
    upstream_expected = row.get("expected")
    if upstream_expected is not None and not isinstance(upstream_expected, str):
        return "malformed_row", "expected must be a string when present"

    payload_hash = sha256_text(
        "\n".join(
            [
                source_id,
                text,
                upstream_expected or "",
                surface,
                str(start),
                str(end),
                str(category),
            ]
        )
    )
    return {
        "id": f"polynorm-{locale.lower()}-{source_id}",
        "schema_version": "1.0.0",
        "taxonomy_version": "1.0.0",
        "policy_version": "1.0.0",
        "language": language,
        "locale": locale,
        "split": "candidate",
        "family_id": f"polynorm-{source_id}",
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
        "units": [
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
                    "span_origin": "explicit",
                    "import_format": format_name,
                },
            }
        ],
        "negative_for": [],
        "notes": notes or "Imported from PolyNorm; adjudicate before promotion.",
    }


def import_polynorm(path: str | Path, *, format: str = "auto") -> ImportResult:
    manifest = source_manifest_map()["polynorm"]
    mapping = load_mapping("polynorm").get("mappings", {})
    source_path = Path(path)
    rows, format_name = _iter_rows(source_path, format)

    records: list[dict] = []
    exclusions: list[dict] = []
    for index, row in enumerate(rows, 1):
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
            manifest=manifest,
            mapping=mapping,
            format_name=format_name,
        )
        if isinstance(created, tuple):
            reason, detail = created
            exclusions.append(
                {
                    "source_id": str(row.get("source_id", index)),
                    "reason": reason,
                    "detail": detail,
                }
            )
            continue
        records.append(created)
    return ImportResult(records=records, exclusions=exclusions, source_rows=len(rows))
