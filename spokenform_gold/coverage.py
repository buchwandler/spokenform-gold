from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path

from .io import read_json


def load_targets(path: str | Path | None, profile: str | None = None):
    if not path:
        return {}
    targets = read_json(path)
    if profile and profile != "none":
        profiles = targets.get("language_profiles", {})
        if profile not in profiles:
            raise ValueError(
                f"unknown language profile {profile!r}; "
                f"expected one of {sorted(profiles)}"
            )
        targets = {
            **targets,
            "languages": profiles[profile],
            "language_profile": profile,
        }
    return targets


def _provenance_class(record: dict) -> str:
    sources = record.get("source_observations") or [record.get("source", {})]
    source = next((item for item in sources if isinstance(item, dict)), {})
    if source.get("benchmark") == "spokenform_translation" or source.get(
        "translation_parent_record_id"
    ):
        return (
            "translation_equivalent"
            if source.get("translation_relation") == "equivalent"
            else "translation_adapted"
        )
    if source.get("benchmark") == "spokenform_curated":
        return "native_curated"
    return "native_upstream_external"


def build_coverage(records, targets=None):
    records = list(records)
    targets = targets or {}
    cat_units = Counter()
    cat_records = Counter()
    cat_languages = defaultdict(set)
    cat_locales = defaultdict(set)
    cat_status = defaultdict(Counter)
    cat_patterns = defaultdict(Counter)
    negative = Counter()

    provenance = Counter()
    category_provenance = defaultdict(Counter)
    language_locales = Counter()
    for record in records:
        provenance_class = _provenance_class(record)
        provenance[provenance_class] += 1
        language_locales[f"{record.get('language')}:{record.get('locale')}"] += 1
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
            category_provenance[category][provenance_class] += 1

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
                "provenance": dict(sorted(category_provenance[category].items())),
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
        "language_profile": targets.get("language_profile", "stable"),
        "language_locales": dict(sorted(language_locales.items())),
        "provenance": dict(sorted(provenance.items())),
        "translation_derived_records": sum(
            value for key, value in provenance.items() if key.startswith("translation_")
        ),
        "translation_derived_fraction": (
            sum(
                value
                for key, value in provenance.items()
                if key.startswith("translation_")
            )
            / len(records)
            if records
            else 0.0
        ),
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
