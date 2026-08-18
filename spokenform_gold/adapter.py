from __future__ import annotations

from collections.abc import Callable, Iterable


def build_prediction_records(
    records: Iterable[dict], prepare_fn: Callable[[str, str, str], str]
) -> list[dict]:
    predictions = []
    for record in records:
        predictions.append(
            {
                "id": record["id"],
                "output": prepare_fn(
                    record["input"], record["language"], record["locale"]
                ),
            }
        )
    return predictions
