from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path

from .io import read_json


def load_targets(path: str | Path | None):
    if not path:
        return {}
    return read_json(path)


def build_coverage(records, targets=None):
    targets = targets or {}
    cat_units = Counter()
    cat_records = Counter()
    cat_languages = defaultdict(set)
    cat_locales = defaultdict(set)
    cat_status = defaultdict(Counter)
    cat_patterns = defaultdict(Counter)
    negative = Counter()

    for record in records:
        for category in record.get("negative_for", []):
            negative[category] += 1
        seen = set()
        for unit in record.get("units", []):
            category = unit.get("category")
            if not category:
                continue
            cat_units[category] += 1
            cat_languages[category].add(record.get("language"))
            cat_locales[category].add(record.get("locale"))
            cat_status[category][record.get("status")] += 1
            pattern = unit.get("features", {}).get("surface_pattern")
            if pattern:
                cat_patterns[category][pattern] += 1
            seen.add(category)
        for category in seen:
            cat_records[category] += 1

    configured = set(targets.get("categories", {}))
    categories = sorted(set(cat_units) | configured)
    defaults = targets.get("default", {})
    target_languages = set(targets.get("languages", []))
    req_patterns = targets.get("required_patterns", {})

    rows, gaps = [], []
    for category in categories:
        override = targets.get("categories", {}).get(category, {})
        min_units = override.get("min_units", defaults.get("min_units", 0))
        min_ambiguous = override.get("min_ambiguous", defaults.get("min_ambiguous", 0))
        min_negative = override.get(
            "min_negative_controls", defaults.get("min_negative_controls", 0)
        )
        missing_languages = sorted(target_languages - cat_languages[category])
        missing_patterns = sorted(
            set(req_patterns.get(category, [])) - set(cat_patterns[category])
        )

        rows.append(
            {
                "category": category,
                "records": cat_records[category],
                "units": cat_units[category],
                "languages": sorted(
                    value for value in cat_languages[category] if value
                ),
                "locales": sorted(value for value in cat_locales[category] if value),
                "statuses": dict(cat_status[category]),
                "negative_controls": negative[category],
                "patterns": dict(cat_patterns[category]),
                "missing_languages": missing_languages,
                "missing_patterns": missing_patterns,
            }
        )

        if cat_units[category] < min_units:
            gaps.append(
                {
                    "category": category,
                    "kind": "low_volume",
                    "have": cat_units[category],
                    "need": min_units,
                }
            )
        if cat_status[category].get("ambiguous", 0) < min_ambiguous:
            gaps.append(
                {
                    "category": category,
                    "kind": "ambiguous",
                    "have": cat_status[category].get("ambiguous", 0),
                    "need": min_ambiguous,
                }
            )
        if negative[category] < min_negative:
            gaps.append(
                {
                    "category": category,
                    "kind": "negative_controls",
                    "have": negative[category],
                    "need": min_negative,
                }
            )
        for language in missing_languages:
            gaps.append({"category": category, "kind": "language", "missing": language})
        for pattern in missing_patterns:
            gaps.append(
                {"category": category, "kind": "surface_pattern", "missing": pattern}
            )

    return {
        "records": len(records),
        "categories_observed": len(cat_units),
        "categories_targeted": len(configured),
        "coverage": rows,
        "gaps": gaps,
    }
