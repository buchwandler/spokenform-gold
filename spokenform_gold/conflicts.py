from __future__ import annotations

from collections import defaultdict


def find_conflicts(records, mode="unit"):
    groups = defaultdict(list)

    if mode == "record":
        for record in records:
            key = (record.get("locale"), record.get("input"))
            groups[key].append(
                {
                    "record_id": record.get("id"),
                    "source": record.get("source", {}).get("benchmark"),
                    "value": record.get("expected_output"),
                    "status": record.get("status"),
                }
            )
    elif mode == "unit":
        for record in records:
            for unit in record.get("units", []):
                key = (record.get("locale"), unit.get("category"), unit.get("surface"))
                groups[key].append(
                    {
                        "record_id": record.get("id"),
                        "source": record.get("source", {}).get("benchmark"),
                        "value": unit.get("canonical"),
                        "accepted": unit.get("accepted", []),
                        "input": record.get("input"),
                        "status": record.get("status"),
                    }
                )
    else:
        raise ValueError("mode must be record or unit")

    output = []
    for key, items in sorted(groups.items()):
        if len(items) < 2:
            continue
        values = {
            str(item.get("value")).strip().casefold()
            for item in items
            if item.get("value") is not None
        }
        if len(values) > 1:
            output.append(
                {
                    "key": list(key),
                    "variants": sorted(values),
                    "items": items,
                    "action": "needs_adjudication",
                }
            )
    return output
