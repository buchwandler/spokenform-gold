from collections import defaultdict

def find_conflicts(records, mode="unit"):
    groups = defaultdict(list)

    if mode == "record":
        for r in records:
            key = (r.get("locale"), r.get("input"))
            groups[key].append({
                "record_id": r.get("id"),
                "source": r.get("source", {}).get("benchmark"),
                "value": r.get("expected_output"),
                "status": r.get("status")
            })
    elif mode == "unit":
        for r in records:
            for u in r.get("units", []):
                key = (r.get("locale"), u.get("category"), u.get("surface"))
                groups[key].append({
                    "record_id": r.get("id"),
                    "source": r.get("source", {}).get("benchmark"),
                    "value": u.get("canonical"),
                    "accepted": u.get("accepted", []),
                    "input": r.get("input"),
                    "status": r.get("status")
                })
    else:
        raise ValueError("mode must be record or unit")

    out = []
    for key, items in groups.items():
        if len(items) < 2:
            continue
        values = {str(x.get("value")).strip().casefold()
                  for x in items if x.get("value") is not None}
        if len(values) > 1:
            out.append({
                "key": key,
                "variants": sorted(values),
                "items": items,
                "action": "needs_adjudication"
            })
    return out
