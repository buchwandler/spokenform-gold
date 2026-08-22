from __future__ import annotations

import hashlib
import itertools
import json
import unicodedata
from typing import Any

COMPARISON_PROFILE = "sentence-exact-v1"
ORACLE_SCHEMA_VERSION = "1.0.0"


def normalize_text(value: str | None) -> str:
    """Apply the frozen sentence-exact-v1 comparison profile."""
    if value is None:
        return ""
    return " ".join(unicodedata.normalize("NFKC", value).split()).casefold()


def canonical_unit_reconstruction(record: dict[str, Any]) -> str | None:
    """Render input by replacing annotated units with their canonical forms."""
    original = record.get("input")
    units = sorted(record.get("units", []), key=lambda unit: unit.get("start", 0))
    if not isinstance(original, str):
        return None
    if not units:
        return original
    cursor = 0
    parts: list[str] = []
    for unit in units:
        start = unit.get("start")
        end = unit.get("end")
        canonical = unit.get("canonical")
        if not isinstance(start, int) or not isinstance(end, int):
            return None
        if not isinstance(canonical, str):
            return None
        parts.append(original[cursor:start])
        parts.append(canonical)
        cursor = end
    parts.append(original[cursor:])
    return "".join(parts)


def _legacy_unit_variants(record: dict[str, Any]) -> set[str]:
    """Return implicit Cartesian variants for migration diagnostics only."""
    units = sorted(record.get("units", []), key=lambda unit: unit.get("start", 0))
    if not units:
        expected = record.get("expected_output")
        return {expected} if isinstance(expected, str) else set()
    options: list[list[str]] = []
    for unit in units:
        values = list(unit.get("accepted", []))
        canonical = unit.get("canonical")
        if isinstance(canonical, str):
            values.append(canonical)
        deduped: list[str] = []
        seen: set[str] = set()
        for value in values:
            if not isinstance(value, str) or not value.strip():
                continue
            key = normalize_text(value)
            if key not in seen:
                deduped.append(value)
                seen.add(key)
        options.append(deduped or [str(unit.get("surface", ""))])
    rendered: set[str] = set()
    original = record.get("input", "")
    for replacements in itertools.product(*options):
        cursor = 0
        parts: list[str] = []
        for unit, replacement in zip(units, replacements):
            start, end = unit["start"], unit["end"]
            parts.extend((original[cursor:start], replacement))
            cursor = end
        parts.append(original[cursor:])
        rendered.add("".join(parts))
    expected = record.get("expected_output")
    if isinstance(expected, str):
        rendered.add(expected)
    return rendered


def explicit_accepted_outputs(record: dict[str, Any]) -> tuple[set[str], bool]:
    """Return normalized explicit outputs and whether the record is legacy."""
    oracle = record.get("oracle")
    if isinstance(oracle, dict) and isinstance(oracle.get("accepted_outputs"), list):
        return {
            normalize_text(value)
            for value in oracle["accepted_outputs"]
            if isinstance(value, str)
        }, False
    return {normalize_text(value) for value in _legacy_unit_variants(record)}, True


def oracle_assertion(record: dict[str, Any]) -> dict[str, Any]:
    """Return volatile-metadata-free content covered by oracle_hash."""
    oracle = record.get("oracle") or {}
    return {
        "language": record.get("language"),
        "locale": record.get("locale"),
        "input": record.get("input"),
        "status": record.get("status"),
        "units": record.get("units", []),
        "oracle": oracle,
        "policy_version": record.get("policy_version"),
        "taxonomy_version": record.get("taxonomy_version"),
        "comparison_profile": COMPARISON_PROFILE,
    }


def oracle_hash(record: dict[str, Any]) -> str:
    payload = json.dumps(
        oracle_assertion(record),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def interpretation_semantic_key(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
