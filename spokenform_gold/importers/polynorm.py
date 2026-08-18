from __future__ import annotations

from pathlib import Path

from ..io import expand_jsonl_paths, read_jsonl
from ..taxonomy import load_mapping, source_manifest_map


def import_polynorm(path: str | Path) -> list[dict]:
    manifest = source_manifest_map()["polynorm"]
    mapping = load_mapping("polynorm").get("mappings", {})
    records: list[dict] = []

    for file_index, source_path in enumerate(expand_jsonl_paths([path]), 1):
        rows = read_jsonl(source_path)
        for row_index, row in enumerate(rows, 1):
            category = row.get("category")
            rule = mapping.get(category)
            if rule is None:
                raise ValueError(
                    f"{source_path}:{row_index}: unsupported PolyNorm category {category!r}"
                )
            locale = row.get("locale", "en-US")
            language = row.get("language", locale.split("-", 1)[0].lower())
            source_id = str(row.get("source_id", f"{file_index}:{row_index}"))
            surface = row["surface"]
            start = row["start"]
            end = row["end"]
            records.append(
                {
                    "id": f"polynorm-{locale.lower()}-{file_index:02d}-{row_index:04d}",
                    "schema_version": "1.0.0",
                    "taxonomy_version": "1.0.0",
                    "policy_version": "1.0.0",
                    "language": language,
                    "locale": locale,
                    "split": "candidate",
                    "family_id": f"polynorm-{source_id}",
                    "status": "quarantine",
                    "input": row["input"],
                    "expected_output": None,
                    "source": {
                        "benchmark": "polynorm",
                        "source_id": source_id,
                        "source_version": manifest["revision"],
                        "source_url": manifest["source_url"],
                        "license": manifest["license"],
                        "upstream_expected": row["expected"],
                        "source_category": category,
                        "importer_version": "1.0.0",
                        "source_file": str(Path(source_path).name),
                    },
                    "units": [
                        {
                            "surface": surface,
                            "start": start,
                            "end": end,
                            "category": rule["category"],
                            "source_category": category,
                            "mapping_status": rule["status"],
                            "semantic": {},
                            "policy": "unadjudicated-upstream",
                            "canonical": None,
                            "accepted": [],
                            "rejected": [],
                            "features": {
                                "surface_pattern": rule.get(
                                    "surface_pattern", "imported"
                                ),
                                "locale_mapping": row.get("locale_mapping", locale),
                            },
                        }
                    ],
                    "negative_for": [],
                    "notes": row.get(
                        "note", "Imported from PolyNorm; adjudicate before promotion."
                    ),
                }
            )
    return records
