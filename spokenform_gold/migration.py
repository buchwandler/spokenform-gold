from __future__ import annotations

import json
from collections.abc import Iterable
from copy import deepcopy
from pathlib import Path

from .oracle import _legacy_unit_variants, oracle_hash


def _date_output(language: str, day: int, month: int, year: int) -> str:
    months = {
        1: "January",
        2: "February",
        3: "March",
        4: "April",
        5: "May",
        6: "June",
        7: "July",
        8: "August",
        9: "September",
        10: "October",
        11: "November",
        12: "December",
    }
    if language == "de":
        return f"Tag {day}, Monat {month}, Jahr {year}"
    if language == "es":
        return f"día {day}, mes {month}, año {year}"
    return f"{months.get(month, f'month {month}')} {day}, {year}"


def _legacy_ambiguity_interpretations(record: dict) -> list[dict]:
    unit = (record.get("units") or [{}])[0]
    candidates = unit.get("semantic", {}).get("candidates", [])
    interpretations = []
    for index, candidate in enumerate(candidates, 1):
        day, month, year = (
            candidate.get("day"),
            candidate.get("month"),
            candidate.get("year"),
        )
        output = _date_output(record.get("language", "en"), day, month, year)
        interpretations.append(
            {
                "label": f"interpretation_{index}",
                "semantic": deepcopy(candidate),
                "accepted_outputs": [output],
            }
        )
    return interpretations


def migrate_record(record: dict) -> dict:
    migrated = deepcopy(record)
    status = migrated.get("status")
    if isinstance(migrated.get("oracle"), dict):
        migrated["oracle_hash"] = oracle_hash(migrated)
        return migrated
    if status == "no_change":
        accepted = [migrated.get("input")]
        oracle = {
            "canonical_output": migrated.get("input"),
            "accepted_outputs": accepted,
            "rejected_outputs": [],
            "variant_mode": "explicit",
            "comparison_profile": "sentence-exact-v1",
        }
    elif status == "ambiguous":
        oracle = {
            "canonical_output": None,
            "accepted_outputs": [],
            "rejected_outputs": [],
            "variant_mode": "explicit",
            "comparison_profile": "sentence-exact-v1",
            "interpretations": _legacy_ambiguity_interpretations(migrated),
        }
    elif isinstance(migrated.get("expected_output"), str):
        explicit = sorted(_legacy_unit_variants(migrated))
        oracle = {
            "canonical_output": migrated["expected_output"],
            "accepted_outputs": explicit,
            "rejected_outputs": [],
            "variant_mode": "explicit",
            "comparison_profile": "sentence-exact-v1",
        }
    else:
        return migrated
    migrated["oracle"] = oracle
    migrated["review"] = {
        "protocol_version": "1.0.0",
        "status": "legacy_review",
        "reviewers": [],
        "adjudicator": None,
        "decision": "migration_only",
    }
    migrated["oracle_hash"] = oracle_hash(migrated)
    return migrated


def migrate_records(records: Iterable[dict]) -> list[dict]:
    return [migrate_record(record) for record in records]


def migrate_jsonl(input_path: str | Path, output_path: str | Path) -> int:
    output = []
    with Path(input_path).open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                output.append(migrate_record(json.loads(line)))
    with Path(output_path).open("w", encoding="utf-8") as handle:
        handle.writelines(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in output)
    return len(output)
