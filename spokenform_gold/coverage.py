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


def build_control_coverage(records, targets=None):
    targets = targets or {}
    counts = defaultdict(Counter)
    languages = defaultdict(set)
    profiles = defaultdict(set)
    for record in records:
        control = record.get("control")
        if not control:
            continue
        counts[control]["records"] += 1
        languages[control].add(record.get("language"))
        for expectation in record.get("expectations", []):
            counts[control]["expectations"] += 1
            profiles[control].add(expectation.get("profile_id"))
            if expectation.get("required_rules") or expectation.get("forbidden_rules"):
                counts[control]["assertion_expectations"] += 1
    configured = targets.get("controls", {})
    rows = []
    gaps = []
    for control in sorted(set(counts) | set(configured)):
        requirement = configured.get(control, {})
        observed_languages = sorted(value for value in languages[control] if value)
        missing_languages = sorted(
            set(requirement.get("required_languages", [])) - set(observed_languages)
        )
        minimum_records = int(requirement.get("min_records", 0))
        row = {
            "control": control,
            "records": counts[control]["records"],
            "expectations": counts[control]["expectations"],
            "assertion_expectations": counts[control]["assertion_expectations"],
            "languages": observed_languages,
            "profiles": sorted(value for value in profiles[control] if value),
            "missing_languages": missing_languages,
        }
        rows.append(row)
        if counts[control]["records"] < minimum_records:
            gaps.append(
                {
                    "control": control,
                    "kind": "low_volume",
                    "have": counts[control]["records"],
                    "need": minimum_records,
                }
            )
        for language in missing_languages:
            gaps.append({"control": control, "kind": "language", "missing": language})
    return {
        "records": len(records),
        "controls_observed": len(counts),
        "controls_targeted": len(configured),
        "coverage": rows,
        "gaps": gaps,
    }
