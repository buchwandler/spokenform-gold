from __future__ import annotations
from collections import Counter, defaultdict
from pathlib import Path
import json

STATUSES = {"gold","multi_valid","policy_choice","ambiguous","quarantine","no_change"}
SPLITS = {"train","dev","test","challenge","judge_gold","candidate"}

def _norm_text(value: str) -> str:
    return " ".join(value.split()).casefold()

def load_categories(path=None) -> set[str]:
    if path is None:
        path = Path(__file__).resolve().parents[2] / "taxonomy" / "categories.json"
    p = Path(path)
    if not p.exists():
        return set()
    return set(json.loads(p.read_text(encoding="utf-8"))["categories"])

def validate_records(records, *, judge=False, categories=None):
    errors = []
    ids = Counter(r.get("id") for r in records)
    for rid, count in ids.items():
        if rid and count > 1:
            errors.append(f"duplicate id: {rid} ({count} records)")

    if judge:
        for r in records:
            line = r.get("_source_line", "?")
            for key in ("id","input","candidate","human_label","reason","category","language"):
                if key not in r:
                    errors.append(f"line {line}: missing judge field {key}")
            if r.get("human_label") not in {"accept","reject"}:
                errors.append(f"line {line}: human_label must be accept/reject")
        return errors

    categories = categories if categories is not None else load_categories()

    for r in records:
        line = r.get("_source_line", "?")
        prefix = f"line {line} ({r.get('id','?')})"
        required = ("id","language","locale","split","family_id","status","input",
                    "expected_output","source","units","negative_for")
        for key in required:
            if key not in r:
                errors.append(f"{prefix}: missing field {key}")
        if r.get("status") not in STATUSES:
            errors.append(f"{prefix}: invalid status {r.get('status')!r}")
        if r.get("split") not in SPLITS:
            errors.append(f"{prefix}: invalid split {r.get('split')!r}")
        if not isinstance(r.get("source"), dict) or not r.get("source", {}).get("benchmark"):
            errors.append(f"{prefix}: source.benchmark is required")
        if not isinstance(r.get("units"), list):
            errors.append(f"{prefix}: units must be a list")
            continue
        if not isinstance(r.get("negative_for"), list):
            errors.append(f"{prefix}: negative_for must be a list")

        if r.get("status") == "no_change":
            if r.get("units"):
                errors.append(f"{prefix}: no_change records must not contain units")
            if r.get("expected_output") != r.get("input"):
                errors.append(f"{prefix}: no_change expected_output must equal input")
            if not r.get("negative_for"):
                errors.append(f"{prefix}: no_change requires negative_for")
        elif r.get("status") in {"gold","multi_valid","policy_choice"}:
            if not isinstance(r.get("expected_output"), str):
                errors.append(f"{prefix}: reviewed records require expected_output")

        text = r.get("input", "")
        for i, u in enumerate(r.get("units", [])):
            up = f"{prefix}: unit[{i}]"
            for key in ("surface","category","canonical","accepted","rejected","features"):
                if key not in u:
                    errors.append(f"{up}: missing field {key}")

            cat = u.get("category")
            if categories and cat not in categories:
                errors.append(f"{up}: unknown category {cat!r}")

            surface = u.get("surface")
            if not isinstance(surface, str) or not surface:
                errors.append(f"{up}: surface must be non-empty string")
                continue

            starts = []
            pos = 0
            while True:
                found = text.find(surface, pos)
                if found < 0:
                    break
                starts.append(found)
                pos = found + 1

            if not starts:
                errors.append(f"{up}: surface {surface!r} not found in input")

            has_span = "start" in u or "end" in u
            if has_span:
                if not isinstance(u.get("start"), int) or not isinstance(u.get("end"), int):
                    errors.append(f"{up}: start/end must both be integers")
                elif text[u["start"]:u["end"]] != surface:
                    errors.append(f"{up}: start/end do not select surface")
            elif len(starts) > 1:
                errors.append(f"{up}: repeated surface requires explicit start/end")

            accepted = u.get("accepted", [])
            rejected = u.get("rejected", [])
            canonical = u.get("canonical")

            if not isinstance(accepted, list) or not all(isinstance(x, str) for x in accepted):
                errors.append(f"{up}: accepted must be list[str]")
                accepted = []
            if not isinstance(rejected, list) or not all(isinstance(x, str) for x in rejected):
                errors.append(f"{up}: rejected must be list[str]")
                rejected = []

            if r.get("status") in {"gold","multi_valid","policy_choice"}:
                if not isinstance(canonical, str) or not canonical.strip():
                    errors.append(f"{up}: canonical required for reviewed record")
                elif _norm_text(canonical) not in {_norm_text(x) for x in accepted}:
                    errors.append(f"{up}: canonical must appear in accepted")

            overlap = {_norm_text(x) for x in accepted} & {_norm_text(x) for x in rejected}
            if overlap:
                errors.append(f"{up}: accepted/rejected overlap: {sorted(overlap)}")

            if not isinstance(u.get("features"), dict):
                errors.append(f"{up}: features must be object")

    family_splits = defaultdict(set)
    for r in records:
        if r.get("family_id") and r.get("split") not in {"candidate","judge_gold"}:
            family_splits[r["family_id"]].add(r.get("split"))
    for family, splits in family_splits.items():
        if len(splits) > 1:
            errors.append(f"family leakage: {family} appears in splits {sorted(splits)}")
    return errors
