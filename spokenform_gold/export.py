from __future__ import annotations

from pathlib import Path

from .io import write_json, write_jsonl
from .splitting import split_records


def export_family_safe_splits(
    records: list[dict],
    *,
    out_root: str | Path,
    seed: int | str = "spokenform-gold-v2",
    ratios: tuple[float, float, float] = (0.70, 0.15, 0.15),
    registry_path: str | Path | None = None,
) -> dict[str, list[dict]]:
    """Export consumer splits without adding split state to canonical records."""
    root = Path(out_root)
    root.mkdir(parents=True, exist_ok=True)
    registry = (
        Path(registry_path) if registry_path else root / "family_assignments.json"
    )
    numeric_seed = int.from_bytes(str(seed).encode("utf-8")[:8].ljust(8, b"0"), "big")
    split_map = split_records(
        [dict(record, split="candidate") for record in records],
        registry_path=registry,
        seed=numeric_seed,
        train_ratio=ratios[0],
        dev_ratio=ratios[1],
        test_ratio=ratios[2],
    )
    for name, rows in split_map.items():
        write_jsonl(root / name / "corpus.jsonl", rows)
    payload = {
        "schema_version": "2.0.0",
        "seed": str(seed),
        "ratios": list(ratios),
        "assignments": __import__("json")
        .loads(registry.read_text(encoding="utf-8"))
        .get("families", {}),
        "counts": {name: len(rows) for name, rows in split_map.items()},
    }
    write_json(root / "split-manifest.json", payload)
    return split_map
