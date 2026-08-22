from __future__ import annotations

from .oracle import oracle_hash


def _assertion(record: dict) -> dict:
    return {
        "oracle_hash": record.get("oracle_hash") or oracle_hash(record),
        "status": record.get("status"),
        "oracle": record.get("oracle"),
        "units": record.get("units", []),
        "input": record.get("input"),
    }


def classify_change(old: dict, new: dict) -> str:
    old_oracle, new_oracle = old.get("oracle") or {}, new.get("oracle") or {}
    if old_oracle.get("canonical_output") != new_oracle.get("canonical_output"):
        return "canonical_change"
    if old_oracle.get("accepted_outputs") != new_oracle.get("accepted_outputs"):
        return "variant_addition" if len(new_oracle.get("accepted_outputs", [])) > len(old_oracle.get("accepted_outputs", [])) else "variant_removal"
    if old.get("units") != new.get("units"):
        return "semantic_change"
    if old.get("status") != new.get("status"):
        return "policy_change"
    return "metadata_only"


def diff_records(old_records: list[dict], new_records: list[dict]) -> dict:
    old_map = {record.get("id"): record for record in old_records}
    new_map = {record.get("id"): record for record in new_records}
    added = sorted(set(new_map) - set(old_map))
    removed = sorted(set(old_map) - set(new_map))
    changed = []
    for record_id in sorted(set(old_map) & set(new_map)):
        old_assertion, new_assertion = _assertion(old_map[record_id]), _assertion(new_map[record_id])
        if old_assertion != new_assertion:
            changed.append({
                "record_id": record_id,
                "old_oracle_hash": old_assertion["oracle_hash"],
                "new_oracle_hash": new_assertion["oracle_hash"],
                "classification": classify_change(old_map[record_id], new_map[record_id]),
                "old": old_assertion,
                "new": new_assertion,
            })
    return {"added": added, "removed": removed, "changed": changed, "counts": {"added": len(added), "removed": len(removed), "changed": len(changed)}}


def correction_record(old: dict, new: dict, *, reason: str, reviewed_by: list[str], adjudicator: str) -> dict:
    return {
        "record_id": new.get("id"),
        "old_oracle_hash": old.get("oracle_hash") or oracle_hash(old),
        "new_oracle_hash": new.get("oracle_hash") or oracle_hash(new),
        "reason": reason,
        "reviewed_by": sorted(reviewed_by),
        "adjudicator": adjudicator,
    }
