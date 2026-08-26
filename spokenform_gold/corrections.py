"""Prepare and apply targeted canonical oracle corrections safely."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from .html_report import render_release_html
from .io import write_json, write_jsonl
from .oracle import oracle_hash
from .review import assert_record_identity_preserved, sentence_oracle_id
from .review_lineage import (
    artifact_sha256,
    sanitize_review_artifact,
    validate_review_evidence,
)
from .validation import validate_records

_ALLOWED_FIELDS = {
    "input",
    "expected_output",
    "units",
    "negative_for",
    "notes",
    "status",
    "oracle",
    "language",
    "locale",
}


def _current_hash(record: dict) -> str:
    return record.get("oracle_hash") or oracle_hash(record)


def _history(record: dict) -> list[dict]:
    review = record.get("review")
    if not isinstance(review, dict):
        return []
    value = review.get("correction_history")
    return list(value) if isinstance(value, list) else []


def validate_correction(original: dict, correction: dict) -> dict:
    """Validate correction metadata and return the proposed canonical record."""
    if not isinstance(correction, dict):
        raise TypeError("correction artifact must be an object")
    record_id = original.get("id")
    if correction.get("record_id") != record_id:
        raise ValueError("correction record_id must match the canonical record")
    old_hash = _current_hash(original)
    if correction.get("old_oracle_hash") != old_hash:
        raise ValueError(f"old_oracle_hash does not match canonical record {record_id}")
    proposed = correction.get("new_record") or correction.get("record")
    if not isinstance(proposed, dict):
        raise TypeError("correction artifact requires new_record")
    updated = deepcopy(original)
    for field in _ALLOWED_FIELDS:
        if field in proposed:
            updated[field] = deepcopy(proposed[field])
    if "id" in proposed:
        updated["id"] = proposed["id"]
    assert_record_identity_preserved(original, updated)
    updated["oracle_hash"] = oracle_hash(updated)
    if correction.get("new_oracle_hash") != updated["oracle_hash"]:
        raise ValueError("new_oracle_hash does not match corrected semantic oracle")
    revision = correction.get("review_revision")
    previous_revision = max(
        [
            int(item.get("review_revision", 0))
            for item in _history(original)
            if isinstance(item, dict)
        ]
        or [0]
    )
    if not isinstance(revision, int) or revision <= previous_revision:
        raise ValueError(f"review_revision must be greater than {previous_revision}")
    for field in ("reason", "adjudicator"):
        if not isinstance(correction.get(field), str) or not correction[field].strip():
            raise ValueError(f"correction requires {field}")
    if (
        not isinstance(correction.get("reviewed_by"), list)
        or not correction["reviewed_by"]
    ):
        raise ValueError("correction requires reviewed_by")
    errors = validate_records([updated])
    if errors:
        raise ValueError("corrected record is invalid: " + "; ".join(errors))
    return updated


def apply_correction(original: dict, correction: dict) -> tuple[dict, dict]:
    """Return a validated corrected record and its durable correction history item."""
    updated = validate_correction(original, correction)
    history_item = {
        "review_revision": correction["review_revision"],
        "old_oracle_hash": _current_hash(original),
        "new_oracle_hash": updated["oracle_hash"],
        "reason": correction["reason"],
        "reviewed_by": list(correction["reviewed_by"]),
        "adjudicator": correction["adjudicator"],
        "previous_sentence_oracle_id": sentence_oracle_id(original),
        "sentence_oracle_id": sentence_oracle_id(updated),
        "artifact_sha256": artifact_sha256(correction),
    }
    review = deepcopy(updated.get("review") or {})
    review["corrected"] = True
    review["status"] = review.get("status", "adjudicated")
    review["correction_history"] = _history(original) + [history_item]
    updated["review"] = review
    updated["oracle_hash"] = oracle_hash(updated)
    return updated, history_item


def prepare_correction_context(
    record: dict,
    evidence: list[dict],
    out_root: str | Path,
    *,
    template: str,
) -> dict[str, Path]:
    """Write a self-contained correction context for one permanent record ID."""
    root = Path(out_root)
    if root.exists() and any(root.iterdir()):
        raise ValueError(f"correction output root must be new or empty: {root}")
    root.mkdir(parents=True, exist_ok=True)
    record_id = record.get("id")
    history = sorted(
        (row for row in evidence if row.get("record_id") == record_id),
        key=lambda row: row.get("review_revision", -1),
    )
    context = {
        "record_id": record_id,
        "family_id": record.get("family_id"),
        "current_record": sanitize_review_artifact(record),
        "current_oracle_hash": _current_hash(record),
        "sentence_oracle_id": sentence_oracle_id(record),
        "review_history": sanitize_review_artifact(history),
        "taxonomy": sorted(
            {
                unit.get("category")
                for unit in record.get("units", [])
                if isinstance(unit, dict) and unit.get("category")
            }
        ),
        "policies": sorted(
            {
                unit.get("policy")
                for unit in record.get("units", [])
                if isinstance(unit, dict) and unit.get("policy")
            }
        ),
        "correction_schema": "schemas/oracle-correction.schema.json",
    }
    context_path = root / "context.json"
    write_json(context_path, context)
    decision = {
        "record_id": record_id,
        "old_oracle_hash": _current_hash(record),
        "new_oracle_hash": "",
        "reason": "",
        "reviewed_by": [],
        "adjudicator": "",
        "review_revision": max(
            [
                row.get("review_revision", 0)
                for row in history
                if isinstance(row.get("review_revision"), int)
            ]
            or [0]
        )
        + 1,
        "previous_review_evidence_hash": artifact_sha256(history[-1])
        if history
        else "legacy-none",
        "new_review_evidence_hash": "",
        "new_record": sanitize_review_artifact(record),
        "changed_fields": [],
    }
    decision_path = root / "decision.json"
    write_json(decision_path, decision)
    task_path = root / "correction-task.md"
    task_path.write_text(
        template.replace("<RECORD_ID>", str(record_id)), encoding="utf-8"
    )
    report_path = root / "report.html"
    render_release_html(
        report_path,
        version=f"correction-{record_id}",
        maturity="correction-preview",
        records=[record],
        coverage={"gaps": []},
        control_coverage={"gaps": []},
        counts={"families": 1},
        review_evidence=history,
    )
    return {
        "context": context_path,
        "decision": decision_path,
        "task": task_path,
        "report": report_path,
    }


def write_correction_application(
    out_root: str | Path,
    records: list[dict],
    updated: dict,
    history_item: dict,
    evidence: list[dict],
) -> dict[str, Path]:
    root = Path(out_root)
    if root.exists() and any(root.iterdir()):
        raise ValueError(
            f"correction application output root must be new or empty: {root}"
        )
    root.mkdir(parents=True, exist_ok=True)
    output_records = [
        updated if row.get("id") == updated.get("id") else row for row in records
    ]
    write_jsonl(root / "records.jsonl", output_records)
    new_evidence = [
        row for row in evidence if row.get("record_id") != updated.get("id")
    ]
    previous = next(
        (
            row
            for row in reversed(evidence)
            if row.get("record_id") == updated.get("id")
        ),
        None,
    )
    entry = {
        "record_id": updated["id"],
        "review_revision": history_item["review_revision"],
        "sentence_oracle_id": history_item["sentence_oracle_id"],
        "candidate_ids": previous.get("candidate_ids", []) if previous else [],
        "source_refs": previous.get("source_refs", []) if previous else [],
        "review_a": previous.get("review_a") if previous else None,
        "review_b": previous.get("review_b") if previous else None,
        "comparison": previous.get("comparison") if previous else None,
        "decision": previous.get("decision", {"data": None, "artifact_sha256": None})
        if previous
        else {"data": None, "artifact_sha256": None},
        "final_oracle_hash": updated["oracle_hash"],
        "correction": history_item,
        "correction_history": updated.get("review", {}).get("correction_history", []),
        "legacy": False,
        "evidence_status": "corrected",
    }
    new_evidence.append(entry)
    errors = validate_review_evidence(new_evidence)
    if errors:
        raise ValueError("corrected review evidence is invalid: " + "; ".join(errors))
    write_jsonl(root / "review-evidence.jsonl", new_evidence)
    write_json(root / "correction.json", history_item)
    render_release_html(
        root / "report.html",
        version=f"correction-{updated['id']}",
        maturity="correction-preview",
        records=output_records,
        coverage={"gaps": []},
        control_coverage={"gaps": []},
        counts={"families": len({row.get("family_id") for row in output_records})},
        review_evidence=new_evidence,
    )
    return {
        "records": root / "records.jsonl",
        "evidence": root / "review-evidence.jsonl",
        "correction": root / "correction.json",
        "report": root / "report.html",
    }


__all__ = [
    "apply_correction",
    "prepare_correction_context",
    "validate_correction",
    "write_correction_application",
]
