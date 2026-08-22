from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from pathlib import Path
from typing import Any
from collections.abc import Iterable

from .census import _ref_key, _source_ref
from .deduplication import normalize_for_fingerprint
from .io import write_json, write_jsonl
from .oracle import oracle_hash
from .validation import validate_records

REVIEW_PROTOCOL_VERSION = "1.0.0"
REVIEW_STATES = {
    "unreviewed",
    "review_a_complete",
    "review_b_complete",
    "agreement",
    "disagreement",
    "adjudication_required",
    "adjudicated",
    "quality_audit_required",
    "release_ready",
    "superseded",
    "legacy_review",
}
SOURCE_ERROR_CODES = {
    "source_wrong_semantics",
    "source_wrong_realization",
    "source_missing_variant",
    "source_over_accepts_variant",
    "source_locale_mismatch",
    "source_policy_difference",
    "source_ambiguous_context",
    "source_span_error",
    "source_category_error",
    "source_language_error",
    "source_corrupt_row",
    "source_duplicate",
    "source_unsupported",
}
_BLIND_FORBIDDEN_KEYS = {
    "upstream_expected",
    "upstream_output",
    "current_output",
    "spokenform_output",
}


def _cluster_key(record: dict) -> tuple[str, str, str]:
    return (
        record.get("language", ""),
        record.get("locale", ""),
        normalize_for_fingerprint(record.get("input")),
    )


def _sentence_oracle_id(record: dict) -> str:
    import hashlib

    return (
        "oracle-" + hashlib.sha256("|".join(_cluster_key(record)).encode()).hexdigest()
    )


def blind_review_batch(records: Iterable[dict], *, reviewer_slot: str) -> list[dict]:
    if reviewer_slot not in {"A", "B"}:
        raise ValueError("reviewer_slot must be A or B")
    groups: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for record in records:
        groups[_cluster_key(record)].append(record)
    output = []
    for key, members in sorted(groups.items()):
        first = sorted(members, key=lambda item: item.get("id", ""))[0]
        source_refs = sorted(
            {
                _ref_key(_source_ref(member)): _source_ref(member) for member in members
            }.values(),
            key=lambda item: (item.get("benchmark") or "", item.get("source_id") or ""),
        )
        output.append(
            {
                "review_schema_version": REVIEW_PROTOCOL_VERSION,
                "sentence_oracle_id": _sentence_oracle_id(first),
                "reviewer_slot": reviewer_slot,
                "language": first.get("language"),
                "locale": first.get("locale"),
                "input": first.get("input"),
                "materialization": first.get("materialization", "embedded"),
                "source_refs": source_refs,
                "annotation": None,
                "review": {
                    "status": "unreviewed",
                    "protocol_version": REVIEW_PROTOCOL_VERSION,
                },
            }
        )
    return output


def compare_review_annotations(review_a: dict, review_b: dict) -> dict:
    annotation_a = review_a.get("annotation") or {}
    annotation_b = review_b.get("annotation") or {}
    oracle_a = annotation_a.get("oracle") or {}
    oracle_b = annotation_b.get("oracle") or {}
    dimensions = {
        "span": annotation_a.get("units") != annotation_b.get("units"),
        "category": [unit.get("category") for unit in annotation_a.get("units", [])]
        != [unit.get("category") for unit in annotation_b.get("units", [])],
        "semantic": [unit.get("semantic") for unit in annotation_a.get("units", [])]
        != [unit.get("semantic") for unit in annotation_b.get("units", [])],
        "ambiguity": annotation_a.get("status") == "ambiguous"
        or annotation_b.get("status") == "ambiguous",
        "policy": [unit.get("policy") for unit in annotation_a.get("units", [])]
        != [unit.get("policy") for unit in annotation_b.get("units", [])],
        "unit_canonical": [
            unit.get("canonical") for unit in annotation_a.get("units", [])
        ]
        != [unit.get("canonical") for unit in annotation_b.get("units", [])],
        "unit_accepted": [
            unit.get("accepted") for unit in annotation_a.get("units", [])
        ]
        != [unit.get("accepted") for unit in annotation_b.get("units", [])],
        "sentence_canonical": oracle_a.get("canonical_output")
        != oracle_b.get("canonical_output"),
        "sentence_accepted": oracle_a.get("accepted_outputs")
        != oracle_b.get("accepted_outputs"),
        "rejected_variants": oracle_a.get("rejected_outputs")
        != oracle_b.get("rejected_outputs"),
    }
    return {
        "sentence_oracle_id": review_a.get("sentence_oracle_id"),
        "dimensions": dimensions,
        "disagreement": any(dimensions.values()),
        "state": "disagreement" if any(dimensions.values()) else "agreement",
    }


def _reviewer_id(review: dict) -> str | None:
    annotation = review.get("annotation") or {}
    lifecycle = review.get("review") or {}
    for container in (review, lifecycle, annotation):
        value = container.get("reviewer_id")
        if isinstance(value, str) and value.strip():
            return value
    return None


def _assert_blind_safe(value: Any, *, path: str = "review") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in _BLIND_FORBIDDEN_KEYS:
                raise ValueError(f"{path}: blind review contains forbidden field {key}")
            _assert_blind_safe(child, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _assert_blind_safe(child, path=f"{path}[{index}]")


def _index_completed_reviews(
    rows: Iterable[dict], *, slot: str
) -> tuple[dict[str, dict], str]:
    indexed: dict[str, dict] = {}
    reviewer_ids: set[str] = set()
    for row in rows:
        _assert_blind_safe(row)
        if row.get("reviewer_slot") != slot:
            raise ValueError(
                f"review row {row.get('sentence_oracle_id', '?')} is not reviewer slot {slot}"
            )
        oracle_id = row.get("sentence_oracle_id")
        if not isinstance(oracle_id, str) or not oracle_id:
            raise ValueError("review rows require sentence_oracle_id")
        if oracle_id in indexed:
            raise ValueError(f"duplicate review row {oracle_id} for reviewer {slot}")
        reviewer_id = _reviewer_id(row)
        if reviewer_id is None:
            raise ValueError(f"review row {oracle_id} is missing reviewer_id")
        annotation = row.get("annotation")
        if not isinstance(annotation, dict):
            raise ValueError(f"review row {oracle_id} is missing completed annotation")
        indexed[oracle_id] = row
        reviewer_ids.add(reviewer_id)
    if len(reviewer_ids) != 1:
        raise ValueError(f"reviewer {slot} file must contain one stable reviewer_id")
    return indexed, next(iter(reviewer_ids))


def compare_review_batches(
    review_a: Iterable[dict], review_b: Iterable[dict]
) -> list[dict]:
    indexed_a, reviewer_a = _index_completed_reviews(review_a, slot="A")
    indexed_b, reviewer_b = _index_completed_reviews(review_b, slot="B")
    if reviewer_a == reviewer_b:
        raise ValueError(
            "reviewer A and reviewer B must have distinct reviewer_id values"
        )
    if set(indexed_a) != set(indexed_b):
        missing_a = sorted(set(indexed_b) - set(indexed_a))
        missing_b = sorted(set(indexed_a) - set(indexed_b))
        raise ValueError(
            f"review sets do not match: missing_a={missing_a}, missing_b={missing_b}"
        )
    comparisons = []
    for oracle_id in sorted(indexed_a):
        left = indexed_a[oracle_id]
        right = indexed_b[oracle_id]
        for field in ("input", "language", "locale"):
            if left.get(field) != right.get(field):
                raise ValueError(f"{oracle_id}: reviewer inputs disagree for {field}")
        comparison = compare_review_annotations(left, right)
        comparison.update(
            {
                "reviewer_a": reviewer_a,
                "reviewer_b": reviewer_b,
                "input": left.get("input"),
                "language": left.get("language"),
                "locale": left.get("locale"),
            }
        )
        comparisons.append(comparison)
    return comparisons


def _assert_output_isolated(
    output_root: Path, input_paths: Iterable[str | Path]
) -> None:
    target = output_root.resolve()
    for raw in input_paths:
        source = Path(raw).resolve()
        source_root = source if source.is_dir() else source.parent
        if (
            target == source_root
            or target in source_root.parents
            or source_root in target.parents
        ):
            raise ValueError(f"output root {target} overlaps input path {source}")
    if target.exists() and any(target.iterdir()):
        raise ValueError(f"output root must be new or empty: {target}")


def apply_reviewed_oracles(
    records: Iterable[dict],
    review_a: Iterable[dict],
    review_b: Iterable[dict],
    decisions: Iterable[dict],
) -> tuple[list[dict], list[dict], dict]:
    records_list = list(records)
    comparisons = compare_review_batches(review_a, review_b)
    comparison_map = {item["sentence_oracle_id"]: item for item in comparisons}
    record_map = {_sentence_oracle_id(record): record for record in records_list}
    if len(record_map) != len(records_list):
        raise ValueError(
            "canonical records contain duplicate sentence oracle identities"
        )
    decision_map: dict[str, dict] = {}
    for decision in decisions:
        oracle_id = decision.get("sentence_oracle_id")
        if not isinstance(oracle_id, str) or not oracle_id:
            raise ValueError("review decisions require sentence_oracle_id")
        if oracle_id in decision_map:
            raise ValueError(f"duplicate adjudication decision {oracle_id}")
        if oracle_id not in record_map or oracle_id not in comparison_map:
            raise ValueError(f"decision references unknown review identity {oracle_id}")
        decision_map[oracle_id] = decision
    missing = sorted(set(record_map) - set(decision_map))
    if missing:
        raise ValueError(f"missing adjudication decisions for {missing}")

    updated: list[dict] = []
    for oracle_id in sorted(record_map):
        original = record_map[oracle_id]
        decision = decision_map[oracle_id]
        comparison = comparison_map[oracle_id]
        reviewers = decision.get("reviewers")
        if (
            not isinstance(reviewers, list)
            or len({item for item in reviewers if isinstance(item, str)}) < 2
        ):
            raise ValueError(
                f"{oracle_id}: adjudication requires two distinct reviewers"
            )
        if (
            comparison["reviewer_a"] not in reviewers
            or comparison["reviewer_b"] not in reviewers
        ):
            raise ValueError(
                f"{oracle_id}: adjudication reviewers do not match blind reviewers"
            )
        adjudicator = decision.get("adjudicator")
        if not isinstance(adjudicator, str) or not adjudicator.strip():
            raise ValueError(f"{oracle_id}: adjudication requires adjudicator")
        for field in ("input", "language", "locale"):
            if field in decision and decision[field] != original.get(field):
                raise ValueError(
                    f"{oracle_id}: adjudication disagrees with canonical {field}"
                )
        if "record_id" in decision and decision["record_id"] != original.get("id"):
            raise ValueError(f"{oracle_id}: record_id does not match canonical record")
        if "family_id" in decision and decision["family_id"] != original.get(
            "family_id"
        ):
            raise ValueError(
                f"{oracle_id}: family_id migration requires explicit adjudication outside this workflow"
            )
        for field in (
            "status",
            "expected_output",
            "units",
            "negative_for",
            "notes",
            "oracle",
        ):
            if field not in decision:
                raise ValueError(f"{oracle_id}: adjudication decision missing {field}")
        record = deepcopy(original)
        for field in (
            "status",
            "expected_output",
            "units",
            "negative_for",
            "notes",
            "oracle",
        ):
            record[field] = deepcopy(decision[field])
        record["oracle_hash"] = oracle_hash(record)
        record["review"] = {
            "protocol_version": decision.get(
                "review_protocol_version", REVIEW_PROTOCOL_VERSION
            ),
            "status": decision.get("review_status", "adjudicated"),
            "reviewers": sorted(set(reviewers)),
            "adjudicator": adjudicator,
            "decision": decision.get("decision", "adjudicated_oracle"),
            "disagreement": deepcopy(
                decision.get("disagreement", comparison["dimensions"])
            ),
            "source_error_codes": sorted(set(decision.get("source_error_codes", []))),
        }
        if record["review"]["status"] not in {"adjudicated", "release_ready"}:
            raise ValueError(
                f"{oracle_id}: final review status must be adjudicated or release_ready"
            )
        updated.append(record)
    errors = validate_records(updated)
    if errors:
        raise ValueError("reviewed output is invalid: " + "; ".join(errors))
    report = {
        "records": len(updated),
        "comparisons": len(comparisons),
        "agreement": sum(item["state"] == "agreement" for item in comparisons),
        "disagreement": sum(item["state"] == "disagreement" for item in comparisons),
        "record_ids": [record["id"] for record in updated],
        "reviewers": sorted(
            {item["reviewer_a"] for item in comparisons}
            | {item["reviewer_b"] for item in comparisons}
        ),
        "adjudicators": sorted({record["review"]["adjudicator"] for record in updated}),
    }
    return updated, comparisons, report


def write_review_application(
    out_root: str | Path,
    records: list[dict],
    comparisons: list[dict],
    report: dict,
    *,
    input_paths: Iterable[str | Path],
) -> None:
    target = Path(out_root)
    _assert_output_isolated(target, input_paths)
    target.mkdir(parents=True, exist_ok=True)
    write_jsonl(target / "records.jsonl", records)
    write_jsonl(target / "comparisons.jsonl", comparisons)
    write_json(target / "report.json", report)
