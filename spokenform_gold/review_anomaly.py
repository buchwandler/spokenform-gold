"""Deterministic review anomaly signals that never decide Gold annotations."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Iterable

_NORMALIZATION_CATEGORIES = {
    "abbreviation",
    "acronym",
    "cardinal",
    "chemical",
    "currency",
    "date",
    "decimal",
    "fraction",
    "math_expression",
    "measurement_unit",
    "ordinal",
    "phone",
    "product_code",
    "roman_numeral",
    "score_or_range",
    "serial_or_plate",
    "time",
    "url_or_email",
    "version",
    "Version Numbers",
    "Fractions",
    "Dates",
    "Times",
    "Decimals",
    "Units",
}


def _annotation(row: dict) -> dict:
    value = row.get("annotation")
    return value if isinstance(value, dict) else {}


def _status(row: dict) -> str:
    return str(_annotation(row).get("status") or row.get("status") or "")


def _oracle(row: dict) -> dict:
    value = _annotation(row).get("oracle")
    return value if isinstance(value, dict) else {}


def _digest(value: object) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_review_anomaly_report(
    review_rows: Iterable[dict],
    *,
    source_rows: Iterable[dict] = (),
    slot: str | None = None,
    substantial_packet_size: int = 10,
) -> dict:
    """Return suspicious uniform-review signals for a completed packet."""
    rows = [dict(row) for row in review_rows]
    sources = [dict(row) for row in source_rows]
    signals: list[dict] = []
    if not rows:
        return {
            "slot": slot,
            "cases": 0,
            "ready": True,
            "fresh_review_required": False,
            "signals": [],
        }

    statuses = Counter(_status(row) for row in rows)
    if len(rows) >= substantial_packet_size and len(statuses) == 1:
        signals.append(
            {
                "code": "uniform_status",
                "case_ids": [row.get("case_id") for row in rows],
                "status": next(iter(statuses)),
            }
        )

    rationales = [
        row.get("rationale") or (row.get("review") or {}).get("rationale")
        for row in rows
    ]
    nonempty_rationales = [
        value for value in rationales if isinstance(value, str) and value
    ]
    if (
        len(nonempty_rationales) >= substantial_packet_size
        and len(set(nonempty_rationales)) == 1
    ):
        signals.append(
            {
                "code": "uniform_rationale",
                "case_ids": [row.get("case_id") for row in rows],
            }
        )

    source_categories = {
        category
        for row in sources
        for unit in row.get("units", [])
        if isinstance(unit, dict)
        for category in [unit.get("source_category") or unit.get("category")]
        if isinstance(category, str)
    }
    if (
        source_categories & _NORMALIZATION_CATEGORIES
        and statuses
        and set(statuses) == {"no_change"}
    ):
        signals.append(
            {
                "code": "uniform_no_change_normalization_packet",
                "case_ids": [row.get("case_id") for row in rows],
                "source_categories": sorted(
                    source_categories & _NORMALIZATION_CATEGORIES
                ),
            }
        )

    empty_units = []
    for row in rows:
        annotation = _annotation(row)
        units = annotation.get("units", [])
        if units:
            continue
        text = str(row.get("input", ""))
        if re.search(r"\d|[@#$%€£$+_=]", text):
            empty_units.append(row.get("case_id"))
    if len(empty_units) == len(rows) and empty_units:
        signals.append(
            {
                "code": "units_always_empty_for_numeric_or_symbol_input",
                "case_ids": empty_units,
            }
        )

    identical_outputs = [
        _oracle(row).get("canonical_output")
        for row in rows
        if _oracle(row).get("canonical_output") is not None
    ]
    if (
        identical_outputs
        and len(identical_outputs) == len(rows)
        and all(
            output == row.get("input") for output, row in zip(identical_outputs, rows)
        )
    ):
        signals.append(
            {
                "code": "canonical_output_always_equals_input",
                "case_ids": [row.get("case_id") for row in rows],
            }
        )

    oracle_digests = [_digest(_oracle(row)) for row in rows]
    if len(rows) >= substantial_packet_size and len(set(oracle_digests)) == 1:
        signals.append(
            {
                "code": "repeated_oracle_object",
                "case_ids": [row.get("case_id") for row in rows],
            }
        )

    return {
        "slot": slot,
        "cases": len(rows),
        "ready": not signals,
        "fresh_review_required": bool(signals),
        "signals": signals,
    }
