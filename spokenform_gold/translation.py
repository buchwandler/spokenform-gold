"""License-aware, sentence-independent translation candidate workflow."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from .io import write_json, write_jsonl
from .packets import PacketError, select_packet_rows

TRANSLATION_SCHEMA_VERSION = "1.0.0"
TRANSLATION_PROTOCOL_VERSION = "translation-protocol-1.0.0"
TARGET_LOCALES = {"ja": "ja-JP", "ko": "ko-KR", "zh": "zh-CN"}
ALLOWED_DECISIONS = {"propose", "not_transferable", "needs_source_context"}
ADJUDICATION_DECISIONS = {"accept_a", "accept_b", "merge", "exclude", "unresolved"}
FORBIDDEN_TRANSLATION_FIELDS = {"current_output", "spokenform_output", "gold_decision"}


class TranslationError(ValueError):
    """Raised when a translation artifact violates its contract."""


class TranslationLicenseError(TranslationError):
    """Raised when a source cannot legally seed an adapted candidate."""


def _sha256(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _public(row: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if not key.startswith("_")}


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


def _indexed(
    rows: Iterable[Mapping[str, Any]], label: str
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        identity = row.get("translation_case_id")
        if not isinstance(identity, str) or not identity:
            raise PacketError(f"{label} row is missing translation_case_id")
        if identity in result:
            raise PacketError(f"duplicate {label} translation_case_id: {identity}")
        result[identity] = _public(row)
    return result


def validate_target_locale(language: str, locale: str) -> None:
    expected = TARGET_LOCALES.get(language)
    if expected is None or locale != expected:
        raise TranslationError(
            f"unsupported target language/locale: {language!r}/{locale!r}; "
            f"expected one of {sorted(TARGET_LOCALES.items())}"
        )


def _source_observations(record: Mapping[str, Any]) -> list[dict[str, Any]]:
    observations = record.get("source_observations")
    if isinstance(observations, list):
        return [item for item in observations if isinstance(item, dict)]
    source = record.get("source")
    return [source] if isinstance(source, dict) else []


def _adaptation_source(record: Mapping[str, Any]) -> dict[str, Any]:
    allowed = []
    for source in _source_observations(record):
        benchmark = source.get("benchmark")
        license_id = source.get("license_id") or source.get("license")
        if (
            benchmark == "spokenform_curated"
            and license_id in {"CC-BY-4.0", "CC BY 4.0"}
        ) or (
            source.get("adaptation_permitted") is True
            and source.get("redistribution_permitted") is True
        ):
            allowed.append(source)
    if not allowed:
        raise TranslationLicenseError(
            f"source record {record.get('id', '<unknown>')} is not allow-listed for adaptation"
        )
    return min(
        allowed,
        key=lambda source: (
            str(source.get("benchmark", "")),
            str(source.get("source_version", "")),
            str(source.get("source_id", "")),
        ),
    )


def translation_case_id(
    source_record_id: str,
    source_oracle_hash: str,
    target_language: str,
    target_locale: str,
    requested_mode: str,
) -> str:
    payload = (
        f"{TRANSLATION_PROTOCOL_VERSION}|{source_record_id}|{source_oracle_hash}|"
        f"{target_language}|{target_locale}|{requested_mode}"
    )
    return "tr-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]


def build_translation_tasks(
    records: Iterable[Mapping[str, Any]],
    *,
    target_language: str,
    target_locale: str,
    requested_mode: str = "locale_transplant",
) -> list[dict[str, Any]]:
    validate_target_locale(target_language, target_locale)
    requested_mode = requested_mode.replace("-", "_")
    if requested_mode not in {"semantic_translation", "locale_transplant"}:
        raise TranslationError(f"invalid translation mode: {requested_mode}")

    tasks = []
    for record in sorted(
        (dict(row) for row in records), key=lambda row: str(row.get("id", ""))
    ):
        source_id = record.get("id")
        if not isinstance(source_id, str) or not source_id:
            raise TranslationError("translation seed is missing record id")
        source = _adaptation_source(record)
        oracle_hash = record.get("oracle_hash")
        if not isinstance(oracle_hash, str) or not oracle_hash:
            raise TranslationError(f"source record {source_id} is missing oracle_hash")
        task = {
            "translation_schema_version": TRANSLATION_SCHEMA_VERSION,
            "translation_case_id": translation_case_id(
                source_id, oracle_hash, target_language, target_locale, requested_mode
            ),
            "source_record_id": source_id,
            "source_oracle_hash": oracle_hash,
            "source_language": record.get("language"),
            "source_locale": record.get("locale"),
            "target_language": target_language,
            "target_locale": target_locale,
            "source_input": record.get("input"),
            "source_status": record.get("status"),
            "source_oracle": record.get("oracle") or {},
            "source_units": record.get("units") or [],
            "parent_family_id": record.get("family_id"),
            "requested_mode": requested_mode,
            "source_license": {
                key: source.get(key)
                for key in (
                    "benchmark",
                    "license",
                    "license_id",
                    "source_id",
                    "source_version",
                )
                if source.get(key) is not None
            },
            "translation": None,
            "review": {"slot": None, "status": "unreviewed"},
        }
        tasks.append(task)
    return tasks


def translation_blind_row(task: Mapping[str, Any], slot: str) -> dict[str, Any]:
    if slot not in {"A", "B"}:
        raise TranslationError("translator slot must be A or B")
    return {
        "translation_schema_version": TRANSLATION_SCHEMA_VERSION,
        "translation_case_id": task["translation_case_id"],
        "translator_slot": slot,
        "source_record_id": task["source_record_id"],
        "source_oracle_hash": task["source_oracle_hash"],
        "source_language": task["source_language"],
        "source_locale": task["source_locale"],
        "target_language": task["target_language"],
        "target_locale": task["target_locale"],
        "source_input": task["source_input"],
        "source_status": task["source_status"],
        "source_oracle": task["source_oracle"],
        "source_units": task["source_units"],
        "parent_family_id": task["parent_family_id"],
        "requested_mode": task["requested_mode"],
        "translation": None,
        "review": {"status": "unreviewed"},
    }


def prepare_translation_batch(
    records: Iterable[Mapping[str, Any]],
    output_root: str | Path,
    *,
    target_language: str,
    target_locale: str,
    batch_id: str,
    requested_mode: str = "locale_transplant",
) -> dict[str, Any]:
    root = Path(output_root)
    if root.exists() and any(root.iterdir()):
        raise TranslationError(f"output root must be new or empty: {root}")
    root.mkdir(parents=True, exist_ok=True)
    tasks = build_translation_tasks(
        records,
        target_language=target_language,
        target_locale=target_locale,
        requested_mode=requested_mode,
    )
    write_jsonl(root / "tasks.jsonl", tasks)
    write_jsonl(
        root / "a.blind.jsonl", [translation_blind_row(task, "A") for task in tasks]
    )
    write_jsonl(
        root / "b.blind.jsonl", [translation_blind_row(task, "B") for task in tasks]
    )
    metadata = {
        "translation_schema_version": TRANSLATION_SCHEMA_VERSION,
        "batch_id": batch_id,
        "target_language": target_language,
        "target_locale": target_locale,
        "requested_mode": requested_mode,
        "case_count": len(tasks),
        "state": "awaiting_translation",
        "translator_a": None,
        "translator_b": None,
        "adjudicator": None,
    }
    write_json(root / "batch.json", metadata)
    return metadata


def translation_packet_rows(
    blind_rows: Iterable[Mapping[str, Any]],
    completed_rows: Iterable[Mapping[str, Any]] = (),
    *,
    max_cases: int,
    max_bytes: int,
) -> list[dict[str, Any]]:
    return select_packet_rows(
        blind_rows,
        (row.get("translation_case_id") for row in completed_rows),
        max_cases=max_cases,
        max_bytes=max_bytes,
        identity_field="translation_case_id",
    )


def _validate_translation_row(row: Mapping[str, Any], slot: str) -> None:
    case_id = row.get("translation_case_id")
    if not isinstance(case_id, str) or not case_id:
        raise PacketError("translation row is missing translation_case_id")
    if row.get("translation_schema_version") != TRANSLATION_SCHEMA_VERSION:
        raise PacketError(f"{case_id}: invalid translation schema version")
    if row.get("translator_slot") != slot:
        raise PacketError(f"{case_id}: wrong translator slot")
    if (
        not isinstance(row.get("translator_id"), str)
        or not row["translator_id"].strip()
    ):
        raise PacketError(f"{case_id}: translator_id is required")
    if (row.get("review") or {}).get("status") != "completed":
        raise PacketError(f"{case_id}: translation row is not complete")
    translation = row.get("translation")
    if not isinstance(translation, dict):
        raise PacketError(f"{case_id}: translation is required")
    decision = translation.get("decision")
    if decision not in ALLOWED_DECISIONS:
        raise PacketError(f"{case_id}: invalid translation decision")
    if decision == "propose":
        if (
            not isinstance(translation.get("target_input"), str)
            or not translation["target_input"].strip()
        ):
            raise PacketError(f"{case_id}: proposal requires non-empty target_input")
        if translation.get("transfer_relation") not in {"equivalent", "adapted"}:
            raise PacketError(f"{case_id}: proposal requires transfer_relation")
    if _contains_forbidden_field(row):
        raise PacketError(
            f"{case_id}: translation row contains forbidden current output evidence"
        )


def _contains_forbidden_field(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            key in FORBIDDEN_TRANSLATION_FIELDS or _contains_forbidden_field(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_forbidden_field(item) for item in value)
    return False


def merge_translation_rows(
    blind_rows: Iterable[Mapping[str, Any]],
    existing_rows: Iterable[Mapping[str, Any]],
    result_rows: Iterable[Mapping[str, Any]],
    *,
    slot: str,
    output: str | Path | None = None,
) -> list[dict[str, Any]]:
    blind = _indexed(blind_rows, "blind")
    existing = _indexed(existing_rows, "existing translation")
    results = _indexed(result_rows, "packet result")
    merged = dict(existing)
    protected = (
        "translation_schema_version",
        "translator_slot",
        "source_record_id",
        "source_oracle_hash",
        "source_language",
        "source_locale",
        "target_language",
        "target_locale",
        "source_input",
        "parent_family_id",
        "requested_mode",
    )
    for case_id, row in results.items():
        _validate_translation_row(row, slot)
        if case_id not in blind:
            raise PacketError(f"translation result has unknown case_id: {case_id}")
        expected = blind[case_id]
        for field in protected:
            if row.get(field) != expected.get(field):
                raise PacketError(
                    f"translation result changes blind field {field} for {case_id}"
                )
        previous = merged.get(case_id)
        if previous is not None and previous != row:
            raise PacketError(f"conflicting duplicate translation result: {case_id}")
        merged[case_id] = row
    output_rows = [merged[key] for key in sorted(merged)]
    for row in output_rows:
        _validate_translation_row(row, slot)
    if output is not None:
        _atomic_write(output, output_rows)
    return output_rows


def check_translation_batch(
    tasks: Iterable[Mapping[str, Any]],
    translation_a: Iterable[Mapping[str, Any]],
    translation_b: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    task_map = _indexed(tasks, "task")
    reports = []
    issues = []
    for slot, rows in (("A", translation_a), ("B", translation_b)):
        try:
            indexed = _indexed(rows, f"translation {slot}")
        except PacketError as exc:
            issues.append(str(exc))
            indexed = {}
        reports.append(indexed)
        for row in indexed.values():
            try:
                _validate_translation_row(row, slot)
            except PacketError as exc:
                issues.append(str(exc))
    a_map, b_map = reports
    if set(a_map) != set(task_map):
        issues.append(
            f"translation A case-ID mismatch: missing={sorted(set(task_map) - set(a_map))} extra={sorted(set(a_map) - set(task_map))}"
        )
    if set(b_map) != set(task_map):
        issues.append(
            f"translation B case-ID mismatch: missing={sorted(set(task_map) - set(b_map))} extra={sorted(set(b_map) - set(task_map))}"
        )
    translator_ids = {
        row.get("translator_id")
        for row in [*a_map.values(), *b_map.values()]
        if row.get("translator_id")
    }
    if len(a_map) == len(task_map) and len(b_map) == len(task_map):
        a_ids = {row.get("translator_id") for row in a_map.values()}
        b_ids = {row.get("translator_id") for row in b_map.values()}
        if a_ids & b_ids:
            issues.append("translator A and B must use distinct stable translator IDs")
    for case_id in sorted(set(a_map) & set(b_map)):
        for field in (
            "source_record_id",
            "source_oracle_hash",
            "target_language",
            "target_locale",
        ):
            if a_map[case_id].get(field) != b_map[case_id].get(field):
                issues.append(f"{case_id}: translation A/B {field} mismatch")
    a_inputs = {
        row["translation"].get("target_input")
        for row in a_map.values()
        if isinstance(row.get("translation"), dict)
        and row["translation"].get("decision") == "propose"
    }
    b_inputs = {
        row["translation"].get("target_input")
        for row in b_map.values()
        if isinstance(row.get("translation"), dict)
        and row["translation"].get("decision") == "propose"
    }
    return {
        "translation_schema_version": TRANSLATION_SCHEMA_VERSION,
        "ready": not issues,
        "case_count": len(task_map),
        "translation_a_rows": len(a_map),
        "translation_b_rows": len(b_map),
        "translator_ids": sorted(str(value) for value in translator_ids),
        "target_input_agreement_count": len(a_inputs & b_inputs),
        "target_input_disagreement_count": len(a_inputs ^ b_inputs),
        "issues": sorted(set(issues)),
    }


def translation_adjudication_packet_rows(
    tasks: Iterable[Mapping[str, Any]],
    translation_a: Iterable[Mapping[str, Any]],
    translation_b: Iterable[Mapping[str, Any]],
    completed_decisions: Iterable[Mapping[str, Any]] = (),
    *,
    max_cases: int,
    max_bytes: int,
) -> list[dict[str, Any]]:
    report = check_translation_batch(tasks, translation_a, translation_b)
    if not report["ready"]:
        raise PacketError("translation-check failed: " + "; ".join(report["issues"]))
    a_map = _indexed(translation_a, "translation A")
    b_map = _indexed(translation_b, "translation B")
    projected = [
        {
            "translation_case_id": task["translation_case_id"],
            "task": _public(task),
            "translation_a": a_map[task["translation_case_id"]],
            "translation_b": b_map[task["translation_case_id"]],
        }
        for task in sorted(tasks, key=lambda row: row["translation_case_id"])
    ]
    return select_packet_rows(
        projected,
        (row.get("translation_case_id") for row in completed_decisions),
        max_cases=max_cases,
        max_bytes=max_bytes,
        identity_field="translation_case_id",
    )


def _validate_adjudication(row: Mapping[str, Any]) -> None:
    case_id = row.get("translation_case_id")
    if not isinstance(case_id, str) or not case_id:
        raise PacketError("translation adjudication row is missing translation_case_id")
    if (
        not isinstance(row.get("adjudicator_id"), str)
        or not row["adjudicator_id"].strip()
    ):
        raise PacketError(f"{case_id}: missing adjudicator_id")
    decision = row.get("decision")
    if decision not in ADJUDICATION_DECISIONS:
        raise PacketError(f"{case_id}: invalid translation adjudication decision")
    if (
        decision in {"accept_a", "accept_b"}
        and row.get("selection") != decision[-1].upper()
    ):
        raise PacketError(f"{case_id}: selection must match decision")
    if decision == "merge" and not isinstance(row.get("final_translation"), dict):
        raise PacketError(f"{case_id}: merge requires complete final_translation")
    if decision in {"accept_a", "accept_b", "merge"}:
        final = row.get("final_translation")
        if (
            not isinstance(final, dict)
            or not isinstance(final.get("target_input"), str)
            or not final["target_input"].strip()
        ):
            raise PacketError(
                f"{case_id}: accepted translation requires non-empty target_input"
            )


def merge_translation_adjudication_rows(
    existing_rows: Iterable[Mapping[str, Any]],
    result_rows: Iterable[Mapping[str, Any]],
    *,
    output: str | Path | None = None,
) -> list[dict[str, Any]]:
    existing = _indexed(existing_rows, "existing translation adjudication")
    results = _indexed(result_rows, "translation adjudication result")
    merged = dict(existing)
    adjudicators = {row.get("adjudicator_id") for row in existing.values()}
    for case_id, row in results.items():
        _validate_adjudication(row)
        adjudicators.add(row.get("adjudicator_id"))
        if case_id in merged and merged[case_id] != row:
            raise PacketError(
                f"conflicting duplicate translation adjudication result: {case_id}"
            )
        merged[case_id] = dict(row)
    if len(adjudicators) > 1:
        raise PacketError(
            "translation adjudication must use one stable adjudicator identity"
        )
    output_rows = [merged[key] for key in sorted(merged)]
    for row in output_rows:
        _validate_adjudication(row)
    if output is not None:
        _atomic_write(output, output_rows)
    return output_rows


def _candidate_from_translation(
    task: Mapping[str, Any], final: Mapping[str, Any]
) -> dict[str, Any]:
    validate_target_locale(final.get("target_language"), final.get("target_locale"))
    target_input = final.get("target_input")
    if not isinstance(target_input, str) or not target_input.strip():
        raise PacketError(f"{task['translation_case_id']}: final target_input is empty")
    relation = final.get("transfer_relation")
    if relation not in {"equivalent", "adapted"}:
        raise PacketError(f"{task['translation_case_id']}: invalid transfer relation")
    source = task["source_license"]
    return {
        "language": final["target_language"],
        "locale": final["target_locale"],
        "input": target_input,
        "family_suggestion": task.get("parent_family_id"),
        "source": {
            "benchmark": "spokenform_translation",
            "source_id": task["translation_case_id"],
            "source_version": TRANSLATION_PROTOCOL_VERSION,
            "source_url": f"spokenform-gold://translation/{task['translation_case_id']}",
            "license": source.get("license", "CC-BY-4.0"),
            "license_id": source.get("license_id", "CC-BY-4.0"),
            "source_hash": _sha256(
                json.dumps(final, ensure_ascii=False, sort_keys=True)
            ),
            "upstream_expected": None,
            "translation_parent_record_id": task["source_record_id"],
            "translation_parent_oracle_hash": task["source_oracle_hash"],
            "translation_target_locale": final["target_locale"],
            "translation_relation": relation,
            "materialization": "embedded",
        },
    }


def finalize_translations(
    tasks: Iterable[Mapping[str, Any]],
    translation_a: Iterable[Mapping[str, Any]],
    translation_b: Iterable[Mapping[str, Any]],
    decisions: Iterable[Mapping[str, Any]],
    *,
    output: str | Path | None = None,
) -> list[dict[str, Any]]:
    task_map = _indexed(tasks, "task")
    a_map = _indexed(translation_a, "translation A")
    b_map = _indexed(translation_b, "translation B")
    decision_map = _indexed(decisions, "translation adjudication")
    if set(decision_map) != set(task_map):
        raise PacketError(
            f"translation adjudication case-ID set mismatch: missing={sorted(set(task_map) - set(decision_map))} extra={sorted(set(decision_map) - set(task_map))}"
        )
    candidates = []
    for case_id in sorted(task_map):
        task = task_map[case_id]
        decision = decision_map[case_id]
        _validate_adjudication(decision)
        _adaptation_source(
            {
                "id": task["source_record_id"],
                "source_observations": [task["source_license"]],
            }
        )
        if decision["decision"] == "accept_a":
            selected = a_map.get(case_id)
            if selected is None:
                raise PacketError(f"{case_id}: missing translator A row")
            final = dict(selected["translation"])
            final.setdefault("target_language", task["target_language"])
            final.setdefault("target_locale", task["target_locale"])
        elif decision["decision"] == "accept_b":
            selected = b_map.get(case_id)
            if selected is None:
                raise PacketError(f"{case_id}: missing translator B row")
            final = dict(selected["translation"])
            final.setdefault("target_language", task["target_language"])
            final.setdefault("target_locale", task["target_locale"])
        elif decision["decision"] == "merge":
            final = decision["final_translation"]
        else:
            continue
        candidates.append(_candidate_from_translation(task, final))
    if output is not None:
        _atomic_write(output, candidates)
    return candidates


__all__ = [
    "ADJUDICATION_DECISIONS",
    "ALLOWED_DECISIONS",
    "TARGET_LOCALES",
    "TRANSLATION_PROTOCOL_VERSION",
    "TRANSLATION_SCHEMA_VERSION",
    "TranslationError",
    "TranslationLicenseError",
    "build_translation_tasks",
    "check_translation_batch",
    "finalize_translations",
    "merge_translation_adjudication_rows",
    "merge_translation_rows",
    "prepare_translation_batch",
    "translation_adjudication_packet_rows",
    "translation_blind_row",
    "translation_case_id",
    "translation_packet_rows",
    "validate_target_locale",
]
