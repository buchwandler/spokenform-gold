from __future__ import annotations

from collections.abc import Iterable
from copy import deepcopy
from pathlib import Path

from .corpus import (
    corpus_identity_map,
    read_corpus,
    sentence_key,
    stable_record_id,
    write_corpus_atomic,
    write_records_atomic,
)
from .io import read_json, read_jsonl, read_records, write_json, write_jsonl
from .rereview import (
    _event_from_decision,
    load_retry_pool,
    merge_retry_events,
    retry_context_fingerprint,
    write_retry_pool_atomic,
)
from .review import validate_v2_review_rows
from .validation import validate_records
from .work_layout import BatchLayout

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


def _batch_artifacts(
    batch_root: str | Path,
) -> tuple[BatchLayout, list[dict], list[dict], list[dict], list[dict], list[dict]]:
    root = Path(batch_root)
    layout = BatchLayout(root)
    cases_path = layout.cases if layout.cases.is_file() else root / "cases.jsonl"
    review_a_path = (
        layout.review_complete("A")
        if layout.review_complete("A").is_file()
        else root / "a.complete.jsonl"
    )
    review_b_path = (
        layout.review_complete("B")
        if layout.review_complete("B").is_file()
        else root / "b.complete.jsonl"
    )
    adjudicated_path = (
        layout.adjudication_decisions
        if layout.adjudication_decisions.is_file()
        else root / "adjudicated.jsonl"
    )
    cases = read_records([cases_path])
    review_a = read_records([review_a_path]) if review_a_path.exists() else []
    review_b = read_records([review_b_path]) if review_b_path.exists() else []
    adjudicated = read_records([adjudicated_path]) if adjudicated_path.exists() else []
    metadata = read_json(layout.metadata) if layout.metadata.is_file() else {}
    return layout, cases, review_a, review_b, adjudicated, metadata


def integrate_batch(
    batch_root: str | Path, corpus_path: str | Path, *, write: bool = False
) -> dict:
    """Integrate accepted decisions while preserving deferred case outcomes."""
    layout, cases, review_a, review_b, adjudicated, metadata = _batch_artifacts(
        batch_root
    )
    review_report = check_reviews(cases, review_a, review_b)
    if not review_report["ready"]:
        raise ValueError("review-check failed: " + "; ".join(review_report["issues"]))
    case_ids = {case.get("case_id") for case in cases}
    by_case = {row.get("case_id"): row for row in adjudicated}
    if len(by_case) != len(adjudicated) or set(by_case) != case_ids:
        missing = sorted(case_ids - set(by_case))
        extra = sorted(set(by_case) - case_ids)
        raise ValueError(
            f"adjudication case-ID set mismatch: missing={missing} extra={extra}"
        )
    require_blocker = metadata.get("batch_kind") == "rereview"
    for decision in adjudicated:
        disposition = decision.get("decision")
        if disposition == "unresolved":
            blocker = decision.get("blocker")
            if not isinstance(blocker, dict) or blocker.get("retryable") is not True:
                raise ValueError(
                    f"{decision.get('case_id')}: unresolved decision requires "
                    "retryable structured blocker"
                )
        elif disposition == "exclude" and require_blocker:
            if not isinstance(decision.get("blocker"), dict):
                raise ValueError(
                    f"{decision.get('case_id')}: exclude decision requires structured blocker"
                )
    corpus_target = Path(corpus_path)
    existing = (
        read_corpus(corpus_target)
        if corpus_target.is_dir()
        else read_records([corpus_target])
        if corpus_target.exists()
        else []
    )
    existing_map = corpus_identity_map(existing)
    final_records: list[dict] = []
    synthetic: list[dict] = []
    excluded: list[dict] = []
    retry: list[dict] = []
    for case in cases:
        decision = by_case[case["case_id"]]
        disposition = decision["decision"]
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
                    "blocker": decision.get("blocker"),
                }
            )
            continue
        if disposition == "unresolved":
            blocker = decision.get("blocker")
            if not isinstance(blocker, dict) or blocker.get("retryable") is not True:
                raise ValueError(
                    f"{case['case_id']}: unresolved decision requires retryable structured blocker"
                )
            retry.append(
                {
                    "case_id": case["case_id"],
                    "reason": decision.get(
                        "rationale", blocker.get("reason", "deferred")
                    ),
                    "blocker": blocker,
                    "decision": decision,
                }
            )
            continue
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
        if corpus_target.suffix == ".jsonl":
            write_records_atomic(corpus_target, combined.values())
        else:
            write_corpus_atomic(corpus_target, combined.values())
        write_jsonl(layout.integration_dir / "synthetic-candidates.jsonl", synthetic)
        write_jsonl(layout.integration_dir / "exclusions.jsonl", excluded)
        write_jsonl(layout.integration_dir / "retry.jsonl", retry)
        write_json(
            layout.integration_summary,
            {
                "state": "integrated",
                "records_added": len(final_records),
                "synthetic_candidates": len(synthetic),
                "excluded": len(excluded),
                "terminal_excluded": len(excluded),
                "retry_deferred": len(retry),
            },
        )
    return {
        "ready": True,
        "records": len(final_records),
        "synthetic_candidates": synthetic,
        "excluded": excluded,
        "retry": retry,
        "review": review_report,
    }


def finalize_batch(
    batch_root: str | Path,
    corpus_path: str | Path,
    retry_pool_path: str | Path | None = None,
    *,
    write: bool = False,
) -> dict:
    """Finalize a batch and update the durable retry index when writing."""
    result = integrate_batch(batch_root, corpus_path, write=write)
    layout, cases, _review_a, _review_b, adjudicated, metadata = _batch_artifacts(
        batch_root
    )
    batch_id = str(metadata.get("batch_id", layout.root.name))
    context_rows = read_jsonl(layout.context) if layout.context.is_file() else []
    context_map = {row.get("case_id"): row for row in context_rows}
    events = []
    for case in cases:
        decision = next(
            row for row in adjudicated if row.get("case_id") == case.get("case_id")
        )
        event = _event_from_decision(
            case,
            decision,
            batch_id,
            layout.root,
            str(metadata.get("batch_kind", "new_data")),
        )
        if event is None:
            continue
        rereview = (context_map.get(case.get("case_id")) or {}).get("rereview") or {}
        resolution = rereview.get("resolution") if isinstance(rereview, dict) else None
        if isinstance(resolution, dict):
            event["retry_context_hash"] = retry_context_fingerprint(resolution)
        event["case"] = {
            key: value for key, value in case.items() if not key.startswith("_")
        }
        if decision.get("decision") == "accept":
            event["record_id"] = (decision.get("final_record") or {}).get("id")
        events.append(event)
    pool_path = (
        Path(retry_pool_path)
        if retry_pool_path
        else layout.root.parent.parent / "state" / "review-exclusions.jsonl"
    )
    existing_pool = load_retry_pool(pool_path)
    existing_ids = {row.get("case_id") for row in existing_pool}
    pool_events = [
        event
        for event in events
        if event.get("decision") != "accept" or event.get("case_id") in existing_ids
    ]
    pool = merge_retry_events(existing_pool, pool_events)
    counts = {
        "accepted": result["records"],
        "terminal_excluded": len(result["excluded"]),
        "retry_deferred": len(result["retry"]),
        "records_added": result["records"],
    }
    if write:
        write_retry_pool_atomic(pool_path, pool)
        metadata = dict(metadata)
        metadata["state"] = "finalized"
        metadata["finalization"] = counts
        write_json(layout.metadata, metadata)
        write_json(
            layout.integration_summary,
            {
                "state": "finalized",
                **counts,
                "synthetic_candidates": len(result["synthetic_candidates"]),
            },
        )
    return {
        **result,
        **counts,
        "pool": str(pool_path),
        "state": "finalized" if write else "ready_to_finalize",
    }
