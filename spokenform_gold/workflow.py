from __future__ import annotations

from collections.abc import Iterable
from copy import deepcopy
from pathlib import Path

from .corpus import (
    corpus_identity_map,
    sentence_key,
    stable_record_id,
    write_records_atomic,
)
from .io import read_records, write_json, write_jsonl
from .review import validate_v2_review_rows
from .validation import validate_records

FINAL_DECISIONS = {"accept", "exclude", "unresolved"}


def _reviewer_id(row: dict) -> str | None:
    value = row.get("reviewer_id")
    if isinstance(value, str) and value.strip():
        return value
    review = row.get("review") or {}
    value = review.get("reviewer_id") if isinstance(review, dict) else None
    return value if isinstance(value, str) and value.strip() else None


def check_reviews(
    cases: Iterable[dict], review_a: Iterable[dict], review_b: Iterable[dict]
) -> dict:
    """Validate both completed sentence-centric v2 artifacts as one gate."""
    cases_list = list(cases)
    case_map = {
        case.get("case_id"): case
        for case in cases_list
        if isinstance(case, dict) and isinstance(case.get("case_id"), str)
    }
    issues: list[str] = []
    reports: list[dict] = []
    for slot, raw_rows in (("A", list(review_a)), ("B", list(review_b))):
        validation = validate_v2_review_rows(raw_rows, slot=slot)
        issues.extend(
            f"review {slot}: {issue['message']}" for issue in validation["issues"]
        )
        indexed = validation.get("_indexed", {})
        for case_id, row in indexed.items():
            case = case_map.get(case_id)
            if case is None:
                issues.append(f"review {slot}: unknown or missing case_id {case_id!r}")
                continue
            fields = ["language", "locale", "input"]
            if "family_id" in case:
                fields.append("family_id")
            for field in fields:
                if row.get(field) != case.get(field):
                    issues.append(
                        f"review {slot}: context mismatch for {case_id} in {field}"
                    )
        review_case_ids = set(indexed)
        expected_case_ids = set(case_map)
        for case_id in sorted(expected_case_ids - review_case_ids):
            issues.append(f"review {slot}: missing case_id {case_id}")
        reports.append(
            {
                "slot": slot,
                "rows": len(raw_rows),
                "case_ids": sorted(review_case_ids),
                "reviewer_id": validation["reviewer_id"],
                "completed": validation["completed"],
                "unreviewed": validation["unreviewed"],
                "validation": {
                    key: value for key, value in validation.items() if key != "_indexed"
                },
            }
        )
    a_ids, b_ids = set(reports[0]["case_ids"]), set(reports[1]["case_ids"])
    if a_ids != b_ids:
        issues.append(
            f"review case sets differ: only_a={sorted(a_ids - b_ids)} only_b={sorted(b_ids - a_ids)}"
        )
    expected_case_ids = set(case_map)
    if a_ids != expected_case_ids or b_ids != expected_case_ids:
        issues.append("review artifacts do not cover exactly the batch cases")
    reviewer_a = reports[0]["reviewer_id"]
    reviewer_b = reports[1]["reviewer_id"]
    if reviewer_a and reviewer_a == reviewer_b:
        issues.append("reviewer A and reviewer B must have distinct identities")
    return {
        "ready": not issues,
        "issues": sorted(set(issues)),
        "review_a": reports[0],
        "review_b": reports[1],
        "cases": len(case_map),
    }


def _source_case_map(cases: Iterable[dict]) -> dict[str, dict]:
    return {case.get("case_id"): case for case in cases}


def _canonical_record(case: dict, final: dict, existing: dict | None = None) -> dict:
    record = deepcopy(final)
    record.pop("case_id", None)
    record.pop("decision", None)
    record.pop("rationale", None)
    record.pop("synthetic_requests", None)
    record.pop("expected_output", None)
    record["schema_version"] = "2.0.0"
    record["id"] = (
        existing.get("id") if existing else record.get("id", stable_record_id(case))
    )
    record["language"] = case["language"]
    record["locale"] = case["locale"]
    record["input"] = case["input"]
    record["family_id"] = (
        existing.get("family_id") if existing else record.get("family_id")
    )
    if not record.get("family_id"):
        raise ValueError(f"{case.get('case_id')}: final record requires family_id")
    observations = deepcopy(case.get("source_observations", []))
    if existing:
        known = {
            (item.get("benchmark"), item.get("source_version"), item.get("source_id"))
            for item in existing.get("source_observations", [])
            if isinstance(item, dict)
        }
        observations = deepcopy(existing.get("source_observations", [])) + [
            item
            for item in observations
            if (
                item.get("benchmark"),
                item.get("source_version"),
                item.get("source_id"),
            )
            not in known
        ]
    record["source_observations"] = observations
    record["oracle_hash"] = __import__(
        "spokenform_gold.oracle", fromlist=["oracle_hash"]
    ).oracle_hash(record)
    return record


def integrate_batch(
    batch_root: str | Path, corpus_path: str | Path, *, write: bool = False
) -> dict:
    root = Path(batch_root)
    cases = read_records([root / "cases.jsonl"])
    review_a = (
        read_records([root / "a.complete.jsonl"])
        if (root / "a.complete.jsonl").exists()
        else []
    )
    review_b = (
        read_records([root / "b.complete.jsonl"])
        if (root / "b.complete.jsonl").exists()
        else []
    )
    adjudicated = (
        read_records([root / "adjudicated.jsonl"])
        if (root / "adjudicated.jsonl").exists()
        else []
    )
    review_report = check_reviews(cases, review_a, review_b)
    if not review_report["ready"]:
        raise ValueError("review-check failed: " + "; ".join(review_report["issues"]))
    by_case = {row.get("case_id"): row for row in adjudicated}
    if len(by_case) != len(adjudicated):
        raise ValueError("duplicate adjudication case_id")
    missing = sorted({case.get("case_id") for case in cases} - set(by_case))
    if missing:
        raise ValueError(f"missing adjudication for {missing}")
    existing = read_records([corpus_path]) if Path(corpus_path).exists() else []
    existing_map = corpus_identity_map(existing)
    final_records: list[dict] = []
    synthetic: list[dict] = []
    excluded: list[dict] = []
    for case in cases:
        decision = by_case[case["case_id"]]
        disposition = decision.get("decision")
        if disposition not in FINAL_DECISIONS:
            raise ValueError(
                f"{case['case_id']}: invalid adjudication decision {disposition!r}"
            )
        if decision.get("synthetic_requests"):
            synthetic.extend(
                decision["synthetic_requests"]
                if isinstance(decision["synthetic_requests"], list)
                else [decision["synthetic_requests"]]
            )
        if disposition == "exclude":
            excluded.append(
                {
                    "case_id": case["case_id"],
                    "reason": decision.get("rationale", "excluded"),
                }
            )
            continue
        if disposition == "unresolved":
            raise ValueError(
                f"{case['case_id']}: unresolved adjudication cannot enter Gold"
            )
        final = decision.get("final_record")
        if not isinstance(final, dict):
            raise TypeError(f"{case['case_id']}: accept decision requires final_record")
        identity = sentence_key(case["language"], case["locale"], case["input"])
        record = _canonical_record(case, final, existing_map.get(identity))
        record["review"] = {
            "protocol_version": "2.0.0",
            "status": "adjudicated",
            "reviewers": [
                review_report["review_a"]["reviewer_id"],
                review_report["review_b"]["reviewer_id"],
            ],
            "adjudicator": decision.get("adjudicator_id"),
            "decision": decision.get("rationale", "accepted"),
        }
        final_records.append(record)
    combined = {record.get("id"): record for record in existing}
    for record in final_records:
        if record["id"] in combined and combined[record["id"]].get(
            "input"
        ) != record.get("input"):
            raise ValueError(f"record.id collision for {record['id']}")
        combined[record["id"]] = record
    errors = validate_records(list(combined.values()))
    if errors:
        raise ValueError("integrated corpus is invalid: " + "; ".join(errors))
    if write:
        write_records_atomic(corpus_path, combined.values())
        write_jsonl(root / "synthetic-candidates.jsonl", synthetic)
        write_jsonl(root / "exclusions.jsonl", excluded)
        metadata = {
            "state": "integrated",
            "records_added": len(final_records),
            "synthetic_candidates": len(synthetic),
            "excluded": len(excluded),
        }
        write_json(root / "integration.json", metadata)
    return {
        "ready": True,
        "records": len(final_records),
        "synthetic_candidates": synthetic,
        "excluded": excluded,
        "review": review_report,
    }
