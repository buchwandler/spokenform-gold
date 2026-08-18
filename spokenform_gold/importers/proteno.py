from __future__ import annotations

import io
import pickle
import re
from pathlib import Path
from typing import ClassVar

from ..io import read_json, sha256_text
from ..taxonomy import load_mapping, source_manifest_map
from .common import ImportResult, build_import_diagnostics
from .surface_patterns import infer_surface_pattern

SPAN_TAG = re.compile(r'<error\s+what="([^"]+)">([^<]+)</error>')
OFFICIAL_LANGUAGES = {
    "English": ("en", "en-US", "proteno_en"),
    "Spanish": ("es", "es-ES", "proteno_es"),
    "Tamil": ("ta", "ta-IN", "proteno_ta"),
}
RECOGNIZERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("ip_address", (r"\b\d{1,3}(?:\.\d{1,3}){3}\b",)),
    ("date", (r"\b\d{4}-\d{2}-\d{2}\b", r"\b\d{1,2}/\d{1,2}/\d{2,4}\b")),
    ("time", (r"\b\d{1,2}:\d{2}(?:\s?[AP]M)?\b",)),
    (
        "currency",
        (
            r"(?:[$€£¥]\s?\d[\d,]*(?:\.\d+)?|\b\d[\d,]*(?:\.\d+)?\s?(?:USD|EUR|GBP|JPY)\b)",
        ),
    ),
    ("fraction", (r"\b\d+/\d+\b",)),
    ("decimal", (r"\b-?\d[\d,]*\.\d+\b",)),
    ("phone", (r"\b(?:\+\d{1,3}\s*)?(?:\d[\s-]?){6,}\d\b",)),
    (
        "url_or_email",
        (r"\bhttps?://\S+\b", r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b"),
    ),
    ("version", (r"\bv?\d+(?:\.\d+)+(?:-[A-Za-z0-9.]+)?\b",)),
    ("math_expression", (r"\b\d+\s*[-+/*^=]\s*\d+(?:\s*[-+/*^=]\s*\d+)*\b",)),
    (
        "measurement_unit",
        (r"\b\d+(?:\.\d+)?\s?(?:kg|g|mg|lb|km|m|cm|mm|L|mL|°C|°F|%)\b",),
    ),
    ("ordinal", (r"\b\d+(?:st|nd|rd|th)\b",)),
    ("identifier", (r"\b[A-Za-z]+[A-Za-z0-9-]*\d+[A-Za-z0-9-]*\b",)),
    ("cardinal", (r"\b\d+\b",)),
)


class RestrictedUnpickler(pickle.Unpickler):
    SAFE_BUILTINS: ClassVar[dict[str, set[str]]] = {
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


def _official_pair(path: Path) -> tuple[Path, Path]:
    if path.is_dir():
        unnorm_path = path / "unnorm_list.pkl"
        norm_path = path / "norm_list.pkl"
    else:
        unnorm_path = path.parent / "unnorm_list.pkl"
        norm_path = path.parent / "norm_list.pkl"
    if not unnorm_path.exists() or not norm_path.exists():
        raise ValueError(f"missing official Proteno pair under {path}")
    return unnorm_path, norm_path


def _iter_rows(
    path: str | Path,
    fmt: str,
) -> tuple[list[dict], str, tuple[str, str, str] | None, list[str]]:
    target = Path(path)
    if fmt == "auto":
        if target.is_dir() or target.name in {"unnorm_list.pkl", "norm_list.pkl"}:
            fmt = "official"
        elif target.suffix == ".json":
            fmt = "raw"
        else:
            fmt = "projection"
    if fmt in {"raw", "projection"}:
        payload = _load_payload(target)
        if not isinstance(payload, dict) or not isinstance(payload.get("cases"), list):
            raise ValueError("proteno payload must be an object with a cases list")
        return (
            payload["cases"],
            str(payload.get("format", fmt)),
            None,
            [str(target.name)],
        )
    if fmt != "official":
        raise ValueError("proteno format must be auto, raw, projection, or official")

    unnorm_path, norm_path = _official_pair(target)
    directory_name = unnorm_path.parent.name
    if directory_name not in OFFICIAL_LANGUAGES:
        raise ValueError(f"unsupported official Proteno directory {directory_name}")
    language_info = OFFICIAL_LANGUAGES[directory_name]
    unnorm_rows = _load_payload(unnorm_path)
    norm_rows = _load_payload(norm_path)
    if not isinstance(unnorm_rows, list) or not isinstance(norm_rows, list):
        raise TypeError("official Proteno pickle payloads must be lists")
    if len(unnorm_rows) != len(norm_rows):
        raise ValueError("Proteno pair length mismatch")

    rows = [
        {"input": unnorm_value, "normalized": norm_value, "row_index": index}
        for index, (unnorm_value, norm_value) in enumerate(
            zip(unnorm_rows, norm_rows, strict=True), 1
        )
    ]
    return rows, "official", language_info, [str(unnorm_path.name), str(norm_path.name)]


def _resolved_span(text: str, surface: str) -> tuple[int, int] | None:
    first = text.find(surface)
    if first < 0:
        return None
    second = text.find(surface, first + 1)
    if second >= 0:
        return None
    return first, first + len(surface)


def _recognize_spans(text: str) -> list[tuple[int, int, str, str]]:
    matches: list[tuple[int, int, str, str]] = []
    for source_category, patterns in RECOGNIZERS:
        for pattern in patterns:
            for match in re.finditer(pattern, text):
                start, end = match.span()
                matches.append((start, end, text[start:end], source_category))
    matches.sort(key=lambda item: (item[0], -(item[1] - item[0])))
    accepted: list[tuple[int, int, str, str]] = []
    occupied: list[tuple[int, int]] = []
    for start, end, surface, source_category in matches:
        if any(
            not (end <= used_start or start >= used_end)
            for used_start, used_end in occupied
        ):
            continue
        occupied.append((start, end))
        accepted.append((start, end, surface, source_category))
    return accepted


def _unit_from_category(
    *,
    mapping: dict,
    source_category: str,
    surface: str,
    start: int,
    end: int,
    format_name: str,
    identity_example: bool = False,
) -> dict | None:
    rule = mapping.get(source_category)
    if rule is None:
        return None
    return {
        "surface": surface,
        "start": start,
        "end": end,
        "category": rule["category"],
        "source_category": source_category,
        "mapping_status": rule["status"],
        "semantic": {},
        "policy": "unadjudicated-upstream",
        "canonical": None,
        "accepted": [],
        "rejected": [],
        "features": {
            "surface_pattern": infer_surface_pattern(
                category=rule["category"],
                surface=surface,
                text=surface,
                source_category=source_category,
            )
            or rule.get("surface_pattern", "imported"),
            "identity_example": identity_example,
            "span_origin": "explicit"
            if format_name != "official"
            else "projected-category-rule",
            "import_format": format_name,
        },
    }


def _official_units(
    *,
    text: str,
    normalized: str,
    mapping: dict,
) -> tuple[list[dict], str, str]:
    if "<error" in normalized:
        units: list[dict] = []
        upstream_expected = normalized
        for spoken, surface in SPAN_TAG.findall(normalized):
            upstream_expected = upstream_expected.replace(
                f'<error what="{spoken}">{surface}</error>', spoken
            )
            resolved = _resolved_span(text, surface)
            if resolved is None:
                return [], "", "alignment_unresolved"
            start, end = resolved
            recognized = _recognize_spans(surface)
            source_category = recognized[0][3] if recognized else "identifier"
            unit = _unit_from_category(
                mapping=mapping,
                source_category=source_category,
                surface=surface,
                start=start,
                end=end,
                format_name="official",
            )
            if unit is None:
                return [], "", f"unsupported_category:{source_category}"
            unit["features"]["upstream_spoken"] = spoken
            units.append(unit)
        return units, upstream_expected, ""

    if not isinstance(normalized, str):
        return [], "", "malformed_row"
    recognized = _recognize_spans(text)
    units: list[dict] = []
    for start, end, surface, source_category in recognized:
        unit = _unit_from_category(
            mapping=mapping,
            source_category=source_category,
            surface=surface,
            start=start,
            end=end,
            format_name="official",
        )
        if unit is None:
            continue
        units.append(unit)
    if not units:
        return [], normalized, "alignment_unresolved"
    return units, normalized, ""


def _projection_record(
    case: dict,
    *,
    source_path: Path,
    manifest: dict,
    mapping: dict,
    format_name: str,
) -> dict | tuple[str, str]:
    category = case.get("category")
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
    unit = _unit_from_category(
        mapping=mapping,
        source_category=str(category),
        surface=surface,
        start=start,
        end=end,
        format_name=format_name,
        identity_example=bool(case.get("identity_example", False)),
    )
    if unit is None:
        return "unsupported_category", str(category)
    return _build_record(
        source_id=source_id,
        text=text,
        upstream_expected=upstream_expected,
        units=[unit],
        language=case.get("language", "en"),
        locale=case.get("locale", "en-US"),
        benchmark=manifest["name"],
        manifest=manifest,
        source_path=source_path,
        source_split=case.get("source_split"),
        notes=case.get("projection_notes", ""),
        format_name=format_name,
        identity_example=bool(case.get("identity_example", False)),
    )


def _build_record(
    *,
    source_id: str,
    text: str,
    upstream_expected: str | None,
    units: list[dict],
    language: str,
    locale: str,
    benchmark: str,
    manifest: dict,
    source_path: Path,
    source_split: str | None,
    notes: str,
    format_name: str,
    identity_example: bool = False,
) -> dict:
    payload_hash = sha256_text(
        "\n".join(
            [source_id, text, upstream_expected or "", language, locale, format_name]
        )
    )
    return {
        "id": f"{benchmark.replace('_', '-')}-{source_id.replace(':', '-')}",
        "schema_version": "1.0.0",
        "taxonomy_version": "1.0.0",
        "policy_version": "1.0.0",
        "language": language,
        "locale": locale,
        "split": "candidate",
        "family_id": f"{benchmark.replace('_', '-')}-{source_id.replace(':', '-')}",
        "status": "quarantine",
        "input": text,
        "expected_output": None,
        "source": {
            "benchmark": benchmark,
            "source_id": source_id,
            "source_version": manifest["revision"],
            "source_url": manifest["source_url"],
            "license": manifest["license"],
            "source_hash": f"sha256:{payload_hash}",
            "source_file": str(source_path.name),
            "source_split": source_split,
            "upstream_expected": upstream_expected,
            "projection_notes": notes,
            "identity_example": identity_example,
            "import_format": format_name,
            "importer_version": "1.0.0",
        },
        "units": units,
        "negative_for": [],
        "notes": notes or "Imported from Proteno; adjudicate before promotion.",
    }


def import_proteno(path: str | Path, *, format: str = "auto") -> ImportResult:
    manifests = source_manifest_map()
    mapping = load_mapping("proteno").get("mappings", {})
    source_path = Path(path)
    rows, format_name, language_info, source_files = _iter_rows(source_path, format)

    if format_name == "official":
        assert language_info is not None
        language, locale, manifest_name = language_info
        manifest = manifests[manifest_name]
        train_cutoff = int(len(rows) * 0.6)
    else:
        manifest = manifests["proteno"]
        language = locale = ""
        train_cutoff = 0

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
        if format_name != "official":
            created = _projection_record(
                case,
                source_path=source_path,
                manifest=manifest,
                mapping=mapping,
                format_name=format_name,
            )
        else:
            text = case.get("input")
            normalized = case.get("normalized")
            if not isinstance(text, str) or not isinstance(normalized, str):
                created = (
                    "malformed_row",
                    "official rows must contain string input and normalized values",
                )
            else:
                units, upstream_expected, issue = _official_units(
                    text=text,
                    normalized=normalized,
                    mapping=mapping,
                )
                if issue:
                    created = (issue, text)
                else:
                    source_id = f"proteno:{language}:{index}"
                    created = _build_record(
                        source_id=source_id,
                        text=text,
                        upstream_expected=upstream_expected,
                        units=units,
                        language=language,
                        locale=locale,
                        benchmark=manifest_name,
                        manifest=manifest,
                        source_path=Path(source_files[0]),
                        source_split="upstream_train"
                        if index <= train_cutoff
                        else "upstream_eval",
                        notes=f"Official Proteno paired-list import from {source_path.name}.",
                        format_name="official",
                    )
        if isinstance(created, tuple):
            reason, detail = created
            exclusions.append(
                {
                    "source_id": str(
                        case.get("case_id") or case.get("row_index") or index
                    ),
                    "reason": reason,
                    "detail": detail,
                }
            )
            continue
        records.append(created)
    diagnostics = build_import_diagnostics(
        records=records,
        exclusions=exclusions,
        source_rows=len(rows),
        source_hashes=[
            record.get("source", {}).get("source_hash", "") for record in records
        ],
    )
    diagnostics["format"] = format_name
    diagnostics["source_files"] = sorted(source_files)
    return ImportResult(
        records=records,
        exclusions=exclusions,
        source_rows=len(rows),
        diagnostics=diagnostics,
    )
