from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from .census import _ref_key, _source_ref
from .deduplication import normalize_for_fingerprint

REVIEW_STATES = {
    "unreviewed", "review_a_complete", "review_b_complete", "agreement",
    "disagreement", "adjudication_required", "adjudicated",
    "quality_audit_required", "release_ready", "superseded", "legacy_review",
}
SOURCE_ERROR_CODES = {
    "source_wrong_semantics", "source_wrong_realization", "source_missing_variant",
    "source_over_accepts_variant", "source_locale_mismatch", "source_policy_difference",
    "source_ambiguous_context", "source_span_error", "source_category_error",
    "source_language_error", "source_corrupt_row", "source_duplicate", "source_unsupported",
}


def _cluster_key(record: dict) -> tuple[str, str, str]:
    return (record.get("language", ""), record.get("locale", ""), normalize_for_fingerprint(record.get("input")))


def blind_review_batch(records: Iterable[dict], *, reviewer_slot: str) -> list[dict]:
    if reviewer_slot not in {"A", "B"}:
        raise ValueError("reviewer_slot must be A or B")
    groups: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for record in records:
        groups[_cluster_key(record)].append(record)
    output = []
    for key, members in sorted(groups.items()):
        first = sorted(members, key=lambda item: item.get("id", ""))[0]
        source_refs = sorted({_ref_key(_source_ref(member)): _source_ref(member) for member in members}.values(), key=lambda item: (item.get("benchmark") or "", item.get("source_id") or ""))
        output.append({
            "review_schema_version": "1.0.0",
            "sentence_oracle_id": "oracle-" + __import__("hashlib").sha256("|".join(key).encode()).hexdigest(),
            "reviewer_slot": reviewer_slot,
            "language": first.get("language"),
            "locale": first.get("locale"),
            "input": first.get("input"),
            "materialization": first.get("materialization", "embedded"),
            "source_refs": source_refs,
            "annotation": None,
            "review": {"status": "unreviewed", "protocol_version": "1.0.0"},
        })
    return output


def compare_review_annotations(review_a: dict, review_b: dict) -> dict:
    annotation_a = review_a.get("annotation") or {}
    annotation_b = review_b.get("annotation") or {}
    oracle_a = annotation_a.get("oracle") or {}
    oracle_b = annotation_b.get("oracle") or {}
    dimensions = {
        "span": annotation_a.get("units") != annotation_b.get("units"),
        "category": [unit.get("category") for unit in annotation_a.get("units", [])] != [unit.get("category") for unit in annotation_b.get("units", [])],
        "semantic": [unit.get("semantic") for unit in annotation_a.get("units", [])] != [unit.get("semantic") for unit in annotation_b.get("units", [])],
        "ambiguity": annotation_a.get("status") == "ambiguous" or annotation_b.get("status") == "ambiguous",
        "policy": [unit.get("policy") for unit in annotation_a.get("units", [])] != [unit.get("policy") for unit in annotation_b.get("units", [])],
        "unit_canonical": [unit.get("canonical") for unit in annotation_a.get("units", [])] != [unit.get("canonical") for unit in annotation_b.get("units", [])],
        "unit_accepted": [unit.get("accepted") for unit in annotation_a.get("units", [])] != [unit.get("accepted") for unit in annotation_b.get("units", [])],
        "sentence_canonical": oracle_a.get("canonical_output") != oracle_b.get("canonical_output"),
        "sentence_accepted": oracle_a.get("accepted_outputs") != oracle_b.get("accepted_outputs"),
        "rejected_variants": oracle_a.get("rejected_outputs") != oracle_b.get("rejected_outputs"),
    }
    return {"sentence_oracle_id": review_a.get("sentence_oracle_id"), "dimensions": dimensions, "disagreement": any(dimensions.values()), "state": "disagreement" if any(dimensions.values()) else "agreement"}
