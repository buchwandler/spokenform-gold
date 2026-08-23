from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from copy import deepcopy
from pathlib import Path
from typing import Any

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


def sentence_oracle_id(record: dict) -> str:
    """Return the stable derived identity for a canonical sentence cluster.

    Canonical records intentionally do not persist this value.  Review artifacts
    use it as a join key derived from language, locale, and normalized input.
    """

    import hashlib

    return (
        "oracle-" + hashlib.sha256("|".join(_cluster_key(record)).encode()).hexdigest()
    )


def _sentence_oracle_id(record: dict) -> str:
    """Backward-compatible private alias for the public identity helper."""
    return sentence_oracle_id(record)



def blind_review_batch(records: Iterable[dict], *, reviewer_slot: str) -> list[dict]:
    if reviewer_slot not in {"A", "B"}:
        raise ValueError("reviewer_slot must be A or B")
    groups: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for record in records:
        groups[_cluster_key(record)].append(record)
    output = []
    for key, members in sorted(groups.items()):
        first = min(members, key=lambda item: item.get("id", ""))
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

_REVIEW_COMPLETE_STATUSES = {"A": "review_a_complete", "B": "review_b_complete"}
_ANNOTATION_STATUSES = {"gold", "multi_valid", "policy_choice", "ambiguous", "no_change"}


def _issue(scope: str, code: str, message: str, oracle_id: str | None = None) -> dict:
    result = {"scope": scope, "code": code, "message": message}
    if oracle_id is not None:
        result["sentence_oracle_id"] = oracle_id
    return result


def _collect_blind_issues(value: Any, *, path: str = "review") -> list[str]:
    issues: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key in _BLIND_FORBIDDEN_KEYS:
                issues.append(f"{path}.{key}")
            issues.extend(_collect_blind_issues(child, path=f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            issues.extend(_collect_blind_issues(child, path=f"{path}[{index}]"))
    return issues


def _rejected_output_strings(rejected: list) -> set[str]:
    """Collect comparable output strings from rejected entries.

    Oracle rejected entries are objects with an ``output`` field; unit-level
    rejected entries are plain strings.  Tolerate both so overlap checks do
    not attempt to hash dicts.
    """
    strings: set[str] = set()
    for item in rejected:
        if isinstance(item, str):
            strings.add(item)
        elif isinstance(item, dict) and isinstance(item.get("output"), str):
            strings.add(item["output"])
    return strings


def _annotation_issues(row: dict, *, oracle_id: str, scope: str) -> list[dict]:
    annotation = row.get("annotation")
    if not isinstance(annotation, dict):
        return [_issue(scope, "incomplete_annotation", "annotation is not an object", oracle_id)]
    issues: list[dict] = []
    status = annotation.get("status")
    if status not in _ANNOTATION_STATUSES:
        issues.append(_issue(scope, "invalid_annotation_status", f"invalid annotation status {status!r}", oracle_id))
    oracle = annotation.get("oracle")
    if not isinstance(oracle, dict):
        issues.append(_issue(scope, "missing_oracle", "annotation.oracle is missing", oracle_id))
    else:
        canonical = oracle.get("canonical_output")
        accepted = oracle.get("accepted_outputs")
        rejected = oracle.get("rejected_outputs")
        if not isinstance(canonical, str) or not canonical:
            issues.append(_issue(scope, "invalid_oracle", "oracle.canonical_output is required", oracle_id))
        if not isinstance(accepted, list) or canonical not in accepted:
            issues.append(_issue(scope, "invalid_oracle", "oracle.canonical_output must be in accepted_outputs", oracle_id))
        if isinstance(accepted, list) and isinstance(rejected, list) and set(accepted) & _rejected_output_strings(rejected):
            issues.append(_issue(scope, "oracle_variant_overlap", "oracle accepted and rejected outputs overlap", oracle_id))
    units = annotation.get("units")
    if not isinstance(units, list):
        issues.append(_issue(scope, "invalid_units", "annotation.units must be an array", oracle_id))
    else:
        for index, unit in enumerate(units):
            if not isinstance(unit, dict):
                issues.append(_issue(scope, "invalid_unit", f"unit {index} must be an object", oracle_id))
                continue
            accepted = unit.get("accepted")
            rejected = unit.get("rejected")
            canonical = unit.get("canonical")
            if not isinstance(accepted, list) or canonical not in accepted:
                issues.append(_issue(scope, "invalid_unit", f"unit {index} canonical must be in accepted", oracle_id))
            if isinstance(accepted, list) and isinstance(rejected, list) and set(accepted) & _rejected_output_strings(rejected):
                issues.append(_issue(scope, "unit_variant_overlap", f"unit {index} accepted and rejected overlap", oracle_id))
    if status == "no_change" and (
        annotation.get("expected_output") != row.get("input")
        or units != []
        or not annotation.get("negative_for")
    ):
        issues.append(_issue(scope, "invalid_no_change", "no_change requires input output, no units, and negative_for", oracle_id))
    return issues


def validate_review_rows(rows: Iterable[dict], *, slot: str) -> dict:
    """Aggregate validation for one reviewer artifact without raising."""
    if slot not in {"A", "B"}:
        raise ValueError("review slot must be A or B")
    rows_list = list(rows)
    expected_status = _REVIEW_COMPLETE_STATUSES[slot]
    indexed: dict[str, dict] = {}
    reviewer_ids: set[str] = set()
    issues: list[dict] = []
    incomplete = 0
    unreviewed = 0
    for index, row in enumerate(rows_list):
        scope = f"review {slot}"
        if not isinstance(row, dict):
            incomplete += 1
            issues.append(_issue(scope, "invalid_row", f"row {index} is not an object"))
            continue
        oracle_id = row.get("sentence_oracle_id")
        oracle_label = oracle_id if isinstance(oracle_id, str) and oracle_id else f"row-{index}"
        row_issues = []
        forbidden = _collect_blind_issues(row)
        row_issues.extend(_issue(scope, "forbidden_blind_field", f"blind review contains forbidden field at {path}", oracle_label) for path in forbidden)
        if row.get("reviewer_slot") != slot:
            row_issues.append(_issue(scope, "slot_mismatch", f"row {oracle_label} is not reviewer slot {slot}", oracle_label))
        if not isinstance(oracle_id, str) or not oracle_id:
            row_issues.append(_issue(scope, "missing_oracle_id", "review row requires sentence_oracle_id", oracle_label))
        elif oracle_id in indexed:
            row_issues.append(_issue(scope, "duplicate_oracle_id", f"duplicate review row {oracle_id}", oracle_id))
        else:
            indexed[oracle_id] = row
        reviewer_id = _reviewer_id(row)
        if reviewer_id is not None:
            reviewer_ids.add(reviewer_id)
        lifecycle = row.get("review") or {}
        lifecycle_status = lifecycle.get("status") if isinstance(lifecycle, dict) else None
        if lifecycle_status == "unreviewed":
            unreviewed += 1
        elif lifecycle_status != expected_status:
            row_issues.append(_issue(scope, "invalid_lifecycle", f"row {oracle_label} lifecycle must be {expected_status}", oracle_label))
        if not isinstance(row.get("annotation"), dict):
            incomplete += 1
        else:
            row_issues.extend(_annotation_issues(row, oracle_id=oracle_label, scope=scope))
        if row_issues:
            issues.extend(row_issues)
        elif isinstance(row.get("annotation"), dict) and lifecycle_status == expected_status:
            pass
    if not reviewer_ids:
        issues.append(_issue(f"review {slot}", "missing_reviewer_id", f"review {slot} has no reviewer_id"))
    elif len(reviewer_ids) != 1:
        issues.append(_issue(f"review {slot}", "unstable_reviewer_id", f"review {slot} must contain one stable reviewer_id"))
    if incomplete:
        issues.append(_issue(f"review {slot}", "incomplete_annotations", f"review {slot} has {incomplete} incomplete annotations"))
    if unreviewed:
        issues.append(_issue(f"review {slot}", "unreviewed_rows", f"review {slot} has {unreviewed} rows in unreviewed lifecycle state"))
    reviewer_id = next(iter(reviewer_ids)) if len(reviewer_ids) == 1 else None
    return {
        "slot": slot,
        "rows": len(rows_list),
        "reviewer_id": reviewer_id,
        "reviewer_ids": sorted(reviewer_ids),
        "completed": sum(1 for row in rows_list if isinstance(row, dict) and isinstance(row.get("annotation"), dict) and isinstance(row.get("review"), dict) and row["review"].get("status") == expected_status and not _annotation_issues(row, oracle_id=str(row.get("sentence_oracle_id", "?")), scope=f"review {slot}")),
        "incomplete": incomplete,
        "unreviewed": unreviewed,
        "issues": issues,
        "ready": not issues,
        "_indexed": indexed,
    }


def _context_issues(left: dict, right: dict, *, oracle_id: str, scope: str) -> list[dict]:
    return [
        _issue(scope, "context_mismatch", f"{oracle_id}: reviewer inputs disagree for {field}", oracle_id)
        for field in ("input", "language", "locale")
        if left.get(field) != right.get(field)
    ]


def review_preflight(
    records: Iterable[dict],
    review_a: Iterable[dict],
    review_b: Iterable[dict],
) -> dict:
    """Return a deterministic aggregate readiness report for canonical re-review."""
    records_list = list(records)
    report_a = validate_review_rows(review_a, slot="A")
    report_b = validate_review_rows(review_b, slot="B")
    issues = list(report_a["issues"]) + list(report_b["issues"])
    canonical_map: dict[str, dict] = {}
    canonical_duplicates: set[str] = set()
    for record in records_list:
        oracle_id = sentence_oracle_id(record)
        if oracle_id in canonical_map:
            canonical_duplicates.add(oracle_id)
        else:
            canonical_map[oracle_id] = record
    for oracle_id in sorted(canonical_duplicates):
        issues.append(_issue("canonical", "duplicate_oracle_id", f"canonical records contain duplicate sentence oracle identity {oracle_id}", oracle_id))
    indexed_a = report_a["_indexed"]
    indexed_b = report_b["_indexed"]
    ids_a = set(indexed_a)
    ids_b = set(indexed_b)
    id_sets_match = ids_a == ids_b
    if not id_sets_match:
        for oracle_id in sorted(ids_b - ids_a):
            issues.append(_issue("cross_review", "missing_in_a", f"review A is missing {oracle_id}", oracle_id))
        for oracle_id in sorted(ids_a - ids_b):
            issues.append(_issue("cross_review", "missing_in_b", f"review B is missing {oracle_id}", oracle_id))
    reviewer_a = report_a["reviewer_id"]
    reviewer_b = report_b["reviewer_id"]
    if reviewer_a and reviewer_b and reviewer_a == reviewer_b:
        issues.append(_issue("cross_review", "shared_reviewer_id", "reviewer A and reviewer B must have distinct reviewer_id values"))
    context_issues: list[dict] = []
    for oracle_id in sorted(ids_a & ids_b):
        context_issues.extend(_context_issues(indexed_a[oracle_id], indexed_b[oracle_id], oracle_id=oracle_id, scope="cross_review"))
    for issue in context_issues:
        issues.append(issue)
    context_match = not context_issues
    canonical_ids = set(canonical_map)
    canonical_identity_match = canonical_ids == ids_a == ids_b
    if canonical_ids != ids_a:
        for oracle_id in sorted(canonical_ids - ids_a):
            issues.append(_issue("canonical", "missing_in_review", f"canonical identity {oracle_id} is missing from review A", oracle_id))
        for oracle_id in sorted(ids_a - canonical_ids):
            issues.append(_issue("canonical", "unknown_review_identity", f"review A contains unknown canonical identity {oracle_id}", oracle_id))
    if canonical_ids != ids_b:
        for oracle_id in sorted(canonical_ids - ids_b):
            issues.append(_issue("canonical", "missing_in_review", f"canonical identity {oracle_id} is missing from review B", oracle_id))
        for oracle_id in sorted(ids_b - canonical_ids):
            issues.append(_issue("canonical", "unknown_review_identity", f"review B contains unknown canonical identity {oracle_id}", oracle_id))
    for oracle_id in sorted(canonical_ids & ids_a):
        for issue in _context_issues(canonical_map[oracle_id], indexed_a[oracle_id], oracle_id=oracle_id, scope="canonical") + _context_issues(canonical_map[oracle_id], indexed_b.get(oracle_id, {}), oracle_id=oracle_id, scope="canonical") if oracle_id in indexed_b else _context_issues(canonical_map[oracle_id], indexed_a[oracle_id], oracle_id=oracle_id, scope="canonical") :
            issues.append(issue)
    issues.sort(key=lambda item: (item.get("scope", ""), item.get("code", ""), item.get("sentence_oracle_id", ""), item.get("message", "")))
    result = {
        "canonical_review_state": "ready" if not issues else "blocked",
        "canonical_records": len(records_list),
        "sentence_oracles": len(canonical_map),
        "review_a": {key: value for key, value in report_a.items() if key != "_indexed"},
        "review_b": {key: value for key, value in report_b.items() if key != "_indexed"},
        "id_sets_match": id_sets_match,
        "context_match": context_match,
        "canonical_identity_match": canonical_identity_match,
        "ready": not issues,
        "issues": issues,
    }
    return result



def _index_completed_reviews(
    rows: Iterable[dict], *, slot: str
 ) -> tuple[dict[str, dict], str]:
    """Strict adapter retaining the historical compare-reviews exceptions."""
    report = validate_review_rows(rows, slot=slot)
    if report["issues"]:
        raise ValueError(report["issues"][0]["message"])
    return report["_indexed"], report["reviewer_id"]


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

def _validate_canonical_decision_shape(decision: dict, *, index: int) -> list[str]:
    """Validate the published canonical decision contract before applying it."""
    label = decision.get("sentence_oracle_id", f"decision-{index}") if isinstance(decision, dict) else f"decision-{index}"
    if not isinstance(decision, dict):
        return [f"{label}: decision must be an object"]
    required = (
        "sentence_oracle_id", "record_id", "family_id", "reviewers", "adjudicator",
        "review_status", "status", "input", "language", "locale", "expected_output",
        "units", "negative_for", "notes", "oracle",
    )
    errors = [f"{label}: decision missing {field}" for field in required if field not in decision]
    for field in ("sentence_oracle_id", "record_id", "family_id", "input", "language", "locale", "notes"):
        if field in decision and (not isinstance(decision[field], str) or not decision[field].strip()):
            errors.append(f"{label}: decision field {field} must be a non-empty string")
    reviewers = decision.get("reviewers")
    if not isinstance(reviewers, list) or len(reviewers) < 2 or any(not isinstance(item, str) or not item.strip() for item in reviewers) or len(set(reviewers)) < 2:
        errors.append(f"{label}: reviewers must contain at least two distinct non-empty strings")
    adjudicator = decision.get("adjudicator")
    if not isinstance(adjudicator, str) or not adjudicator.strip():
        errors.append(f"{label}: adjudicator must be a non-empty string")
    if decision.get("review_status") not in {"adjudicated", "release_ready"}:
        errors.append(f"{label}: review_status must be adjudicated or release_ready")
    if decision.get("status") not in _ANNOTATION_STATUSES:
        errors.append(f"{label}: invalid record status {decision.get('status')!r}")
    units = decision.get("units")
    if not isinstance(units, list):
        errors.append(f"{label}: units must be an array")
    else:
        unit_fields = ("surface", "start", "end", "category", "semantic", "policy", "canonical", "accepted", "rejected", "features")
        for unit_index, unit in enumerate(units):
            if not isinstance(unit, dict):
                errors.append(f"{label}: unit {unit_index} must be an object")
            else:
                errors.extend(f"{label}: unit {unit_index} missing {field}" for field in unit_fields if field not in unit)
    if not isinstance(decision.get("negative_for"), list):
        errors.append(f"{label}: negative_for must be an array")
    if not isinstance(decision.get("expected_output"), (str, type(None))):
        errors.append(f"{label}: expected_output must be a string or null")
    oracle = decision.get("oracle")
    if not isinstance(oracle, dict):
        errors.append(f"{label}: oracle must be an object")
    else:
        canonical = oracle.get("canonical_output")
        accepted = oracle.get("accepted_outputs")
        rejected = oracle.get("rejected_outputs")
        if not isinstance(canonical, str) or not canonical:
            errors.append(f"{label}: oracle.canonical_output is required")
        if not isinstance(accepted, list) or canonical not in accepted:
            errors.append(f"{label}: oracle.canonical_output must be in accepted_outputs")
        if not isinstance(rejected, list):
            errors.append(f"{label}: oracle.rejected_outputs must be an array")
        elif isinstance(accepted, list) and set(accepted) & _rejected_output_strings(rejected):
            errors.append(f"{label}: oracle accepted and rejected outputs overlap")
    if decision.get("status") == "no_change" and (decision.get("expected_output") != decision.get("input") or decision.get("units") != [] or not decision.get("negative_for")):
        errors.append(f"{label}: no_change requires input output, no units, and negative_for")
    return errors


def apply_reviewed_oracles(
    records: Iterable[dict],
    review_a: Iterable[dict],
    review_b: Iterable[dict],
    decisions: Iterable[dict],
) -> tuple[list[dict], list[dict], dict]:
    records_list = list(records)
    decisions_list = list(decisions)
    decision_errors = [
        error
        for index, decision in enumerate(decisions_list)
        for error in _validate_canonical_decision_shape(decision, index=index)
    ]
    if decision_errors:
        raise ValueError("invalid canonical review decision: " + "; ".join(decision_errors))
    comparisons = compare_review_batches(review_a, review_b)
    comparison_map = {item["sentence_oracle_id"]: item for item in comparisons}
    record_map = {sentence_oracle_id(record): record for record in records_list}
    if len(record_map) != len(records_list):
        raise ValueError(
            "canonical records contain duplicate sentence oracle identities"
        )
    decision_map: dict[str, dict] = {}
    for decision in decisions_list:
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
