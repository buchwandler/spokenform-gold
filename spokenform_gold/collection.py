from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path

from .corpus import (
    corpus_identity_map,
    corpus_source_keys,
    sentence_key,
    source_key,
    stable_case_id,
)
from .io import read_json, read_records, write_json, write_jsonl


def _observation(record: dict) -> dict:
    source = record.get("source") or record.get("source_observation") or {}
    return {
        "benchmark": source.get("benchmark"),
        "source_id": source.get("source_id"),
        "source_version": source.get("source_version"),
        "source_category": source.get("source_category"),
        "source_url": source.get("source_url"),
        "license": source.get("license"),
        "license_id": source.get("license_id"),
        "license_scope": source.get("license_scope"),
        "source_hash": source.get("source_hash"),
        "expected_hash": source.get("expected_hash"),
        "upstream_expected": source.get("upstream_expected"),
        "materialization": record.get(
            "materialization", source.get("materialization", "embedded")
        ),
        "source_artifact": source.get("source_artifact"),
    }


def cluster_observations(records: Iterable[dict]) -> list[dict]:
    groups: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for record in records:
        if not isinstance(record, dict):
            continue
        if not isinstance(record.get("input"), str):
            continue
        key = sentence_key(
            record.get("language", ""), record.get("locale", ""), record["input"]
        )
        groups[key].append(record)
    cases: list[dict] = []
    for key, members in sorted(groups.items()):
        first = min(
            members,
            key=lambda row: (
                str((row.get("source") or {}).get("benchmark", "")),
                str((row.get("source") or {}).get("source_id", "")),
                str(row.get("id", "")),
            ),
        )
        # Dicts are not hashable, so deduplicate with source keys.
        by_source: dict[str, dict] = {}
        for member in members:
            item = _observation(member)
            by_source[source_key(item)] = item
        cases.append(
            {
                "schema_version": "2.0.0",
                "case_id": stable_case_id(*key),
                "language": key[0],
                "locale": key[1],
                "input": first["input"],
                "source_observations": [by_source[k] for k in sorted(by_source)],
            }
        )
    return cases


def _exclusion_keys(paths: Iterable[str | Path]) -> set[str]:
    keys: set[str] = set()
    for path in paths:
        payload = read_json(path)
        entries = (
            payload if isinstance(payload, list) else payload.get("exclusions", [])
        )
        for item in entries:
            if isinstance(item, dict):
                key = item.get("source_key") or item.get("source_id")
                if key:
                    keys.add(str(key))
    return keys


def select_cases(
    observations: Iterable[dict],
    reviewed: Iterable[dict] = (),
    exclusions: Iterable[str | Path] = (),
    limit: int = 100,
) -> tuple[list[dict], list[dict]]:
    reviewed_records = list(reviewed)
    reviewed_sources = corpus_source_keys(reviewed_records)
    reviewed_identities = corpus_identity_map(reviewed_records)
    excluded = _exclusion_keys(exclusions)
    candidates = [
        record
        for record in observations
        if source_key(_observation(record)) not in reviewed_sources
        or sentence_key(
            record.get("language", ""),
            record.get("locale", ""),
            record.get("input", ""),
        )
        not in reviewed_identities
    ]
    candidates = [
        record
        for record in candidates
        if source_key(_observation(record)) not in excluded
    ]
    cases = cluster_observations(candidates)
    unseen: list[dict] = []
    for case in cases:
        key = sentence_key(case["language"], case["locale"], case["input"])
        existing = reviewed_identities.get(key)
        if existing is not None:
            known = {
                source_key(item)
                for item in existing.get("source_observations", [])
                if isinstance(item, dict)
            }
            if all(source_key(item) in known for item in case["source_observations"]):
                continue
            case["existing_record_id"] = existing.get("id")
            case["conflicts_with_existing"] = any(
                isinstance(item.get("upstream_expected"), str)
                and item.get("upstream_expected")
                != (existing.get("oracle") or {}).get("canonical_output")
                for item in case["source_observations"]
            )
        unseen.append(case)
    return unseen[:limit], unseen


def blind_case(case: dict, slot: str) -> dict:
    if slot not in {"A", "B"}:
        raise ValueError("reviewer slot must be A or B")
    return {
        "review_schema_version": "2.0.0",
        "case_id": case["case_id"],
        "reviewer_slot": slot,
        "language": case["language"],
        "locale": case["locale"],
        "input": case["input"],
        "family_id": case.get("family_id"),
        "annotation": None,
        "review": {"status": "unreviewed"},
    }


def build_batch(
    cases: list[dict],
    output_root: str | Path,
    *,
    batch_id: str,
    source_lock_hash: str | None = None,
) -> dict:
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    write_jsonl(root / "cases.jsonl", cases)
    write_jsonl(root / "context.jsonl", cases)
    write_jsonl(root / "a.blind.jsonl", [blind_case(case, "A") for case in cases])
    write_jsonl(root / "b.blind.jsonl", [blind_case(case, "B") for case in cases])
    metadata = {
        "schema_version": "2.0.0",
        "batch_id": batch_id,
        "source_lock_hash": source_lock_hash,
        "case_count": len(cases),
        "source_observation_count": sum(
            len(case.get("source_observations", [])) for case in cases
        ),
        "state": "awaiting_review",
        "reviewer_a": None,
        "reviewer_b": None,
        "adjudicator": None,
    }
    write_json(root / "batch.json", metadata)
    return metadata


def collect_batch(
    observation_paths: Iterable[str | Path],
    *,
    reviewed_paths: Iterable[str | Path] = (),
    exclusion_paths: Iterable[str | Path] = (),
    output_root: str | Path,
    batch_id: str,
    limit: int = 100,
    source_lock_hash: str | None = None,
) -> dict:
    observations = read_records(observation_paths)
    reviewed = read_records(reviewed_paths)
    cases, all_candidates = select_cases(observations, reviewed, exclusion_paths, limit)
    result = build_batch(
        cases, output_root, batch_id=batch_id, source_lock_hash=source_lock_hash
    )
    result.update(
        {
            "available_case_count": len(all_candidates),
            "input_observation_count": len(observations),
        }
    )
    write_json(Path(output_root) / "batch.json", result)
    return result
