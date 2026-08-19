from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from .io import expand_jsonl_paths, read_records, write_jsonl


def candidate_sort_key(record: dict) -> tuple[str, str, str, str, str]:
    source = record.get("source") or {}
    return (
        str(source.get("benchmark", "")),
        str(record.get("language", "")),
        str(record.get("locale", "")),
        str(source.get("source_id", "")),
        str(record.get("id", "")),
    )


def merge_candidates(records: Iterable[dict]) -> list[dict]:
    ordered = sorted(records, key=candidate_sort_key)
    seen: dict[str, int] = {}
    for record in ordered:
        record_id = record.get("id")
        if not isinstance(record_id, str) or not record_id:
            raise ValueError("candidate records require a non-empty id")
        seen[record_id] = seen.get(record_id, 0) + 1
    duplicates = sorted(record_id for record_id, count in seen.items() if count > 1)
    if duplicates:
        raise ValueError(f"duplicate candidate IDs: {duplicates}")
    return ordered


def merge_candidate_files(paths: Iterable[str | Path], out: str | Path) -> list[dict]:
    files = expand_jsonl_paths(paths)
    if not files:
        raise ValueError("no JSONL candidate files matched")
    merged = merge_candidates(read_records(files))
    write_jsonl(out, merged)
    return merged
