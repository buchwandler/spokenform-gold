from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Iterable

from .oracle import normalize_text


def _source_observations(record: dict) -> list[dict]:
    observations = record.get("source_observations")
    if not isinstance(observations, list) or not observations:
        observations = [record.get("source", {})]
    return [item for item in observations if isinstance(item, dict)]


def _provenance(record: dict) -> list[dict]:
    return [
        {
            "record_id": record.get("id"),
            "benchmark": source.get("benchmark"),
            "source_version": source.get("source_version"),
            "source_id": source.get("source_id"),
        }
        for source in _source_observations(record)
    ]


def _conflict_payload(conflict: dict) -> dict:
    key = conflict.get("key", [])
    return {
        "locale": key[0] if len(key) > 0 else "",
        "category": key[1] if len(key) > 1 else "",
        "surface": key[2] if len(key) > 2 else "",
        "variants": sorted(
            {
                normalize_text(value)
                for value in conflict.get("variants", [])
                if value is not None
            }
        ),
        "record_ids": sorted(
            item.get("record_id")
            for item in conflict.get("items", [])
            if item.get("record_id")
        ),
    }


def conflict_fingerprint(conflict: dict) -> str:
    """Return the stable fingerprint of the exact conflict being adjudicated."""
    encoded = json.dumps(
        _conflict_payload(conflict),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _member(record: dict, *, value: str | None = None, accepted=None) -> dict:
    provenance = _provenance(record)
    first = provenance[0] if provenance else {}
    return {
        "record_id": record.get("id"),
        "source": first.get("benchmark"),
        "benchmark": first.get("benchmark"),
        "source_version": first.get("source_version"),
        "source_id": first.get("source_id"),
        "source_observations": provenance,
        "value": value,
        "accepted": accepted if accepted is not None else [],
        "input": record.get("input"),
        "status": record.get("status"),
    }


def find_conflicts(records, mode="unit"):
    groups = defaultdict(list)

    if mode == "record":
        for record in records:
            key = (record.get("locale"), record.get("input"))
            groups[key].append(_member(record, value=record.get("expected_output")))
    elif mode == "unit":
        for record in records:
            for unit in record.get("units", []):
                key = (
                    record.get("locale"),
                    unit.get("category"),
                    unit.get("surface"),
                )
                groups[key].append(
                    _member(
                        record,
                        value=unit.get("canonical"),
                        accepted=unit.get("accepted", []),
                    )
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
            conflict = {
                "key": list(key),
                "variants": sorted(values),
                "items": items,
                "action": "needs_adjudication",
            }
            conflict["fingerprint"] = conflict_fingerprint(conflict)
            output.append(conflict)
    return output


def unresolved_adjudicated_conflicts(
    conflicts: Iterable[dict], adjudication: dict | None
) -> list[dict]:
    """Return conflicts without a current, fingerprint-matching waiver.

    Contextual variants may remain in the raw conflict report. A policy correction
    only resolves a release conflict once the canonical records no longer produce
    that raw group. Missing, stale, or unknown dispositions fail closed.
    """
    groups = {}
    if isinstance(adjudication, dict):
        for group in adjudication.get("groups", []):
            if isinstance(group, dict) and isinstance(group.get("key"), list):
                groups[tuple(group["key"])] = group

    unresolved = []
    for conflict in conflicts:
        key = tuple(conflict.get("key", []))
        group = groups.get(key)
        disposition = group.get("disposition") if group else None
        current_fingerprint = conflict.get("fingerprint") or conflict_fingerprint(
            conflict
        )
        item = dict(conflict)
        if group is None:
            item["action"] = "missing_or_unresolved_adjudication"
        elif group.get("fingerprint") != current_fingerprint:
            item["action"] = "stale_adjudication"
        elif disposition == "contextual_valid":
            continue
        elif disposition == "corrected_policy_inconsistency":
            item["action"] = "correction_not_applied"
        else:
            item["action"] = "missing_or_unresolved_adjudication"
        unresolved.append(item)
    return unresolved
