from __future__ import annotations

import io
import pickle
from pathlib import Path

from ..io import read_json, sha256_text
from ..taxonomy import load_mapping, source_manifest_map
from .common import ImportResult


class RestrictedUnpickler(pickle.Unpickler):
    SAFE_BUILTINS = {
        "builtins": {
            "dict",
            "list",
            "tuple",
            "set",
            "str",
            "int",
            "float",
            "bool",
            "NoneType",
        }
    }

    def find_class(self, module, name):
        if module in self.SAFE_BUILTINS and name in self.SAFE_BUILTINS[module]:
            return getattr(__import__(module), name)
        raise pickle.UnpicklingError(f"unsafe pickle global: {module}.{name}")


def _load_payload(path: str | Path):
    target = Path(path)
    if target.suffix == ".json":
        return read_json(target)
    if target.suffix == ".pkl":
        return RestrictedUnpickler(io.BytesIO(target.read_bytes())).load()
    raise ValueError("proteno source must be .json or .pkl")


def _iter_rows(path: str | Path, fmt: str) -> tuple[list[dict], str]:
    payload = _load_payload(path)
    if fmt not in {"auto", "raw", "projection"}:
        raise ValueError("proteno format must be auto, raw, or projection")
    if not isinstance(payload, dict) or not isinstance(payload.get("cases"), list):
        raise ValueError("proteno payload must be an object with a cases list")
    if fmt == "projection":
        return payload["cases"], "projection"
    if fmt == "raw":
        return payload["cases"], "raw"
    return payload["cases"], str(payload.get("format", "raw"))


def _make_record(
    case: dict,
    *,
    source_path: Path,
    manifest: dict,
    mapping: dict,
    format_name: str,
) -> dict | tuple[str, str]:
    category = case.get("category")
    rule = mapping.get(category)
    if rule is None:
        return "unsupported_category", str(category)
    text = case.get("input")
    surface = case.get("surface")
    start = case.get("start")
    end = case.get("end")
    if not isinstance(text, str):
        return "malformed_row", "input must be a string"
    if not isinstance(surface, str) or not surface:
        return "malformed_row", "surface must be a string"
    if not isinstance(start, int) or not isinstance(end, int):
        return "missing_explicit_span", "start/end are required"
    if text[start:end] != surface:
        return "span_mismatch", surface
    source_id = str(case.get("case_id") or case.get("source_id") or "")
    if not source_id:
        return "malformed_row", "case_id is required"

    upstream_expected = case.get("expected")
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
        "id": f"proteno-{source_id}",
        "schema_version": "1.0.0",
        "taxonomy_version": "1.0.0",
        "policy_version": "1.0.0",
        "language": case.get("language", "en"),
        "locale": case.get("locale", "en-US"),
        "split": "candidate",
        "family_id": f"proteno-{source_id}",
        "status": "quarantine",
        "input": text,
        "expected_output": None,
        "source": {
            "benchmark": "proteno",
            "source_id": source_id,
            "source_version": manifest["revision"],
            "source_url": manifest["source_url"],
            "license": manifest["license"],
            "source_hash": f"sha256:{payload_hash}",
            "source_file": str(source_path.name),
            "source_split": case.get("source_split"),
            "upstream_expected": upstream_expected,
            "projection_notes": case.get("projection_notes", ""),
            "identity_example": bool(case.get("identity_example", False)),
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
                    "identity_example": bool(case.get("identity_example", False)),
                    "span_origin": "explicit",
                    "import_format": format_name,
                },
            }
        ],
        "negative_for": [],
        "notes": case.get("projection_notes", ""),
    }


def import_proteno(path: str | Path, *, format: str = "auto") -> ImportResult:
    manifest = source_manifest_map()["proteno"]
    mapping = load_mapping("proteno").get("mappings", {})
    source_path = Path(path)
    rows, format_name = _iter_rows(source_path, format)

    records: list[dict] = []
    exclusions: list[dict] = []
    for index, case in enumerate(rows, 1):
        if not isinstance(case, dict):
            exclusions.append(
                {
                    "source_id": str(index),
                    "reason": "malformed_row",
                    "detail": "case must be an object",
                }
            )
            continue
        created = _make_record(
            case,
            source_path=source_path,
            manifest=manifest,
            mapping=mapping,
            format_name=format_name,
        )
        if isinstance(created, tuple):
            reason, detail = created
            exclusions.append(
                {
                    "source_id": str(case.get("case_id", index)),
                    "reason": reason,
                    "detail": detail,
                }
            )
            continue
        records.append(created)
    return ImportResult(records=records, exclusions=exclusions, source_rows=len(rows))
