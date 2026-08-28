from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Iterator
from dataclasses import asdict, dataclass
from pathlib import Path

from .corpus import (
    IdentityCollisionError,
    corpus_identity_map,
    corpus_source_keys,
    find_identity_collisions,
    sentence_key,
    source_key,
    stable_case_id,
)
from .io import read_json, read_records, write_json, write_jsonl


@dataclass(frozen=True)
class CollectionAccounting:
    input_observations: int
    invalid_observations: int
    excluded_observations: int
    already_reviewed_observations: int
    duplicate_observations: int
    candidate_observations: int
    available_cases: int
    selected_cases: int
    selected_source_observations: int

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


@dataclass
class CollectionResult:
    cases: list[dict]
    available_cases: list[dict]
    accounting: CollectionAccounting

    def __iter__(self) -> Iterator[list[dict]]:
        """Retain tuple unpacking for callers using the pre-accounting API."""
        yield self.cases
        yield self.available_cases


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
        "translation_parent_record_id": source.get("translation_parent_record_id"),
        "translation_parent_oracle_hash": source.get("translation_parent_oracle_hash"),
        "translation_target_locale": source.get("translation_target_locale"),
        "translation_relation": source.get("translation_relation"),
    }


def cluster_observations(records: Iterable[dict]) -> list[dict]:
    records = list(records)
    collisions = find_identity_collisions(records)
    if collisions:
        raise IdentityCollisionError(collisions)
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
                "family_id": first.get("family_id") or first.get("family_suggestion"),
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


DEFAULT_V2_COLLECTION_LIMIT = 1000


def _valid_observation(record: object) -> bool:
    return isinstance(record, dict) and isinstance(record.get("input"), str)


def select_cases(
    observations: Iterable[dict],
    reviewed: Iterable[dict] = (),
    exclusions: Iterable[str | Path] = (),
    limit: int = DEFAULT_V2_COLLECTION_LIMIT,
) -> CollectionResult:
    if limit < 0:
        raise ValueError("limit must not be negative")
    observation_rows = list(observations)
    reviewed_records = list(reviewed)
    reviewed_sources = corpus_source_keys(reviewed_records)
    reviewed_identities = corpus_identity_map(reviewed_records)
    excluded = _exclusion_keys(exclusions)
    invalid = [record for record in observation_rows if not _valid_observation(record)]
    valid = [record for record in observation_rows if _valid_observation(record)]

    unique: dict[str, dict] = {}
    duplicate_count = 0
    excluded_count = 0
    already_reviewed_count = 0
    candidate_rows: list[dict] = []
    for record in valid:
        observation = _observation(record)
        key = source_key(observation)
        if key in unique:
            duplicate_count += 1
            continue
        unique[key] = record
        if key in excluded:
            excluded_count += 1
            continue
        identity = sentence_key(
            record.get("language", ""), record.get("locale", ""), record["input"]
        )
        if key in reviewed_sources and identity in reviewed_identities:
            already_reviewed_count += 1
            continue
        candidate_rows.append(record)

    cases = cluster_observations(candidate_rows)
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
                already_reviewed_count += len(case["source_observations"])
                continue
            case["existing_record_id"] = existing.get("id")
            case["conflicts_with_existing"] = any(
                isinstance(item.get("upstream_expected"), str)
                and item.get("upstream_expected")
                != (existing.get("oracle") or {}).get("canonical_output")
                for item in case["source_observations"]
            )
        unseen.append(case)

    selected = unseen[:limit]
    accounting = CollectionAccounting(
        input_observations=len(observation_rows),
        invalid_observations=len(invalid),
        excluded_observations=excluded_count,
        already_reviewed_observations=already_reviewed_count,
        duplicate_observations=duplicate_count,
        candidate_observations=len(candidate_rows),
        available_cases=len(unseen),
        selected_cases=len(selected),
        selected_source_observations=sum(
            len(case.get("source_observations", [])) for case in selected
        ),
    )
    return CollectionResult(selected, unseen, accounting)


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
    accounting: CollectionAccounting | dict[str, int] | None = None,
) -> dict:
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    write_jsonl(root / "cases.jsonl", cases)
    write_jsonl(root / "context.jsonl", cases)
    write_jsonl(root / "a.blind.jsonl", [blind_case(case, "A") for case in cases])
    write_jsonl(root / "b.blind.jsonl", [blind_case(case, "B") for case in cases])
    counts = (
        accounting.to_dict()
        if isinstance(accounting, CollectionAccounting)
        else dict(accounting or {})
    )
    counts.setdefault("selected_cases", len(cases))
    counts.setdefault(
        "selected_source_observations",
        sum(len(case.get("source_observations", [])) for case in cases),
    )
    metadata = {
        "schema_version": "2.0.0",
        "batch_id": batch_id,
        "source_lock_hash": source_lock_hash,
        "case_count": len(cases),
        "source_observation_count": counts["selected_source_observations"],
        "state": "empty" if not cases else "awaiting_review",
        "empty_reason": "no_unreviewed_cases" if not cases else None,
        "accounting": counts,
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
    limit: int = DEFAULT_V2_COLLECTION_LIMIT,
    source_lock_hash: str | None = None,
) -> dict:
    observations = read_records(observation_paths)
    reviewed = read_records(reviewed_paths)
    result = select_cases(observations, reviewed, exclusion_paths, limit)
    metadata = build_batch(
        result.cases,
        output_root,
        batch_id=batch_id,
        source_lock_hash=source_lock_hash,
        accounting=result.accounting,
    )
    metadata["available_case_count"] = result.accounting.available_cases
    metadata["input_observation_count"] = result.accounting.input_observations
    write_json(Path(output_root) / "batch.json", metadata)
    return metadata
