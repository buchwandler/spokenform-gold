from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def load_judge_predictions(path: str | Path) -> dict[str, str]:
    predictions: dict[str, str] = {}
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise ValueError(
                    f"{path}:{line_number}: judge prediction must be an object"
                )
            record_id = payload.get("id")
            label = payload.get("label")
            if not isinstance(record_id, str) or not isinstance(label, str):
                raise ValueError(
                    f"{path}:{line_number}: judge prediction requires string id and label"
                )
            if label not in {"accept", "reject"}:
                raise ValueError(
                    f"{path}:{line_number}: judge prediction label must be accept/reject"
                )
            predictions[record_id] = label
    return predictions


def _bucket(
    target: dict[str, dict[str, int]], key: str, actual: str, predicted: str
) -> None:
    bucket = target.setdefault(
        key,
        {
            "records": 0,
            "correct": 0,
            "accept_gold": 0,
            "reject_gold": 0,
        },
    )
    bucket["records"] += 1
    if actual == predicted:
        bucket["correct"] += 1
    if actual == "accept":
        bucket["accept_gold"] += 1
    else:
        bucket["reject_gold"] += 1


def _accuracy_table(target: dict[str, dict[str, int]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for key, bucket in sorted(target.items()):
        records = bucket["records"]
        result[key] = {
            **bucket,
            "accuracy": bucket["correct"] / records if records else 0.0,
        }
    return result


def build_judge_calibration(
    records: list[dict[str, Any]], predictions: dict[str, str]
) -> dict[str, Any]:
    record_ids = {record.get("id") for record in records}
    missing = sorted(
        record_id for record_id in record_ids if record_id not in predictions
    )
    unexpected = sorted(
        prediction_id
        for prediction_id in predictions
        if prediction_id not in record_ids
    )
    if missing:
        raise ValueError(f"missing judge predictions for ids: {missing}")
    if unexpected:
        raise ValueError(f"unexpected judge predictions for ids: {unexpected}")

    counts = Counter()
    by_category: dict[str, dict[str, int]] = {}
    by_language: dict[str, dict[str, int]] = {}
    by_ambiguity_family: dict[str, dict[str, int]] = {}
    confusion = defaultdict(int)

    for record in records:
        actual = record["human_label"]
        predicted = predictions[record["id"]]
        counts["records"] += 1
        counts[f"gold_{actual}"] += 1
        counts[f"predicted_{predicted}"] += 1
        confusion[f"{actual}_as_{predicted}"] += 1
        _bucket(by_category, record["category"], actual, predicted)
        _bucket(by_language, record["language"], actual, predicted)
        ambiguity_family = record.get("ambiguity_family") or "none"
        _bucket(by_ambiguity_family, ambiguity_family, actual, predicted)

    true_accept = confusion["accept_as_accept"]
    false_reject = confusion["accept_as_reject"]
    false_accept = confusion["reject_as_accept"]
    true_reject = confusion["reject_as_reject"]

    predicted_accept = true_accept + false_accept
    gold_accept = true_accept + false_reject
    gold_reject = true_reject + false_accept
    accuracy = (
        (true_accept + true_reject) / counts["records"] if counts["records"] else 0.0
    )
    precision = true_accept / predicted_accept if predicted_accept else 0.0
    recall = true_accept / gold_accept if gold_accept else 0.0
    false_acceptance_rate = false_accept / gold_reject if gold_reject else 0.0
    false_rejection_rate = false_reject / gold_accept if gold_accept else 0.0

    return {
        "records": counts["records"],
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "false_acceptance_rate": false_acceptance_rate,
        "false_rejection_rate": false_rejection_rate,
        "confusion": {
            "true_accept": true_accept,
            "false_reject": false_reject,
            "false_accept": false_accept,
            "true_reject": true_reject,
        },
        "per_category_accuracy": _accuracy_table(by_category),
        "per_language_accuracy": _accuracy_table(by_language),
        "per_ambiguity_family_accuracy": _accuracy_table(by_ambiguity_family),
    }
