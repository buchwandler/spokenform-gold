from __future__ import annotations

import random
from collections import defaultdict


def split_records(
    records: list[dict],
    *,
    train_ratio: float,
    dev_ratio: float,
    test_ratio: float,
    seed: int,
) -> dict[str, list[dict]]:
    if not records:
        return {"train": [], "dev": [], "test": []}
    total = train_ratio + dev_ratio + test_ratio
    if total <= 0:
        raise ValueError("split ratios must sum to more than 0")

    grouped: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        family_id = record.get("family_id")
        if not family_id:
            raise ValueError("all records require family_id for splitting")
        grouped[family_id].append(record)

    family_items = list(grouped.items())
    rnd = random.Random(seed)
    rnd.shuffle(family_items)
    family_items.sort(key=lambda item: (len(item[1]), item[0]))
    rnd.shuffle(family_items)

    total_records = sum(len(items) for _, items in family_items)
    target_counts = {
        "train": total_records * (train_ratio / total),
        "dev": total_records * (dev_ratio / total),
        "test": total_records * (test_ratio / total),
    }
    assigned_counts = {"train": 0, "dev": 0, "test": 0}
    output = {"train": [], "dev": [], "test": []}

    for family_id, family_records in sorted(
        family_items,
        key=lambda item: (-len(item[1]), item[0]),
    ):
        split_name = min(
            ("train", "dev", "test"),
            key=lambda name: (
                assigned_counts[name] - target_counts[name],
                assigned_counts[name],
                name,
            ),
        )
        assigned_counts[split_name] += len(family_records)
        for record in family_records:
            updated = dict(record)
            updated["split"] = split_name
            output[split_name].append(updated)

    for split_name in output:
        output[split_name].sort(key=lambda record: record.get("id", ""))
    return output
