from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from copy import deepcopy

from .coverage import build_coverage

REASON_SCORES = {
    "category_missing": 100,
    "category_below_minimum": 50,
    "required_pattern_missing": 40,
    "new_language_for_category": 30,
    "source_disagreement": 25,
    "multi_unit": 20,
    "ambiguity_family": 15,
    "rare_surface_pattern": 10,
    "cross_source_duplicate": 5,
    "metadata_only": -50,
    "broad_or_ambiguous_mapping": -30,
    "duplicate_exact_input_output": -20,
}


def _target_for_category(targets: dict, category: str) -> int:
    defaults = targets.get("default", {})
    override = targets.get("categories", {}).get(category, {})
    return int(override.get("min_units", defaults.get("min_units", 0)))


def _coverage_indexes(
    coverage: dict,
) -> tuple[dict, dict[str, set[str]], dict[str, set[str]]]:
    rows = {row.get("category"): row for row in coverage.get("coverage", [])}
    languages = {
        category: set(row.get("languages", [])) for category, row in rows.items()
    }
    patterns = {
        category: set(row.get("patterns", {})) for category, row in rows.items()
    }
    return rows, languages, patterns


def _record_categories(record: dict) -> set[str]:
    return {
        unit.get("category")
        for unit in record.get("units", [])
        if isinstance(unit, dict) and isinstance(unit.get("category"), str)
    }


def _conflict_ids(conflicts: Iterable[dict]) -> set[str]:
    result: set[str] = set()
    for conflict in conflicts:
        for item in conflict.get("items", []):
            if isinstance(item, dict) and isinstance(item.get("record_id"), str):
                result.add(item["record_id"])
        for variant in conflict.get("variants", []):
            for item in variant.get("members", []) if isinstance(variant, dict) else []:
                if isinstance(item, dict) and isinstance(item.get("record_id"), str):
                    result.add(item["record_id"])
    return result


def _duplicate_indexes(
    dedupe: dict,
) -> tuple[set[str], set[str], set[str], set[str]]:
    exact_pair_ids: set[str] = set()
    cross_source_ids: set[str] = set()
    duplicate_input_ids: set[str] = set()
    conflicting_output_ids: set[str] = set()
    for group in dedupe.get("exact_pair_groups", []):
        members = group.get("members", [])
        ids = {item.get("record_id") for item in members if item.get("record_id")}
        exact_pair_ids.update(ids)
        if len({item.get("benchmark") for item in members}) > 1:
            cross_source_ids.update(ids)
    for group in dedupe.get("exact_input_groups", []):
        members = group.get("members", [])
        ids = {item.get("record_id") for item in members if item.get("record_id")}
        duplicate_input_ids.update(ids)
        if len({item.get("benchmark") for item in members}) > 1:
            cross_source_ids.update(ids)
    for group in dedupe.get("conflicting_output_groups", []):
        for output in group.get("outputs", []):
            for member in output.get("members", []):
                record_id = member.get("record_id")
                if record_id:
                    conflicting_output_ids.add(record_id)
    return exact_pair_ids, cross_source_ids, duplicate_input_ids, conflicting_output_ids


def _add_reason(reasons: set[str], reason: str, score: int) -> int:
    if reason in reasons:
        return 0
    reasons.add(reason)
    return score


def build_candidate_ranking(
    candidates: Iterable[dict],
    reviewed: Iterable[dict],
    *,
    targets: dict | None = None,
    dedupe: dict | None = None,
    conflicts: Iterable[dict] | None = None,
) -> list[dict]:
    target_config = targets or {}
    coverage = build_coverage(list(reviewed), target_config)
    coverage_rows, category_languages, category_patterns = _coverage_indexes(coverage)
    conflict_ids = _conflict_ids(conflicts or [])
    (
        exact_pair_ids,
        cross_source_ids,
        duplicate_input_ids,
        conflicting_output_ids,
    ) = _duplicate_indexes(dedupe or {})
    conflict_ids.update(conflicting_output_ids)

    candidates_list = list(candidates)
    surface_counts = Counter(
        unit.get("features", {}).get("surface_pattern")
        for record in candidates_list
        for unit in record.get("units", [])
        if unit.get("features", {}).get("surface_pattern")
    )
    ranked: list[dict] = []
    for record in candidates_list:
        record_id = record.get("id")
        reasons: set[str] = set()
        priority = 0
        categories = sorted(_record_categories(record))
        for category in categories:
            row = coverage_rows.get(category, {})
            have_units = int(row.get("units", 0))
            if have_units == 0:
                priority += _add_reason(
                    reasons, "category_missing", REASON_SCORES["category_missing"]
                )
            elif have_units < _target_for_category(target_config, category):
                priority += _add_reason(
                    reasons,
                    "category_below_minimum",
                    REASON_SCORES["category_below_minimum"],
                )
            if record.get("language") not in category_languages.get(category, set()):
                priority += _add_reason(
                    reasons,
                    "new_language_for_category",
                    REASON_SCORES["new_language_for_category"],
                )

            missing_patterns = set(
                target_config.get("required_patterns", {}).get(category, [])
            ) - category_patterns.get(category, set())
            candidate_patterns = {
                unit.get("features", {}).get("surface_pattern")
                for unit in record.get("units", [])
                if unit.get("category") == category
            }
            if missing_patterns & candidate_patterns:
                priority += _add_reason(
                    reasons,
                    "required_pattern_missing",
                    REASON_SCORES["required_pattern_missing"],
                )
            if any(
                surface_counts.get(pattern, 0) <= 1
                for pattern in candidate_patterns
                if pattern
            ):
                priority += _add_reason(
                    reasons,
                    "rare_surface_pattern",
                    REASON_SCORES["rare_surface_pattern"],
                )

        if record_id in conflict_ids:
            priority += _add_reason(
                reasons, "source_disagreement", REASON_SCORES["source_disagreement"]
            )
        if len(record.get("units", [])) > 1:
            priority += _add_reason(reasons, "multi_unit", REASON_SCORES["multi_unit"])
        if record.get("ambiguity_family") or any(
            unit.get("features", {}).get("ambiguity_family")
            for unit in record.get("units", [])
        ):
            priority += _add_reason(
                reasons, "ambiguity_family", REASON_SCORES["ambiguity_family"]
            )
        if record_id in cross_source_ids:
            priority += _add_reason(
                reasons,
                "cross_source_duplicate",
                REASON_SCORES["cross_source_duplicate"],
            )
        if record_id in exact_pair_ids or (
            record_id in duplicate_input_ids and record_id not in cross_source_ids
        ):
            priority += _add_reason(
                reasons,
                "duplicate_exact_input_output",
                REASON_SCORES["duplicate_exact_input_output"],
            )
        if not record.get("units"):
            priority += _add_reason(
                reasons, "metadata_only", REASON_SCORES["metadata_only"]
            )
        if any(
            unit.get("mapping_status") in {"broader", "ambiguous"}
            for unit in record.get("units", [])
        ):
            priority += _add_reason(
                reasons,
                "broad_or_ambiguous_mapping",
                REASON_SCORES["broad_or_ambiguous_mapping"],
            )

        source = record.get("source") or {}
        ranked.append(
            {
                "record_id": record_id,
                "priority": priority,
                "reasons": sorted(reasons),
                "status": record.get("status"),
                "source": source.get("benchmark"),
                "language": record.get("language"),
                "locale": record.get("locale"),
                "categories": categories,
                "family_id": record.get("family_id"),
                "record": deepcopy(
                    {
                        key: value
                        for key, value in record.items()
                        if not key.startswith("_")
                    }
                ),
            }
        )

    ranked.sort(key=lambda item: (-item["priority"], item.get("record_id") or ""))
    return ranked


def export_review_batch(
    ranked_items: Iterable[dict],
    *,
    limit: int = 100,
    languages: set[str] | None = None,
    max_per_category: int | None = None,
    max_per_family_suggestion: int | None = None,
) -> list[dict]:
    if limit < 0:
        raise ValueError("limit must not be negative")
    selected: list[dict] = []
    language_counts = Counter()
    category_counts = Counter()
    family_counts = Counter()
    for item in sorted(
        ranked_items,
        key=lambda value: (-value.get("priority", 0), value.get("record_id", "")),
    ):
        if len(selected) >= limit:
            break
        language = item.get("language")
        if languages and language not in languages:
            continue
        categories = item.get("categories") or []
        if max_per_category is not None and any(
            category_counts[category] >= max_per_category for category in categories
        ):
            continue
        family_id = item.get("family_id") or ""
        if (
            max_per_family_suggestion is not None
            and family_counts[family_id] >= max_per_family_suggestion
        ):
            continue
        record = deepcopy(item.get("record"))
        if not isinstance(record, dict):
            continue
        record["review_priority"] = item.get("priority", 0)
        record["review_reasons"] = item.get("reasons", [])
        selected.append(record)
        language_counts[language] += 1
        for category in categories:
            category_counts[category] += 1
        family_counts[family_id] += 1
    return selected
