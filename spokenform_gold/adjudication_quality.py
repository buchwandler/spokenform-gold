"""Deterministic quality gates for LLM adjudication artifacts."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from typing import Any

from .review import validate_review_rows

HARD_BLOCKER_CODES = {
    "missing_context",
    "source_corrupt",
    "source_identity_conflict",
    "language_uncertain",
    "locale_uncertain",
    "policy_not_representable",
    "license_disposition_unresolved",
    "taxonomy_missing",
    "review_evidence_invalid",
    "semantic_ambiguity_irreducible",
    "other_hard_blocker",
}

PROMOTABLE_DECISIONS = {"promote_curated", "promote_upstream"}
BLOCKED_DECISIONS = {"needs_review", "quarantine"}
GENERIC_DISAGREEMENT_TEXT = {
    "a/b disagreement",
    "a and b disagree",
    "reviewer disagreement",
    "reviewers disagree",
    "a/b reviewers disagree",
}


def _non_empty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _issue(code: str, message: str, **extra: Any) -> dict[str, Any]:
    return {"code": code, "message": message, **extra}


def _validate_blocker(decision: dict, *, index: int) -> list[dict[str, Any]]:
    if decision.get("decision") not in BLOCKED_DECISIONS:
        return []
    label = str(decision.get("candidate_id", f"decision-{index}"))
    issues: list[dict[str, Any]] = []
    code = decision.get("blocker_code")
    reason = decision.get("blocker_reason")
    attempted = decision.get("attempted_resolution")
    if code not in HARD_BLOCKER_CODES:
        issues.append(
            _issue(
                "invalid_blocker_code",
                f"{label}: {decision.get('decision')} requires a named hard blocker code",
                candidate_id=label,
            )
        )
    for field, value in (
        ("blocker_reason", reason),
        ("attempted_resolution", attempted),
    ):
        if not _non_empty(value):
            issues.append(
                _issue(
                    "missing_blocker_metadata",
                    f"{label}: {decision.get('decision')} requires {field}",
                    candidate_id=label,
                )
            )
    normalized_reason = " ".join(str(reason or "").casefold().split())
    if normalized_reason in GENERIC_DISAGREEMENT_TEXT or normalized_reason in {
        "a/b disagreement alone",
        "a and b disagree alone",
    }:
        issues.append(
            _issue(
                "generic_disagreement_blocker",
                f"{label}: A/B disagreement alone is not a hard blocker",
                candidate_id=label,
            )
        )
    return issues


def _validate_promotable(decision: dict, *, index: int) -> list[dict[str, Any]]:
    if decision.get("decision") not in PROMOTABLE_DECISIONS:
        return []
    label = str(decision.get("candidate_id", f"decision-{index}"))
    required = ("record_id", "family_id", "status", "input", "language", "locale", "expected_output", "units", "negative_for", "notes", "oracle", "license_disposition")
    return [
        _issue(
            "incomplete_promotable_decision",
            f"{label}: promotable decision is missing {field}",
            candidate_id=label,
        )
        for field in required
        if field not in decision
    ]


def validate_adjudication_batch(
    candidates: Iterable[dict],
    review_a: Iterable[dict],
    review_b: Iterable[dict],
    comparison: Iterable[dict],
    decisions: Iterable[dict],
    *,
    max_unresolved_percent: float | None = None,
) -> dict[str, Any]:
    """Return a deterministic readiness report for one adjudication batch."""
    candidate_rows = list(candidates)
    decision_rows = list(decisions)
    candidate_ids = [row.get("id") for row in candidate_rows]
    issues: list[dict[str, Any]] = []
    if any(not _non_empty(value) for value in candidate_ids):
        issues.append(_issue("invalid_candidate_id", "every candidate requires a non-empty id"))
    duplicate_candidates = sorted(
        key for key, count in Counter(candidate_ids).items() if key and count > 1
    )
    if duplicate_candidates:
        issues.append(
            _issue("duplicate_candidates", f"duplicate candidate IDs: {duplicate_candidates}")
        )
    candidate_set = {value for value in candidate_ids if isinstance(value, str)}

    decision_ids = [row.get("candidate_id") if isinstance(row, dict) else None for row in decision_rows]
    duplicate_decisions = sorted(
        key for key, count in Counter(decision_ids).items() if key and count > 1
    )
    if duplicate_decisions:
        issues.append(
            _issue("duplicate_decisions", f"duplicate decision candidate IDs: {duplicate_decisions}")
        )
    decision_set = {value for value in decision_ids if isinstance(value, str)}
    if len(candidate_rows) != len(decision_rows):
        issues.append(
            _issue(
                "count_mismatch",
                f"candidate count {len(candidate_rows)} != decision count {len(decision_rows)}",
            )
        )
    if candidate_set != decision_set:
        issues.append(
            _issue(
                "candidate_id_set_mismatch",
                f"candidate/decision ID sets differ; missing={sorted(candidate_set - decision_set)}, unexpected={sorted(decision_set - candidate_set)}",
            )
        )

    report_a = validate_review_rows(review_a, slot="A")
    report_b = validate_review_rows(review_b, slot="B")
    if report_a["issues"]:
        issues.extend(report_a["issues"])
    if report_b["issues"]:
        issues.extend(report_b["issues"])
    reviewer_a = report_a.get("reviewer_id")
    reviewer_b = report_b.get("reviewer_id")
    if reviewer_a and reviewer_b and reviewer_a == reviewer_b:
        issues.append(_issue("shared_reviewer", "reviewer A and B identities must be distinct"))

    comparison_rows = list(comparison)
    comparison_map = {row.get("sentence_oracle_id"): row for row in comparison_rows if isinstance(row, dict)}
    record_ids: list[str] = []
    counts: Counter[str] = Counter()
    blocker_counts: Counter[str] = Counter()
    critic_counts: Counter[str] = Counter()
    for index, decision in enumerate(decision_rows):
        if not isinstance(decision, dict):
            issues.append(_issue("invalid_decision", f"decision {index} is not an object"))
            continue
        disposition = decision.get("decision")
        counts[str(disposition)] += 1
        issues.extend(_validate_blocker(decision, index=index))
        issues.extend(_validate_promotable(decision, index=index))
        blocker_code = decision.get("blocker_code")
        if isinstance(blocker_code, str) and blocker_code:
            blocker_counts[blocker_code] += 1
        critic = decision.get("critic") or decision.get("critic_status")
        if isinstance(critic, str) and critic:
            critic_counts[critic] += 1
        adjudicator = decision.get("adjudicator")
        if not _non_empty(adjudicator):
            issues.append(_issue("missing_adjudicator", f"decision {index} requires adjudicator"))
        reviewers = decision.get("reviewers")
        if not isinstance(reviewers, list) or len({item for item in reviewers if _non_empty(item)}) < 2:
            issues.append(_issue("invalid_reviewers", f"decision {index} requires two distinct reviewers"))
        elif reviewer_a and reviewer_b and not {reviewer_a, reviewer_b}.issubset(set(reviewers)):
            issues.append(_issue("reviewer_identity_mismatch", f"decision {index} reviewers do not match A/B evidence"))
        record_id = decision.get("record_id")
        if record_id is not None:
            if not _non_empty(record_id):
                issues.append(_issue("invalid_record_id", f"decision {index} has an invalid record_id"))
            else:
                record_ids.append(record_id)
        if disposition == "promote_upstream" and not _non_empty(decision.get("license_disposition")):
            issues.append(_issue("invalid_license_disposition", f"decision {index} requires license_disposition"))
        if "source_duplicate" in (decision.get("source_error_codes") or []):
            if disposition != "reject":
                issues.append(_issue("source_duplicate_disposition", f"decision {index} source_duplicate must be rejected"))
            if not _non_empty(decision.get("represented_by_record_id")):
                issues.append(_issue("source_duplicate_link", f"decision {index} source_duplicate requires represented_by_record_id"))
        oracle_id = decision.get("sentence_oracle_id")
        if oracle_id and oracle_id not in comparison_map:
            issues.append(_issue("missing_comparison", f"decision {index} references missing comparison {oracle_id}"))

    duplicate_record_ids = sorted(key for key, count in Counter(record_ids).items() if count > 1)
    if duplicate_record_ids:
        issues.append(_issue("duplicate_record_ids", f"duplicate final record IDs: {duplicate_record_ids}"))
    unresolved = counts.get("needs_review", 0) + counts.get("quarantine", 0)
    total = len(candidate_rows)
    unresolved_percent = (100.0 * unresolved / total) if total else 0.0
    if max_unresolved_percent is not None and unresolved_percent > max_unresolved_percent:
        issues.append(
            _issue(
                "mass_deferral",
                f"unresolved decisions are {unresolved_percent:.2f}% (limit {max_unresolved_percent:.2f}%)",
                unresolved_percentage=unresolved_percent,
            )
        )
    return {
        "ready": not issues,
        "candidates": total,
        "comparisons": len(comparison_rows),
        "decisions": len(decision_rows),
        "decision_counts": dict(sorted(counts.items())),
        "blocker_counts": dict(sorted(blocker_counts.items())),
        "critic_counts": dict(sorted(critic_counts.items())),
        "unresolved": unresolved,
        "unresolved_percentage": unresolved_percent,
        "reviewer_a": reviewer_a,
        "reviewer_b": reviewer_b,
        "issues": sorted(issues, key=lambda item: (item.get("code", ""), item.get("message", ""))),
    }


__all__ = ["HARD_BLOCKER_CODES", "validate_adjudication_batch"]
