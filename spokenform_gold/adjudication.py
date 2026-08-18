from __future__ import annotations

import json
from pathlib import Path
from typing import Any


HIGH_RISK_CATEGORIES = {
    "date",
    "time",
    "decimal",
    "fraction",
    "currency",
    "ip_address",
    "version",
}


def _load_json(path: str | Path | None) -> Any:
    if not path:
        return None
    target = Path(path)
    if not target.exists():
        return None
    return json.loads(target.read_text(encoding="utf-8"))


def build_adjudication_queue(
    records: list[dict],
    *,
    conflicts: list[dict] | None = None,
    coverage: dict | None = None,
) -> list[dict]:
    conflict_keys = {
        tuple(item.get("key", ()))
        for item in (conflicts or [])
        if isinstance(item.get("key"), list | tuple)
    }
    coverage_gaps = {}
    for gap in (coverage or {}).get("gaps", []):
        category = gap.get("category")
        if isinstance(category, str):
            coverage_gaps.setdefault(category, []).append(gap)

    queue = []
    for record in records:
        priority = 0
        reasons: list[str] = []
        source_name = record.get("source", {}).get("benchmark")
        if source_name == "spokenform_regression":
            priority += 50
            reasons.append("production_regression")

        categories = sorted(
            {
                unit.get("category")
                for unit in record.get("units", [])
                if unit.get("category")
            }
        )
        for unit in record.get("units", []):
            key = (record.get("locale"), unit.get("category"), unit.get("surface"))
            if key in conflict_keys:
                priority += 40
                reasons.append("source_disagreement")
                break

        for category in categories:
            if category in coverage_gaps:
                priority += 15
                reasons.append(f"coverage_gap:{category}")
        if any(category in HIGH_RISK_CATEGORIES for category in categories):
            priority += 10
            reasons.append("semantic_risk")
        if record.get("status") == "quarantine":
            priority += 5
            reasons.append("quarantine_review")

        queue.append(
            {
                "id": record.get("id"),
                "priority": priority,
                "reasons": sorted(set(reasons)),
                "status": record.get("status"),
                "source": source_name,
                "language": record.get("language"),
                "locale": record.get("locale"),
                "categories": categories,
                "input": record.get("input"),
            }
        )

    queue.sort(key=lambda item: (-item["priority"], item["id"] or ""))
    return queue
