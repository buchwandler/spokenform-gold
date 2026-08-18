from __future__ import annotations
from collections import Counter, defaultdict
import json
from pathlib import Path

def load_targets(path):
    if not path:
        return {}
    return json.loads(Path(path).read_text(encoding="utf-8"))

def build_coverage(records, targets=None):
    targets = targets or {}
    cat_units = Counter()
    cat_records = Counter()
    cat_languages = defaultdict(set)
    cat_status = defaultdict(Counter)
    cat_patterns = defaultdict(Counter)
    negative = Counter()

    for r in records:
        for cat in r.get("negative_for", []):
            negative[cat] += 1
        seen = set()
        for u in r.get("units", []):
            cat = u.get("category")
            if not cat:
                continue
            cat_units[cat] += 1
            cat_languages[cat].add(r.get("language"))
            cat_status[cat][r.get("status")] += 1
            pattern = u.get("features", {}).get("surface_pattern")
            if pattern:
                cat_patterns[cat][pattern] += 1
            seen.add(cat)
        for cat in seen:
            cat_records[cat] += 1

    configured = set(targets.get("categories", {}))
    categories = sorted(set(cat_units) | configured)
    defaults = targets.get("default", {})
    target_languages = set(targets.get("languages", []))
    req_patterns = targets.get("required_patterns", {})

    rows, gaps = [], []
    for cat in categories:
        override = targets.get("categories", {}).get(cat, {})
        min_units = override.get("min_units", defaults.get("min_units", 0))
        min_amb = override.get("min_ambiguous", defaults.get("min_ambiguous", 0))
        min_neg = override.get("min_negative_controls", defaults.get("min_negative_controls", 0))
        missing_langs = sorted(target_languages - cat_languages[cat])
        missing_patterns = sorted(set(req_patterns.get(cat, [])) - set(cat_patterns[cat]))

        rows.append({
            "category": cat,
            "records": cat_records[cat],
            "units": cat_units[cat],
            "languages": sorted(x for x in cat_languages[cat] if x),
            "statuses": dict(cat_status[cat]),
            "negative_controls": negative[cat],
            "patterns": dict(cat_patterns[cat]),
            "missing_languages": missing_langs,
            "missing_patterns": missing_patterns
        })

        if cat_units[cat] < min_units:
            gaps.append({"category":cat,"kind":"low_volume","have":cat_units[cat],"need":min_units})
        if cat_status[cat].get("ambiguous", 0) < min_amb:
            gaps.append({"category":cat,"kind":"ambiguous","have":cat_status[cat].get("ambiguous",0),"need":min_amb})
        if negative[cat] < min_neg:
            gaps.append({"category":cat,"kind":"negative_controls","have":negative[cat],"need":min_neg})
        for lang in missing_langs:
            gaps.append({"category":cat,"kind":"language","missing":lang})
        for pattern in missing_patterns:
            gaps.append({"category":cat,"kind":"surface_pattern","missing":pattern})

    return {
        "records": len(records),
        "categories_observed": len(cat_units),
        "categories_targeted": len(configured),
        "coverage": rows,
        "gaps": gaps
    }
