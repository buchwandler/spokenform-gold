"""Prepare and apply targeted canonical oracle corrections safely."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from .corpus import read_corpus, replace_corpus_record_atomic
from .html_report import render_release_html
from .io import write_json, write_jsonl
from .oracle import oracle_hash
from .review import assert_record_identity_preserved, sentence_oracle_id
from .review_lineage import (
    artifact_sha256,
    record_evidence_history,
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


def _previous_revision(record: dict, evidence: list[dict]) -> int:
    record_id = record.get("id")
    revisions = [
        int(item.get("review_revision", 0))
        for item in _history(record) + list(evidence)
        if (
            isinstance(item, dict)
            and item.get("record_id") == record_id
            and isinstance(item.get("review_revision"), int)
        )
    ]
    return max(revisions, default=0)


def _changed_fields(original: dict, updated: dict) -> list[str]:
    return sorted(
        field for field in _ALLOWED_FIELDS if original.get(field) != updated.get(field)
    )


def validate_correction(
    original: dict, correction: dict, *, evidence: list[dict] | None = None
) -> dict:
    """Validate a semantic correction and return its proposed canonical record."""
    if not isinstance(correction, dict):
        raise TypeError("correction artifact must be an object")
    record_id = original.get("id")
    if correction.get("record_id", record_id) != record_id:
        raise ValueError("correction record_id must match the canonical record")
    old_hash = _current_hash(original)
    supplied_old_hash = correction.get("old_oracle_hash")
    if supplied_old_hash is not None and supplied_old_hash != old_hash:
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
    supplied_new_hash = correction.get("new_oracle_hash")
    if (
        supplied_new_hash is not None
        and supplied_new_hash not in {"", "pending"}
        and supplied_new_hash != updated["oracle_hash"]
    ):
        raise ValueError("new_oracle_hash does not match corrected semantic oracle")
    errors = validate_records([updated])
    if errors:
        raise ValueError("corrected record is invalid: " + "; ".join(errors))
    return updated


def apply_correction(
    original: dict, correction: dict, *, evidence: list[dict] | None = None
) -> tuple[dict, dict]:
    """Return a validated corrected record and mechanically derived history item."""
    evidence_rows = list(evidence or [])
    updated = validate_correction(original, correction, evidence=evidence_rows)
    previous_history = _history(original)
    revision = _previous_revision(original, evidence_rows) + 1
    supplied_revision = correction.get("review_revision")
    if supplied_revision is not None and supplied_revision not in {revision, 0}:
        raise ValueError(f"review_revision must be {revision}")
    reason = correction.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("correction requires reason")
    actor = correction.get("actor") or correction.get("adjudicator")
    reviewed_by = correction.get("reviewed_by", [])
    if not isinstance(actor, str) or not actor.strip():
        raise ValueError("correction requires actor")
    if not isinstance(reviewed_by, list):
        reviewed_by = []
    changed_fields = _changed_fields(original, updated)
    if not changed_fields:
        raise ValueError("correction has no semantic changes or is already applied")
    previous_evidence = record_evidence_history(original["id"], evidence_rows)
    previous_evidence_hash = (
        artifact_sha256(previous_evidence[-1]) if previous_evidence else "legacy-none"
    )
    evidence_basis = {
        "record_id": updated["id"],
        "review_revision": revision,
        "final_oracle_hash": updated["oracle_hash"],
        "changed_fields": changed_fields,
        "reason": reason,
        "actor": actor,
    }
    history_item = {
        "review_revision": revision,
        "old_oracle_hash": _current_hash(original),
        "new_oracle_hash": updated["oracle_hash"],
        "reason": reason,
        "basis": correction.get("basis", "targeted_maintainer_correction"),
        "actor": actor,
        "reviewed_by": list(reviewed_by),
        "adjudicator": correction.get("adjudicator"),
        "changed_fields": changed_fields,
        "previous_review_evidence_hash": previous_evidence_hash,
        "new_review_evidence_hash": artifact_sha256(evidence_basis),
        "previous_sentence_oracle_id": sentence_oracle_id(original),
        "sentence_oracle_id": sentence_oracle_id(updated),
    }
    history_item["artifact_sha256"] = artifact_sha256(history_item)
    review = deepcopy(updated.get("review") or {})
    review["corrected"] = True
    review["status"] = review.get("status", "adjudicated")
    review["correction_history"] = previous_history + [history_item]
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
    history = record_evidence_history(record_id, evidence)
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
        "basis": "targeted_maintainer_correction",
        "actor": "",
        "old_oracle_hash": _current_hash(record),
        "new_oracle_hash": "",
        "reason": "",
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


def _correction_evidence_entry(
    updated: dict, history_item: dict, evidence: list[dict]
) -> list[dict]:
    previous = next(
        (row for row in reversed(evidence) if row.get("record_id") == updated["id"]),
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
    return [row for row in evidence if row.get("record_id") != updated["id"]] + [entry]


def write_correction_application(
    out_root: str | Path,
    records: list[dict],
    updated: dict,
    history_item: dict,
    evidence: list[dict],
    *,
    include_records: bool = True,
) -> dict[str, Path]:
    """Write a preview receipt and evidence artifact for compatibility callers."""
    root = Path(out_root)
    if root.exists() and any(root.iterdir()):
        raise ValueError(
            f"correction application output root must be new or empty: {root}"
        )
    root.mkdir(parents=True, exist_ok=True)
    output_records = [
        updated if row.get("id") == updated.get("id") else row for row in records
    ]
    new_evidence = _correction_evidence_entry(updated, history_item, evidence)
    errors = validate_review_evidence(new_evidence)
    if errors:
        raise ValueError("corrected review evidence is invalid: " + "; ".join(errors))
    records_path = root / "records.jsonl"
    evidence_path = root / "review-evidence.jsonl"
    correction_path = root / "correction.json"
    result_path = root / "result.json"
    receipt_path = root / "receipt.json"
    if include_records:
        write_jsonl(records_path, output_records)
    write_jsonl(evidence_path, new_evidence)
    write_json(correction_path, history_item)
    write_json(
        result_path,
        {
            "record_id": updated["id"],
            "review_revision": history_item["review_revision"],
            "old_oracle_hash": history_item["old_oracle_hash"],
            "new_oracle_hash": history_item["new_oracle_hash"],
            "changed_fields": history_item["changed_fields"],
        },
    )
    write_json(
        receipt_path,
        {
            "record_id": updated["id"],
            "review_revision": history_item["review_revision"],
            "old_oracle_hash": history_item["old_oracle_hash"],
            "new_oracle_hash": history_item["new_oracle_hash"],
            "changed_fields": history_item["changed_fields"],
        },
    )
    report_records = output_records if include_records else [updated]
    render_release_html(
        root / "report.html",
        version=f"correction-{updated['id']}",
        maturity="correction-preview",
        records=report_records,
        coverage={"gaps": []},
        control_coverage={"gaps": []},
        counts={"families": len({row.get("family_id") for row in report_records})},
        review_evidence=new_evidence,
    )
    paths = {
        "evidence": evidence_path,
        "correction": correction_path,
        "result": result_path,
        "receipt": receipt_path,
        "report": root / "report.html",
    }
    if include_records:
        paths["records"] = records_path
    return paths


def apply_correction_to_corpus(
    corpus_root: str | Path,
    lineage_path: str | Path,
    original: dict,
    correction: dict,
    evidence: list[dict],
    output_root: str | Path,
) -> dict[str, Path]:
    """Apply one correction directly to the canonical sharded corpus."""
    updated, history_item = apply_correction(original, correction, evidence=evidence)
    current = read_corpus(corpus_root)
    current_record = next(
        (row for row in current if row.get("id") == original["id"]), None
    )
    if current_record is None:
        raise ValueError(f"unknown canonical record id: {original['id']}")
    if _current_hash(current_record) != history_item["old_oracle_hash"]:
        raise ValueError("canonical record changed since correction was prepared")
    combined_evidence = _correction_evidence_entry(updated, history_item, evidence)
    errors = validate_review_evidence(combined_evidence)
    if errors:
        raise ValueError("corrected review evidence is invalid: " + "; ".join(errors))
    lineage = Path(lineage_path)
    lineage.parent.mkdir(parents=True, exist_ok=True)
    replacement = replace_corpus_record_atomic(corpus_root, original["id"], updated)
    write_jsonl(lineage, combined_evidence)
    paths = write_correction_application(
        output_root, replacement, updated, history_item, evidence, include_records=False
    )
    return paths


__all__ = [
    "apply_correction",
    "apply_correction_to_corpus",
    "prepare_correction_context",
    "validate_correction",
    "write_correction_application",
]
