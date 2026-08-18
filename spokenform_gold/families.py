from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable


def sentence_skeleton(record: dict) -> str:
    text = record.get("input", "")
    units = sorted(
        record.get("units", []),
        key=lambda unit: (unit.get("start", 0), unit.get("end", 0)),
        reverse=True,
    )
    for unit in units:
        start, end = unit.get("start"), unit.get("end")
        if (
            not isinstance(start, int)
            or not isinstance(end, int)
            or not 0 <= start <= end <= len(text)
        ):
            continue
        text = text[:start] + f"<{unit.get('category', 'UNIT')}>" + text[end:]
    return re.sub(r"\s+", " ", text).strip().casefold()


def family_signature(record: dict) -> dict:
    units = record.get("units", [])
    categories = tuple(unit.get("category", "") for unit in units)
    patterns = tuple(
        unit.get("features", {}).get("surface_pattern", "") for unit in units
    )
    source = record.get("source", {})
    source_id = str(source.get("source_id", ""))
    parallel_root = source_id.rsplit(":", 1)[0] if ":" in source_id else ""
    return {
        "language": record.get("language", ""),
        "locale": record.get("locale", ""),
        "categories": categories,
        "surface_patterns": patterns,
        "sentence_skeleton": sentence_skeleton(record),
        "parallel_source_root": parallel_root,
        "source_benchmark": source.get("benchmark", ""),
    }


def suggest_families(records: Iterable[dict]) -> list[dict]:
    items = []
    for record in sorted(records, key=lambda item: item.get("id", "")):
        signature = family_signature(record)
        if signature["parallel_source_root"]:
            key = (
                "parallel",
                signature["source_benchmark"],
                signature["parallel_source_root"],
            )
            reason = "shared source template root"
        else:
            key = (
                "skeleton",
                signature["language"],
                signature["locale"],
                signature["categories"],
                signature["surface_patterns"],
                signature["sentence_skeleton"],
            )
            reason = "same locale and conservative sentence skeleton"
        items.append((key, reason, record, signature))

    groups: dict[tuple, list[tuple[str, dict]]] = defaultdict(list)
    reasons: dict[tuple, str] = {}
    for key, reason, record, signature in items:
        groups[key].append((record.get("id", ""), signature))
        reasons[key] = reason

    suggestions = []
    for index, key in enumerate(sorted(groups, key=str), 1):
        members = sorted(groups[key], key=lambda item: item[0])
        suggestions.append(
            {
                "suggested_family_id": f"suggested-family-{index:04d}",
                "reason": reasons[key],
                "key": [str(value) for value in key],
                "members": [member_id for member_id, _ in members],
                "signatures": [signature for _, signature in members],
                "requires_review": True,
            }
        )
    return suggestions
