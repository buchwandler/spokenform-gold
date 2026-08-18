from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path

RELEASE_SPLITS = ("train", "dev", "test")


def _normalized_ratios(
    train_ratio: float, dev_ratio: float, test_ratio: float
) -> list[tuple[str, float]]:
    total = train_ratio + dev_ratio + test_ratio
    if total <= 0:
        raise ValueError("split ratios must sum to more than 0")
    return [
        ("train", train_ratio / total),
        ("dev", dev_ratio / total),
        ("test", test_ratio / total),
    ]


def load_split_registry(path: str | Path) -> dict:
    target = Path(path)
    if not target.exists():
        return {"schema_version": "1", "seed": None, "families": {}}
    return json.loads(target.read_text(encoding="utf-8"))


def write_split_registry(path: str | Path, registry: dict) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(registry, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _assignment_from_hash(
    family_id: str, *, seed: int, ratios: list[tuple[str, float]]
) -> str:
    digest = hashlib.sha256(f"{seed}:{family_id}".encode()).digest()
    bucket = int.from_bytes(digest[:8], "big") / 2**64
    running = 0.0
    for split_name, ratio in ratios:
        running += ratio
        if bucket < running:
            return split_name
    return ratios[-1][0]


def resolve_family_assignments(
    records: list[dict],
    *,
    registry_path: str | Path,
    seed: int,
    train_ratio: float = 0.70,
    dev_ratio: float = 0.15,
    test_ratio: float = 0.15,
) -> dict:
    ratios = _normalized_ratios(train_ratio, dev_ratio, test_ratio)
    registry = load_split_registry(registry_path)
    families = dict(registry.get("families", {}))
    if registry.get("seed") is None:
        registry["seed"] = str(seed)
    elif str(registry.get("seed")) != str(seed):
        raise ValueError(
            f"split registry seed {registry.get('seed')!r} does not match requested seed {seed!r}"
        )

    grouped: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        family_id = record.get("family_id")
        if not family_id:
            raise ValueError("all records require family_id for splitting")
        grouped[family_id].append(record)

    for family_id, items in grouped.items():
        assigned = families.get(family_id)
        record_splits = {
            item.get("split") for item in items if item.get("split") in RELEASE_SPLITS
        }
        if assigned is not None:
            if record_splits and record_splits != {assigned}:
                raise ValueError(
                    f"family {family_id!r} is frozen to {assigned!r} but records contain {sorted(record_splits)!r}"
                )
            continue
        if len(record_splits) > 1:
            raise ValueError(
                f"family {family_id!r} crosses splits in source data: {sorted(record_splits)!r}"
            )
        if record_splits:
            families[family_id] = next(iter(record_splits))
        else:
            families[family_id] = _assignment_from_hash(
                family_id, seed=seed, ratios=ratios
            )

    registry["families"] = dict(sorted(families.items()))
    write_split_registry(registry_path, registry)
    return registry


def split_records(
    records: list[dict],
    *,
    registry_path: str | Path,
    seed: int,
    train_ratio: float = 0.70,
    dev_ratio: float = 0.15,
    test_ratio: float = 0.15,
) -> dict[str, list[dict]]:
    registry = resolve_family_assignments(
        records,
        registry_path=registry_path,
        seed=seed,
        train_ratio=train_ratio,
        dev_ratio=dev_ratio,
        test_ratio=test_ratio,
    )
    families = registry["families"]
    output = {"train": [], "dev": [], "test": []}
    for record in records:
        family_id = record["family_id"]
        split_name = families[family_id]
        if split_name not in output:
            raise ValueError(
                f"split registry assigned unsupported split {split_name!r} for family {family_id!r}"
            )
        updated = dict(record)
        updated["split"] = split_name
        output[split_name].append(updated)

    for split_name, split_records_list in output.items():
        split_records_list.sort(key=lambda record: record.get("id", ""))
    return output
