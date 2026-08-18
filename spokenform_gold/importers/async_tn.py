from __future__ import annotations
import json
from pathlib import Path

def _unit(surface, category):
    return {
        "surface": surface,
        "category": category,
        "semantic": {},
        "policy": "unadjudicated-upstream",
        "canonical": None,
        "accepted": [],
        "rejected": [],
        "features": {"surface_pattern": "unclassified"}
    }

def import_async(path, language="en", locale="en-US"):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    records = []
    for idx, row in enumerate(data, 1):
        original = row.get("original_text")
        expected = row.get("normalized_text")
        if not isinstance(original, str):
            continue
        units = [
            _unit(u.get("text",""), u.get("norm_category","unknown"))
            for u in row.get("units", [])
            if u.get("text")
        ]
        records.append({
            "id": f"async-tn-{language}-{row.get('row_index', idx):06d}",
            "language": language,
            "locale": locale,
            "split": "candidate",
            "family_id": f"async-tn-row-{row.get('row_index', idx)}",
            "status": "quarantine",
            "input": original,
            "expected_output": None,
            "source": {
                "benchmark": "async_tn",
                "source_id": str(row.get("row_index", idx)),
                "upstream_expected": expected,
                "import_note": "Imported as candidate; adjudicate before gold promotion."
            },
            "units": units,
            "negative_for": [],
            "notes": ""
        })
    return records
