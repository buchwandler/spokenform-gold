"""Deterministic, bounded packet and checkpoint helpers for v2 review."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from .io import write_json, write_jsonl
from .review import validate_v2_review_rows
from .validation import validate_records

REVIEW_PACKET_FIELDS = (
    "review_schema_version",
    "case_id",
    "reviewer_slot",
    "language",
    "locale",
    "input",
    "family_id",
    "annotation",
    "review",
    "review_guidance",
)
DECISIONS = {"accept", "exclude", "unresolved"}


class PacketError(ValueError):
    """Raised when a packet or merge would violate its contract."""


def serialized_row_bytes(row: Mapping[str, Any]) -> int:
    """Return the UTF-8 bytes used by one deterministic JSONL row."""

    return len(
        (json.dumps(dict(row), ensure_ascii=False, sort_keys=True) + "\n").encode(
            "utf-8"
        )
    )


def select_packet_rows(
    rows: Iterable[Mapping[str, Any]],
    completed_ids: Iterable[str] = (),
    *,
    max_cases: int,
    max_bytes: int,
    identity_field: str = "case_id",
) -> list[dict[str, Any]]:
    """Select the next stable rows within both packet limits."""

    if max_cases <= 0 or max_bytes <= 0:
        raise PacketError("max_cases and max_bytes must be positive")
    completed = set(completed_ids)
    selected: list[dict[str, Any]] = []
    total_bytes = 0
    ordered = sorted(
        (dict(row) for row in rows), key=lambda row: str(row.get(identity_field, ""))
    )
    for row in ordered:
        identity = row.get(identity_field)
        if not isinstance(identity, str) or not identity:
            raise PacketError(f"packet row is missing {identity_field}")
        if identity in completed:
            continue
        if len(selected) >= max_cases:
            break
        row_bytes = serialized_row_bytes(row)
        if row_bytes > max_bytes:
            raise PacketError(
                f"{identity_field} {identity} exceeds max byte budget "
                f"({row_bytes} > {max_bytes})"
            )
        if selected and total_bytes + row_bytes > max_bytes:
            break
        selected.append(row)
        total_bytes += row_bytes
    return selected


def review_packet_rows(
    blind_rows: Iterable[Mapping[str, Any]],
    completed_rows: Iterable[Mapping[str, Any]] = (),
    *,
    max_cases: int,
    max_bytes: int,
) -> list[dict[str, Any]]:
    """Project blind-review rows and select the next uncompleted packet."""

    projected = [
        {key: row[key] for key in REVIEW_PACKET_FIELDS if key in row}
        for row in blind_rows
    ]
    completed_ids = [row.get("case_id") for row in completed_rows]
    return select_packet_rows(
        projected,
        (value for value in completed_ids if isinstance(value, str)),
        max_cases=max_cases,
        max_bytes=max_bytes,
    )


def _public_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if not key.startswith("_")}


def _without_sources(row: Mapping[str, Any]) -> dict[str, Any]:
    result = _public_row(row)
    result.pop("source_observations", None)
    return result


def adjudication_packet_rows(
    cases: Iterable[Mapping[str, Any]],
    contexts: Iterable[Mapping[str, Any]],
    review_a: Iterable[Mapping[str, Any]],
    review_b: Iterable[Mapping[str, Any]],
    completed_decisions: Iterable[Mapping[str, Any]] = (),
    *,
    max_cases: int,
    max_bytes: int,
) -> list[dict[str, Any]]:
    """Project aligned case, context, reviews, and selected source observations."""

    case_map = {row.get("case_id"): _public_row(row) for row in cases}
    context_map = {row.get("case_id"): _public_row(row) for row in contexts}
    a_map = {row.get("case_id"): _public_row(row) for row in review_a}
    b_map = {row.get("case_id"): _public_row(row) for row in review_b}
    case_ids = set(case_map)
    if case_ids != set(context_map) or case_ids != set(a_map) or case_ids != set(b_map):
        raise PacketError(
            "cases, context, review A, and review B case-ID sets must match"
        )
    projected = []
    for case_id in sorted(case_ids):
        case = case_map[case_id]
        projected.append(
            {
                "case_id": case_id,
                "case": _without_sources(case),
                "context": _without_sources(context_map[case_id]),
                "review_a": a_map[case_id],
                "review_b": b_map[case_id],
                "source_observations": case.get("source_observations", []),
            }
        )
    completed_ids = [row.get("case_id") for row in completed_decisions]
    return select_packet_rows(
        projected,
        (value for value in completed_ids if isinstance(value, str)),
        max_cases=max_cases,
        max_bytes=max_bytes,
    )


def _atomic_write(path: str | Path, rows: Iterable[Mapping[str, Any]]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    os.close(fd)
    temporary = Path(name)
    try:
        write_jsonl(temporary, rows)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def _indexed_unique(
    rows: Iterable[Mapping[str, Any]], label: str
) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        identity = row.get("case_id")
        if not isinstance(identity, str) or not identity:
            raise PacketError(f"{label} row is missing case_id")
        if identity in indexed:
            raise PacketError(f"duplicate {label} case_id: {identity}")
        indexed[identity] = _public_row(row)
    return indexed


def merge_review_rows(
    blind_rows: Iterable[Mapping[str, Any]],
    existing_rows: Iterable[Mapping[str, Any]],
    result_rows: Iterable[Mapping[str, Any]],
    *,
    slot: str,
    output: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Merge completed packet rows, rejecting conflicts and preserving blind fields."""

    blind = _indexed_unique(blind_rows, "blind")
    existing = _indexed_unique(existing_rows, "existing review")
    results = _indexed_unique(result_rows, "packet result")
    validation = validate_v2_review_rows(results.values(), slot=slot)
    if validation["issues"]:
        raise PacketError(
            "invalid review result: " + validation["issues"][0]["message"]
        )
    merged = dict(existing)
    for case_id, row in results.items():
        if case_id not in blind:
            raise PacketError(f"review result has unknown case_id: {case_id}")
        expected = blind[case_id]
        for field in (
            "review_schema_version",
            "reviewer_slot",
            "language",
            "locale",
            "input",
            "family_id",
            "review_guidance",
        ):
            if row.get(field) != expected.get(field):
                raise PacketError(
                    f"review result changes blind field {field} for {case_id}"
                )
        previous = merged.get(case_id)
        if previous is not None and previous != row:
            raise PacketError(f"conflicting duplicate review result: {case_id}")
        merged[case_id] = row
    output_rows = [merged[key] for key in sorted(merged)]
    validation = validate_v2_review_rows(output_rows, slot=slot)
    if validation["issues"]:
        raise PacketError(
            "invalid merged review: " + validation["issues"][0]["message"]
        )
    if output is not None:
        _atomic_write(output, output_rows)
    return output_rows


def _validate_decision(
    row: Mapping[str, Any], *, require_structured_blocker: bool = False
) -> None:
    case_id = row.get("case_id")
    if not isinstance(case_id, str) or not case_id:
        raise PacketError("adjudication row is missing case_id")
    if (
        not isinstance(row.get("adjudicator_id"), str)
        or not row["adjudicator_id"].strip()
    ):
        raise PacketError(f"{case_id}: missing adjudicator_id")
    decision = row.get("decision")
    if decision not in DECISIONS:
        raise PacketError(f"{case_id}: invalid adjudication decision")
    blocker = row.get("blocker")
    if decision == "accept":
        if not isinstance(row.get("final_record"), dict):
            raise PacketError(f"{case_id}: accept decision requires final_record")
        if blocker is not None:
            raise PacketError(f"{case_id}: accept decision cannot contain blocker")
    elif decision == "unresolved":
        if not isinstance(blocker, dict):
            raise PacketError(
                f"{case_id}: unresolved decision requires structured blocker"
            )
        required = ("code", "class", "reason", "attempted_resolution")
        if any(
            not isinstance(blocker.get(key), str) or not blocker[key].strip()
            for key in required
        ):
            raise PacketError(f"{case_id}: unresolved blocker is incomplete")
        if blocker.get("retryable") is not True:
            raise PacketError(f"{case_id}: unresolved blocker must be retryable")
    elif decision == "exclude":
        if require_structured_blocker and not isinstance(blocker, dict):
            raise PacketError(
                f"{case_id}: exclude decision requires structured blocker"
            )
        if blocker is not None and not isinstance(blocker, dict):
            raise PacketError(f"{case_id}: exclude blocker must be an object")


def adjudication_repair_packet_rows(
    cases: Iterable[Mapping[str, Any]],
    contexts: Iterable[Mapping[str, Any]],
    review_a: Iterable[Mapping[str, Any]],
    review_b: Iterable[Mapping[str, Any]],
    decisions: Iterable[Mapping[str, Any]],
    diagnostics: Iterable[Mapping[str, Any]],
    *,
    max_cases: int,
    max_bytes: int,
) -> list[dict[str, Any]]:
    """Build a bounded packet for replacing only preflight-invalid decisions."""
    case_map = {row.get("case_id"): _public_row(row) for row in cases}
    context_map = {row.get("case_id"): _public_row(row) for row in contexts}
    a_map = {row.get("case_id"): _public_row(row) for row in review_a}
    b_map = {row.get("case_id"): _public_row(row) for row in review_b}
    decision_map = {row.get("case_id"): _public_row(row) for row in decisions}
    rows = []
    for diagnostic in sorted(diagnostics, key=lambda row: str(row.get("case_id", ""))):
        case_id = diagnostic.get("case_id")
        if case_id not in case_map or case_id not in decision_map:
            raise PacketError(
                f"repair diagnostic references unknown case_id: {case_id}"
            )
        rows.append(
            {
                "case": _without_sources(case_map[case_id]),
                "context": _without_sources(
                    context_map.get(case_id, case_map[case_id])
                ),
                "review_a": a_map[case_id],
                "review_b": b_map[case_id],
                "existing_adjudication": decision_map[case_id],
                "validation_errors": list(diagnostic.get("errors", [])),
                "case_id": case_id,
                "source_observations": case_map[case_id].get("source_observations", []),
            }
        )
    return select_packet_rows(rows, max_cases=max_cases, max_bytes=max_bytes)


def _rows_digest(rows: Iterable[Mapping[str, Any]]) -> str:
    payload = json.dumps(
        [
            {key: value for key, value in row.items() if not key.startswith("_")}
            for row in rows
        ],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def merge_adjudication_rows(
    existing_rows: Iterable[Mapping[str, Any]],
    result_rows: Iterable[Mapping[str, Any]],
    *,
    output: str | Path | None = None,
    require_structured_blocker: bool = False,
) -> list[dict[str, Any]]:
    """Merge adjudication packet results with stable identity and atomic output."""

    existing = _indexed_unique(existing_rows, "existing adjudication")
    results = _indexed_unique(result_rows, "packet result")
    merged = dict(existing)
    adjudicator_ids = {row.get("adjudicator_id") for row in existing.values()}
    for case_id, row in results.items():
        _validate_decision(row, require_structured_blocker=require_structured_blocker)
        adjudicator_ids.add(row.get("adjudicator_id"))
        previous = merged.get(case_id)
        if previous is not None and previous != row:
            raise PacketError(f"conflicting duplicate adjudication result: {case_id}")
        merged[case_id] = dict(row)
    if len(adjudicator_ids) > 1:
        raise PacketError("adjudication must use one stable adjudicator identity")
    output_rows = [merged[key] for key in sorted(merged)]
    for row in output_rows:
        _validate_decision(row, require_structured_blocker=require_structured_blocker)
    if output is not None:
        _atomic_write(output, output_rows)
    return output_rows


def merge_adjudication_repairs(
    existing_rows: Iterable[Mapping[str, Any]],
    result_rows: Iterable[Mapping[str, Any]],
    repair_case_ids: Iterable[str],
    cases: Iterable[Mapping[str, Any]],
    *,
    output: str | Path,
    manifest: str | Path,
) -> list[dict[str, Any]]:
    """Atomically replace exactly the decisions selected for repair."""
    existing = _indexed_unique(existing_rows, "existing adjudication")
    results = _indexed_unique(result_rows, "repair result")
    selected = set(repair_case_ids)
    if set(results) != selected:
        raise PacketError(
            f"repair result case IDs mismatch: missing={sorted(selected - set(results))} "
            f"extra={sorted(set(results) - selected)}"
        )
    case_ids = {row.get("case_id") for row in cases}
    if set(existing) != case_ids:
        raise PacketError("existing adjudication does not cover the batch exactly")
    if not selected <= case_ids:
        raise PacketError("repair packet contains an unknown batch case")
    for row in results.values():
        _validate_decision(row)
    merged = dict(existing)
    for case_id, row in results.items():
        merged[case_id] = dict(row)
    output_rows = [merged[key] for key in sorted(merged)]
    old_hash = _rows_digest(existing.values())
    new_hash = _rows_digest(output_rows)
    _atomic_write(output, output_rows)
    write_json(
        manifest,
        {
            "schema_version": "1",
            "rule": "targeted-adjudication-repair-v1",
            "repaired_case_ids": sorted(selected),
            "old_decisions_sha256": old_hash,
            "new_decisions_sha256": new_hash,
            "case_count": len(output_rows),
        },
    )
    return output_rows


def finalize_adjudication(
    cases: Iterable[Mapping[str, Any]],
    decisions: Iterable[Mapping[str, Any]],
    *,
    output: str | Path | None = None,
    require_structured_blocker: bool = False,
) -> list[dict[str, Any]]:
    """Require an exact case-ID decision set and validate accepted records."""

    case_ids = {row.get("case_id") for row in cases}
    indexed = _indexed_unique(decisions, "adjudication")
    if set(indexed) != case_ids:
        missing = sorted(case_ids - set(indexed))
        extra = sorted(set(indexed) - case_ids)
        raise PacketError(
            f"adjudication case-ID set mismatch: missing={missing} extra={extra}"
        )
    for row in indexed.values():
        _validate_decision(row, require_structured_blocker=require_structured_blocker)
    accepted = [
        row["final_record"] for row in indexed.values() if row["decision"] == "accept"
    ]
    errors = validate_records(accepted)
    if errors:
        raise PacketError("invalid accepted final_record: " + errors[0])
    output_rows = [indexed[key] for key in sorted(indexed)]
    if output is not None:
        _atomic_write(output, output_rows)
    return output_rows
