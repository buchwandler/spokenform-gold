from __future__ import annotations

import itertools
import json
import unicodedata
from collections import Counter
from pathlib import Path
from collections.abc import Iterable


EXCLUDED_STATUSES = {"ambiguous", "quarantine"}
SCORABLE_STATUSES = {"gold", "multi_valid", "policy_choice", "no_change"}


def normalize_text(value: str | None) -> str:
    if value is None:
        return ""
    return " ".join(unicodedata.normalize("NFKC", value).split()).casefold()


def load_predictions(path: str | Path) -> dict[str, str]:
    predictions: dict[str, str] = {}
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise ValueError(f"{path}:{line_number}: prediction must be an object")
            record_id = payload.get("id")
            output = payload.get("output")
            if not isinstance(record_id, str) or not isinstance(output, str):
                raise ValueError(
                    f"{path}:{line_number}: prediction requires string id and output"
                )
            predictions[record_id] = output
    return predictions


def _render_variants(record: dict) -> set[str]:
    units = sorted(record.get("units", []), key=lambda unit: unit.get("start", 0))
    if not units:
        expected = record.get("expected_output")
        return {expected} if isinstance(expected, str) else set()

    options: list[list[str]] = []
    for unit in units:
        accepted = [
            value
            for value in unit.get("accepted", [])
            if isinstance(value, str) and value.strip()
        ]
        canonical = unit.get("canonical")
        if isinstance(canonical, str) and canonical.strip():
            accepted.append(canonical)
        deduped = []
        seen = set()
        for value in accepted:
            key = normalize_text(value)
            if key not in seen:
                deduped.append(value)
                seen.add(key)
        options.append(deduped or [unit.get("surface", "")])

    rendered: set[str] = set()
    original = record.get("input", "")
    for variant_tuple in itertools.product(*options):
        cursor = 0
        parts: list[str] = []
        for unit, replacement in zip(units, variant_tuple):
            start = unit["start"]
            end = unit["end"]
            parts.append(original[cursor:start])
            parts.append(replacement)
            cursor = end
        parts.append(original[cursor:])
        rendered.add("".join(parts))
        if len(rendered) > 256:
            break
    if isinstance(record.get("expected_output"), str):
        rendered.add(record["expected_output"])
    return rendered


def _status_bucket(target: dict[str, dict], key: str) -> dict:
    return target.setdefault(
        key,
        {
            "records": 0,
            "canonical_matches": 0,
            "accepted_matches": 0,
        },
    )


def evaluate_records(
    records: Iterable[dict], predictions: dict[str, str]
) -> list[dict]:
    results: list[dict] = []
    for record in records:
        status = record.get("status")
        if status in EXCLUDED_STATUSES or record.get("split") == "candidate":
            continue
        if status not in SCORABLE_STATUSES:
            continue
        predicted = predictions.get(record.get("id"))
        if predicted is None:
            predicted = ""
        normalized_prediction = normalize_text(predicted)
        canonical_target = normalize_text(record.get("expected_output"))
        accepted_targets = {normalize_text(value) for value in _render_variants(record)}
        is_canonical = normalized_prediction == canonical_target
        is_accepted = is_canonical or normalized_prediction in accepted_targets
        results.append(
            {
                "id": record.get("id"),
                "status": status,
                "language": record.get("language"),
                "locale": record.get("locale"),
                "input": record.get("input"),
                "expected_output": record.get("expected_output"),
                "prediction": predicted,
                "canonical_match": is_canonical,
                "accepted_match": is_accepted,
                "accepted_variants": sorted(_render_variants(record)),
            }
        )
    return results


def score_records(
    records: Iterable[dict], predictions: dict[str, str], *, mode: str = "canonical"
) -> dict:
    if mode not in {"canonical", "accepted"}:
        raise ValueError("mode must be canonical or accepted")

    record_list = list(records)
    per_category: dict[str, dict] = {}
    per_language: dict[str, dict] = {}
    per_locale: dict[str, dict] = {}
    per_status: dict[str, dict] = {}
    totals = Counter()
    scorable_records = 0
    canonical_matches = 0
    accepted_matches = 0
    scorable_units = 0
    unit_canonical_matches = 0
    no_change_records = 0
    no_change_matches = 0
    no_change_mutations = 0
    missing_predictions = []

    evaluation = {
        item["id"]: item for item in evaluate_records(record_list, predictions)
    }

    for record in record_list:
        status = record.get("status")
        totals[status] += 1
        if status in EXCLUDED_STATUSES or record.get("split") == "candidate":
            continue
        if status not in SCORABLE_STATUSES:
            continue

        scorable_records += 1
        detail = evaluation.get(record.get("id"))
        predicted = predictions.get(record.get("id"))
        if predicted is None:
            missing_predictions.append(record.get("id"))
        if detail is None:
            is_canonical = False
            is_accepted = False
        else:
            is_canonical = bool(detail["canonical_match"])
            is_accepted = bool(detail["accepted_match"])

        if is_canonical:
            canonical_matches += 1
        if is_accepted:
            accepted_matches += 1

        units = record.get("units", [])
        unit_count = max(len(units), 1 if status == "no_change" else 0)
        scorable_units += unit_count
        if is_canonical:
            unit_canonical_matches += unit_count

        for unit in units:
            category = unit.get("category", "unknown")
            bucket = _status_bucket(per_category, category)
            bucket["records"] += 1
            bucket["canonical_matches"] += int(is_canonical)
            bucket["accepted_matches"] += int(is_accepted)

        for key, target in (
            (record.get("language", "unknown"), per_language),
            (record.get("locale", "unknown"), per_locale),
            (status, per_status),
        ):
            bucket = _status_bucket(target, key)
            bucket["records"] += 1
            bucket["canonical_matches"] += int(is_canonical)
            bucket["accepted_matches"] += int(is_accepted)

        if status == "no_change":
            no_change_records += 1
            if is_canonical:
                no_change_matches += 1
            else:
                no_change_mutations += 1

    result = {
        "mode": mode,
        "records_total": len(record_list),
        "records_scorable": scorable_records,
        "sentence_canonical_accuracy": canonical_matches / scorable_records
        if scorable_records
        else 0.0,
        "unit_canonical_accuracy": unit_canonical_matches / scorable_units
        if scorable_units
        else 0.0,
        "accepted_variant_accuracy": accepted_matches / scorable_records
        if scorable_records
        else 0.0,
        "no_change_accuracy": no_change_matches / no_change_records
        if no_change_records
        else 0.0,
        "false_positive_normalization_rate": no_change_mutations / no_change_records
        if no_change_records
        else 0.0,
        "per_category": dict(sorted(per_category.items())),
        "per_language": dict(sorted(per_language.items())),
        "per_locale": dict(sorted(per_locale.items())),
        "per_status": dict(sorted(per_status.items())),
        "ambiguous_count": totals.get("ambiguous", 0),
        "quarantine_count": totals.get("quarantine", 0),
        "excluded_count": totals.get("ambiguous", 0)
        + totals.get("quarantine", 0)
        + totals.get("candidate", 0),
        "missing_prediction_ids": sorted(
            record_id for record_id in missing_predictions if record_id
        ),
        "record_results": [evaluation[key] for key in sorted(evaluation)],
    }
    if mode == "accepted":
        result["primary_accuracy"] = result["accepted_variant_accuracy"]
    else:
        result["primary_accuracy"] = result["sentence_canonical_accuracy"]
    return result
