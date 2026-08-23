"""Durable, sanitized review lineage keyed by canonical ``record.id``."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from copy import deepcopy
from pathlib import Path
from typing import Any

from .io import write_jsonl
from .oracle import oracle_hash
from .review import sentence_oracle_id

_FORBIDDEN = {"upstream_expected", "upstream_output", "current_output", "spokenform_output"}
_TRANSIENT = {"_source_file", "_source_line"}


def sanitize_review_artifact(value: Any) -> Any:
    """Remove blind-review forbidden and local ingestion-only fields recursively."""
    if isinstance(value, dict):
        return {
            key: sanitize_review_artifact(child)
            for key, child in value.items()
            if key not in _FORBIDDEN and key not in _TRANSIENT
        }
    if isinstance(value, list):
        return [sanitize_review_artifact(child) for child in value]
    return deepcopy(value)


def artifact_sha256(value: Any) -> str:
    payload = json.dumps(
        sanitize_review_artifact(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _source_ref(source: dict | None) -> dict | None:
    if not isinstance(source, dict):
        return None
    benchmark = source.get("benchmark")
    source_id = source.get("source_id")
    if not isinstance(benchmark, str) or not isinstance(source_id, str):
        return None
    return {"benchmark": benchmark, "source_id": source_id}


def _unique_refs(values: Iterable[dict]) -> list[dict]:
    result: dict[tuple[str, str], dict] = {}
    for value in values:
        ref = _source_ref(value)
        if ref:
            result[(ref["benchmark"], ref["source_id"])] = ref
    return [result[key] for key in sorted(result)]


def _row_map(rows: Iterable[dict], key: str) -> dict[str, dict]:
    return {
        row[key]: row
        for row in rows
        if isinstance(row, dict) and isinstance(row.get(key), str) and row[key]
    }


def _decision_key(decision: dict) -> str | None:
    candidate_id = decision.get("candidate_id")
    return candidate_id if isinstance(candidate_id, str) and candidate_id else None


def _revision_for(record_id: str, previous: Iterable[dict]) -> int:
    revisions = [
        int(entry.get("review_revision", 0))
        for entry in previous
        if isinstance(entry, dict)
        and entry.get("record_id") == record_id
        and isinstance(entry.get("review_revision"), int)
    ]
    return max(revisions, default=0) + 1


def build_review_evidence(
    candidates: Iterable[dict],
    review_a: Iterable[dict],
    review_b: Iterable[dict],
    comparisons: Iterable[dict],
    decisions: Iterable[dict],
    *,
    records: Iterable[dict] | None = None,
    previous: Iterable[dict] = (),
) -> list[dict]:
    """Build one durable evidence entry per final canonical record.

    ``records`` is preferred for promotion output.  When absent, promotable
    decision ``record_id`` values are used, which also supports canonical
    re-review artifacts.
    """
    candidate_rows = list(candidates)
    record_rows = list(records or [])
    review_a_map = _row_map(review_a, "sentence_oracle_id")
    review_b_map = _row_map(review_b, "sentence_oracle_id")
    comparison_map = _row_map(comparisons, "sentence_oracle_id")
    decision_rows = [row for row in decisions if isinstance(row, dict)]
    candidate_map = {
        row.get("id"): row
        for row in candidate_rows
        if isinstance(row.get("id"), str) and row.get("id")
    }
    decision_by_record: dict[str, list[dict]] = {}
    for decision in decision_rows:
        record_id = decision.get("record_id") or decision.get("represented_by_record_id")
        if isinstance(record_id, str) and record_id:
            decision_by_record.setdefault(record_id, []).append(decision)

    targets: dict[str, dict] = {
        record["id"]: record
        for record in record_rows
        if isinstance(record, dict) and isinstance(record.get("id"), str)
    }
    for decision in decision_rows:
        record_id = decision.get("record_id")
        if isinstance(record_id, str) and record_id and record_id not in targets:
            targets[record_id] = candidate_map.get(decision.get("candidate_id"), decision)

    previous_rows = list(previous)
    entries: list[dict] = []
    for record_id in sorted(targets):
        record = targets[record_id]
        matched = decision_by_record.get(record_id, [])
        if not matched and record_id in candidate_map:
            matched = [
                decision
                for decision in decision_rows
                if decision.get("candidate_id") == record_id
            ]
        primary = next(
            (decision for decision in matched if decision.get("record_id") == record_id),
            matched[0] if matched else {},
        )
        candidate_ids = sorted(
            {
                value
                for decision in matched
                for value in [decision.get("candidate_id")]
                if isinstance(value, str) and value
            }
        )
        if not candidate_ids and record_id in candidate_map:
            candidate_ids = [record_id]
        source_refs = _unique_refs(
            [candidate_map[item].get("source", {}) for item in candidate_ids if item in candidate_map]
            + [record.get("source", {})]
        )
        oracle_id = primary.get("sentence_oracle_id")
        if not isinstance(oracle_id, str) or not oracle_id:
            oracle_id = sentence_oracle_id(record)
        a = sanitize_review_artifact(review_a_map.get(oracle_id)) if oracle_id in review_a_map else None
        b = sanitize_review_artifact(review_b_map.get(oracle_id)) if oracle_id in review_b_map else None
        comparison = sanitize_review_artifact(comparison_map.get(oracle_id)) if oracle_id in comparison_map else None
        decision = sanitize_review_artifact(primary) if primary else None
        review_revision = _revision_for(record_id, previous_rows)
        entry: dict[str, Any] = {
            "record_id": record_id,
            "review_revision": review_revision,
            "sentence_oracle_id": oracle_id,
            "candidate_ids": candidate_ids,
            "source_refs": source_refs,
            "review_a": {
                "reviewer_id": a.get("reviewer_id") if isinstance(a, dict) else None,
                "annotation": a.get("annotation") if isinstance(a, dict) else None,
                "artifact_sha256": artifact_sha256(
                    {
                        "reviewer_id": a.get("reviewer_id"),
                        "annotation": a.get("annotation"),
                    }
                ) if a is not None else None,
            },
            "review_b": {
                "reviewer_id": b.get("reviewer_id") if isinstance(b, dict) else None,
                "annotation": b.get("annotation") if isinstance(b, dict) else None,
                "artifact_sha256": artifact_sha256(
                    {
                        "reviewer_id": b.get("reviewer_id"),
                        "annotation": b.get("annotation"),
                    }
                ) if b is not None else None,
            },
            "comparison": {
                "dimensions": comparison.get("dimensions") if isinstance(comparison, dict) else {},
                "disagreement": comparison.get("disagreement", False) if isinstance(comparison, dict) else False,
                "artifact_sha256": artifact_sha256(
                    {
                        "dimensions": comparison.get("dimensions") if isinstance(comparison, dict) else {},
                        "disagreement": comparison.get("disagreement", False) if isinstance(comparison, dict) else False,
                    }
                ) if comparison is not None else None,
            },
            "decision": {
                "adjudicator": decision.get("adjudicator") if isinstance(decision, dict) else None,
                "disposition": decision.get("decision") if isinstance(decision, dict) else None,
                "artifact_sha256": artifact_sha256(decision) if decision is not None else None,
                "data": decision,
            },
            "final_oracle_hash": record.get("oracle_hash") or oracle_hash(record),
            "correction": None,
        }
        if isinstance(record.get("review"), dict) and record["review"].get("correction_history"):
            entry["correction_history"] = sanitize_review_artifact(record["review"]["correction_history"])
        if a is None or b is None or comparison is None or decision is None:
            entry["legacy"] = True
            entry["evidence_status"] = "legacy_review_metadata_only"
        else:
            entry["legacy"] = False
            entry["evidence_status"] = "complete"
        entries.append(entry)
    return entries


def backfill_legacy_evidence(records: Iterable[dict]) -> list[dict]:
    """Create explicit revision-zero entries without fabricating review evidence."""
    entries = []
    for record in sorted(records, key=lambda row: row.get("id", "")):
        record_id = record.get("id")
        if not isinstance(record_id, str) or not record_id:
            continue
        entries.append(
            {
                "record_id": record_id,
                "review_revision": 0,
                "sentence_oracle_id": sentence_oracle_id(record),
                "candidate_ids": [],
                "source_refs": _unique_refs([record.get("source", {})]),
                "review_a": None,
                "review_b": None,
                "comparison": None,
                "decision": {"data": None, "artifact_sha256": None},
                "final_oracle_hash": record.get("oracle_hash") or oracle_hash(record),
                "correction": None,
                "legacy": True,
                "evidence_status": "legacy_review_metadata_only",
            }
        )
    return entries


def validate_review_evidence(entries: Iterable[dict]) -> list[str]:
    errors: list[str] = []
    seen: set[tuple[str, int]] = set()
    for index, entry in enumerate(entries):
        label = f"evidence[{index}]"
        if not isinstance(entry, dict):
            errors.append(f"{label}: entry must be an object")
            continue
        record_id = entry.get("record_id")
        revision = entry.get("review_revision")
        if not isinstance(record_id, str) or not record_id:
            errors.append(f"{label}: record_id is required")
        if not isinstance(revision, int) or revision < 0:
            errors.append(f"{label}: review_revision must be a non-negative integer")
        if isinstance(record_id, str) and isinstance(revision, int):
            key = (record_id, revision)
            if key in seen:
                errors.append(f"{label}: duplicate record/revision {record_id}/{revision}")
            seen.add(key)
        for section in ("review_a", "review_b"):
            value = entry.get(section)
            if isinstance(value, dict) and value.get("artifact_sha256"):
                payload = {"reviewer_id": value.get("reviewer_id"), "annotation": value.get("annotation")}
                if value["artifact_sha256"] != artifact_sha256(payload):
                    errors.append(f"{label}: {section} artifact hash mismatch")
        comparison = entry.get("comparison")
        if isinstance(comparison, dict) and comparison.get("artifact_sha256"):
            payload = {key: comparison.get(key) for key in ("dimensions", "disagreement")}
            if comparison["artifact_sha256"] != artifact_sha256(payload):
                errors.append(f"{label}: comparison artifact hash mismatch")
        decision = entry.get("decision")
        if (
            isinstance(decision, dict)
            and decision.get("artifact_sha256")
            and decision["artifact_sha256"] != artifact_sha256(decision.get("data"))
        ):
            errors.append(f"{label}: decision artifact hash mismatch")
        if any(_contains_forbidden(entry, key) for key in _FORBIDDEN):
            errors.append(f"{label}: forbidden blind field leaked into evidence")
    return errors


def _contains_forbidden(value: Any, needle: str) -> bool:
    if isinstance(value, dict):
        return needle in value or any(_contains_forbidden(child, needle) for child in value.values())
    if isinstance(value, list):
        return any(_contains_forbidden(child, needle) for child in value)
    return False


def resolve_record_evidence(record_id: str, records: Iterable[dict], evidence: Iterable[dict]) -> dict:
    record = next((row for row in records if row.get("id") == record_id), None)
    if record is None:
        raise KeyError(f"unknown canonical record id: {record_id}")
    history = sorted(
        (row for row in evidence if row.get("record_id") == record_id),
        key=lambda row: row.get("review_revision", -1),
    )
    return {"record": sanitize_review_artifact(record), "evidence": history, "review_revisions": len(history)}


def write_review_evidence(path: str | Path, entries: Iterable[dict]) -> None:
    validated = list(entries)
    errors = validate_review_evidence(validated)
    if errors:
        raise ValueError("invalid review evidence: " + "; ".join(errors))
    write_jsonl(path, sorted(validated, key=lambda row: (row.get("record_id", ""), row.get("review_revision", 0))))


__all__ = [
    "artifact_sha256",
    "backfill_legacy_evidence",
    "build_review_evidence",
    "resolve_record_evidence",
    "sanitize_review_artifact",
    "validate_review_evidence",
    "write_review_evidence",
]
