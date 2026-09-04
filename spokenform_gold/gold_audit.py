from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable

from .corpus import sentence_key
from .oracle import normalize_text, oracle_hash
from .validation import REVIEWED_STATUSES, validate_records


def _review_complete(record: dict) -> bool:
    review = record.get("review")
    if not isinstance(review, dict):
        return False
    reviewers = review.get("reviewers")
    return (
        isinstance(reviewers, list)
        and len({item for item in reviewers if isinstance(item, str)}) >= 2
        and isinstance(review.get("adjudicator"), str)
        and bool(review.get("adjudicator"))
        and review.get("status") in {"adjudicated", "release_ready"}
        and isinstance(review.get("protocol_version"), str)
        and bool(review.get("protocol_version"))
    )


def find_reviewed_oracle_conflicts(records: Iterable[dict]) -> list[dict]:
    groups: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for record in records:
        if record.get("status") not in REVIEWED_STATUSES:
            continue
        groups[
            sentence_key(
                record.get("language", ""),
                record.get("locale", ""),
                record.get("input", ""),
            )
            + (record.get("policy_version", ""),)
        ].append(record)
    conflicts = []
    for key, items in sorted(groups.items()):
        canonical = {
            normalize_text((item.get("oracle") or {}).get("canonical_output"))
            for item in items
        }
        if len(canonical) > 1:
            conflicts.append(
                {
                    "key": list(key),
                    "record_ids": sorted(item.get("id") for item in items),
                    "canonical_outputs": sorted(canonical),
                    "action": "needs_adjudication",
                }
            )
        accepted_by_record = {
            item.get("id"): {
                _norm
                for _norm in [
                    normalize_text(v)
                    for v in (item.get("oracle") or {}).get("accepted_outputs", [])
                ]
            }
            for item in items
        }
        rejected_by_record = {
            item.get("id"): {
                normalize_text(v.get("output"))
                for v in (item.get("oracle") or {}).get("rejected_outputs", [])
                if isinstance(v, dict)
            }
            for item in items
        }
        ids = sorted(accepted_by_record)
        for index, left_id in enumerate(ids):
            for right_id in ids[index + 1 :]:
                contradiction = (
                    accepted_by_record[left_id] & rejected_by_record[right_id]
                ) | (accepted_by_record[right_id] & rejected_by_record[left_id])
                if contradiction:
                    conflicts.append(
                        {
                            "key": list(key),
                            "record_ids": [left_id, right_id],
                            "contradictory_outputs": sorted(contradiction),
                            "action": "needs_adjudication",
                        }
                    )
    return conflicts


def audit_records(records: Iterable[dict], *, strict: bool = False) -> dict:
    record_list = list(records)
    errors = list(validate_records(record_list))
    legacy_ids = []
    missing_hash_ids = []
    review_gap_ids = []
    quarantine_ids = []
    for record in record_list:
        status = record.get("status")
        oracle = record.get("oracle")
        if status in REVIEWED_STATUSES | {"no_change", "ambiguous"} and not isinstance(
            oracle, dict
        ):
            errors.append(f"{record.get('id')}: missing sentence oracle")
        if status in REVIEWED_STATUSES | {"no_change", "ambiguous"} and isinstance(
            oracle, dict
        ):
            if oracle.get("variant_mode") != "explicit":
                legacy_ids.append(record.get("id"))
            if record.get("oracle_hash") != oracle_hash(record):
                missing_hash_ids.append(record.get("id"))
        if status == "quarantine":
            quarantine_ids.append(record.get("id"))
        if (
            strict
            and status in REVIEWED_STATUSES | {"no_change"}
            and not _review_complete(record)
        ):
            review_gap_ids.append(record.get("id"))
    conflicts = find_reviewed_oracle_conflicts(record_list)
    errors.extend(f"oracle conflict: {item}" for item in conflicts)
    if strict:
        errors.extend(
            f"{record_id}: incomplete review evidence" for record_id in review_gap_ids
        )
        errors.extend(
            f"{record_id}: legacy or non-explicit oracle" for record_id in legacy_ids
        )
        errors.extend(
            f"{record_id}: missing or invalid oracle_hash"
            for record_id in missing_hash_ids
        )
        errors.extend(
            f"{record_id}: quarantine record is not release eligible"
            for record_id in quarantine_ids
        )
    status_counts = Counter(record.get("status") for record in record_list)
    report = {
        "strict": strict,
        "records": len(record_list),
        "oracle_complete": not errors,
        "legacy_oracle_records": sorted(legacy_ids),
        "missing_oracle_hash_records": sorted(missing_hash_ids),
        "review_gap_records": sorted(review_gap_ids),
        "quarantine_records": sorted(quarantine_ids),
        "reviewed_oracle_conflicts": conflicts,
        "status_counts": dict(sorted(status_counts.items())),
        "review_complete_records": sum(
            _review_complete(record) for record in record_list
        ),
        "errors": sorted(errors),
    }
    return report
