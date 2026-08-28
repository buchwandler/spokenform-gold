from __future__ import annotations

import hashlib
import json
import shutil
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
        handle.writelines(
            json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
            for record in output
        )
    return len(output)


_LEGACY_MOVES = {
    "cases.jsonl": "cases/cases.jsonl",
    "context.jsonl": "cases/context.jsonl",
    "a.blind.jsonl": "reviews/a/blind.jsonl",
    "b.blind.jsonl": "reviews/b/blind.jsonl",
    "a.complete.jsonl": "reviews/a/complete.jsonl",
    "b.complete.jsonl": "reviews/b/complete.jsonl",
    "review-check.json": "reviews/check.json",
    "adjudicated.jsonl": "adjudication/decisions.jsonl",
    "adjudicated.partial.jsonl": "adjudication/decisions.partial.jsonl",
    "integration.json": "integration/summary.json",
}


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def classify_work_root(root: str | Path) -> dict:
    """Classify known legacy batch artifacts without reading JSONL payloads."""
    work = Path(root)
    batches = []
    batch_root = work / "batches"
    if batch_root.is_dir():
        for path in sorted(item for item in batch_root.iterdir() if item.is_dir()):
            metadata = path / "batch.json"
            payload = (
                json.loads(metadata.read_text(encoding="utf-8"))
                if metadata.is_file()
                else {}
            )
            batches.append(
                {
                    "batch_id": payload.get("batch_id", path.name),
                    "state": payload.get("state", "unknown"),
                    "cases": payload.get("case_count"),
                    "root": str(path),
                }
            )
    corrections = []
    correction_root = work / "corrections"
    if correction_root.is_dir():
        for record_root in sorted(
            item for item in correction_root.iterdir() if item.is_dir()
        ):
            revisions = sorted(
                item.name for item in record_root.iterdir() if item.is_dir()
            )
            corrections.append({"record_id": record_root.name, "revisions": revisions})
    legacy = [
        {"path": str(work / name), "classification": "legacy"}
        for name in ("candidates", "exclusions", "reports", "review_batches")
        if (work / name).exists()
    ]
    known = {
        "batches",
        "corrections",
        "archive",
        "state",
        *(item["path"].split("/")[-1] for item in legacy),
    }
    loose = (
        sorted(
            str(path.relative_to(work))
            for path in work.iterdir()
            if path.name not in known
        )
        if work.is_dir()
        else []
    )
    return {
        "batches": batches,
        "corrections": corrections,
        "legacy": legacy,
        "loose_artifacts": loose,
    }


def work_migration_plan(root: str | Path) -> list[dict]:
    work = Path(root)
    actions = []
    if not work.is_dir():
        return actions
    for batch in (
        sorted((work / "batches").iterdir()) if (work / "batches").is_dir() else []
    ):
        if not batch.is_dir():
            continue
        for old, new in sorted(_LEGACY_MOVES.items()):
            source = batch / old
            target = batch / new
            if not source.is_file():
                continue
            if target.exists():
                actions.append(
                    {
                        "source": str(source),
                        "target": str(target),
                        "action": "conflict"
                        if _file_hash(source) != _file_hash(target)
                        else "already_present",
                        "source_hash": _file_hash(source),
                        "target_hash": _file_hash(target),
                    }
                )
            else:
                actions.append(
                    {
                        "source": str(source),
                        "target": str(target),
                        "action": "move",
                        "source_hash": _file_hash(source),
                    }
                )
    return actions


def migrate_work_root(root: str | Path, *, apply: bool = False) -> list[dict]:
    actions = work_migration_plan(root)
    if not apply:
        return actions
    conflicts = [action for action in actions if action["action"] == "conflict"]
    if conflicts:
        raise ValueError(
            f"migration would overwrite distinct artifact: {conflicts[0]['target']}"
        )
    for action in actions:
        if action["action"] == "conflict":
            raise ValueError(
                f"migration would overwrite distinct artifact: {action['target']}"
            )
        if action["action"] == "move":
            target = Path(action["target"])
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(action["source"], action["target"])
            action["action"] = "moved"
    return actions
