from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from .control_validation import validate_control_records
from .evaluation_profiles import resolve_profile
from .io import read_jsonl

ControlPrepare = Callable[[str, str, str, dict[str, Any]], str | dict[str, Any]]


def _output_and_rules(value: str | dict[str, Any]) -> tuple[str, set[str]]:
    if isinstance(value, str):
        return value, set()
    if not isinstance(value, dict) or not isinstance(value.get("output"), str):
        raise TypeError("control prepare results must be strings or output objects")
    rules = value.get("rules", value.get("owners", []))
    if not isinstance(rules, list) or not all(isinstance(item, str) for item in rules):
        raise TypeError("control prepare result rules must be list[str]")
    return value["output"], set(rules)


def build_control_predictions(
    records: Iterable[dict[str, Any]], prepare: ControlPrepare
) -> list[dict[str, Any]]:
    predictions: list[dict[str, Any]] = []
    for record in records:
        profiles: dict[str, dict[str, Any]] = {}
        for expectation in record["expectations"]:
            profile_id = expectation["profile_id"]
            profile = resolve_profile(profile_id)
            output, rules = _output_and_rules(
                prepare(record["input"], record["language"], record["locale"], profile)
            )
            profiles[profile_id] = {"output": output, "rules": sorted(rules)}
        predictions.append({"id": record["id"], "profiles": profiles})
    return predictions


def load_control_predictions(paths: Iterable[str | Path]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for path in paths:
        for item in read_jsonl(path):
            record_id = item.get("id")
            if not isinstance(record_id, str) or record_id in result:
                raise ValueError(f"duplicate or missing control prediction id: {record_id!r}")
            profiles = item.get("profiles")
            if not isinstance(profiles, dict):
                raise TypeError(f"control prediction {record_id!r} requires profiles")
            result[record_id] = item
    return result


def score_control_records(
    records: list[dict[str, Any]],
    predictions: dict[str, dict[str, Any]],
    *,
    validate: bool = True,
) -> dict[str, Any]:
    if validate:
        errors = validate_control_records(records)
        if errors:
            raise ValueError("control validation failed: " + "; ".join(errors))
    results: list[dict[str, Any]] = []
    by_control: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_language: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        prediction = predictions.get(record["id"], {})
        profile_predictions = prediction.get("profiles", {})
        for expectation in record["expectations"]:
            profile_id = expectation["profile_id"]
            actual = profile_predictions.get(profile_id, {})
            output = actual.get("output") if isinstance(actual, dict) else None
            rules = set(actual.get("rules", [])) if isinstance(actual, dict) else set()
            required = set(expectation["required_rules"])
            forbidden = set(expectation["forbidden_rules"])
            output_match = output == expectation["expected_output"]
            required_match = required <= rules
            forbidden_violation = bool(forbidden & rules)
            result = {
                "id": record["id"],
                "control": record["control"],
                "language": record["language"],
                "profile_id": profile_id,
                "output": output,
                "expected_output": expectation["expected_output"],
                "output_match": output_match,
                "required_rules_match": required_match,
                "forbidden_rule_violation": forbidden_violation,
                "full_match": output_match and required_match and not forbidden_violation,
            }
            results.append(result)
            by_control[record["control"]].append(result)
            by_language[record["language"]].append(result)

    def summarize(items: list[dict[str, Any]]) -> dict[str, Any]:
        count = len(items)
        return {
            "expectations": count,
            "output_accuracy": sum(item["output_match"] for item in items) / count
            if count
            else 0.0,
            "required_rule_accuracy": sum(
                item["required_rules_match"] for item in items
            )
            / count
            if count
            else 0.0,
            "forbidden_rule_violations": sum(
                item["forbidden_rule_violation"] for item in items
            ),
            "full_accuracy": sum(item["full_match"] for item in items) / count
            if count
            else 0.0,
        }

    summary = summarize(results)
    return {
        "cases": len(records),
        **summary,
        "by_control": {
            key: summarize(value) for key, value in sorted(by_control.items())
        },
        "by_language": {
            key: summarize(value) for key, value in sorted(by_language.items())
        },
        "false_positive_control_failures": sum(
            item["forbidden_rule_violation"]
            for item in results
            if not item["output_match"] or item["forbidden_rule_violation"]
        ),
        "results": results,
    }


def write_control_predictions(path: str | Path, predictions: list[dict[str, Any]]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        for prediction in predictions:
            handle.write(json.dumps(prediction, ensure_ascii=False, sort_keys=True) + "\n")
