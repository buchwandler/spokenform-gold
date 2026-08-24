from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unicodedata
from collections.abc import Iterable
from copy import deepcopy
from pathlib import Path

from .io import read_records, write_jsonl
from .oracle import oracle_hash

CORPUS_SCHEMA_VERSION = "2.0.0"


def sentence_key(language: str, locale: str, input_text: str) -> tuple[str, str, str]:
    """Return the conservative identity of one sentence case."""
    normalized = " ".join(
        unicodedata.normalize("NFKC", input_text)
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .split()
    )
    return language or "", locale or "", normalized


def source_key(source: dict) -> str:
    benchmark = source.get("benchmark", "")
    version = source.get("source_version", "")
    source_id = source.get("source_id", "")
    return f"{benchmark}+{version}+{source_id}"


def stable_case_id(language: str, locale: str, input_text: str) -> str:
    digest = hashlib.sha256(
        "|".join(sentence_key(language, locale, input_text)).encode("utf-8")
    ).hexdigest()[:20]
    return f"case-{digest}"


def stable_record_id(case: dict) -> str:
    return (
        "sfg-"
        + hashlib.sha256(
            "|".join(
                sentence_key(
                    case.get("language", ""),
                    case.get("locale", ""),
                    case.get("input", ""),
                )
            ).encode("utf-8")
        ).hexdigest()[:20]
    )


def source_observation(source: dict) -> dict:
    """Copy only source provenance, retaining upstream assertions and hashes."""
    return deepcopy(
        {key: value for key, value in source.items() if not key.startswith("_")}
    )


def migrate_record(record: dict) -> dict:
    """Convert one legacy split record to the v2 sentence-centric shape."""
    migrated = {
        key: deepcopy(value) for key, value in record.items() if not key.startswith("_")
    }
    source = migrated.pop("source", None)
    migrated.pop("split", None)
    migrated.pop("expected_output", None)
    migrated["schema_version"] = CORPUS_SCHEMA_VERSION
    if isinstance(source, dict):
        migrated["source_observations"] = [source_observation(source)]
    elif "source_observations" not in migrated:
        migrated["source_observations"] = []
    if isinstance(migrated.get("oracle"), dict):
        migrated["expected_output"] = migrated["oracle"].get("canonical_output")
        # expected_output remains only as a transient compatibility alias in memory.
        migrated.pop("expected_output", None)
    migrated["oracle_hash"] = (
        oracle_hash(migrated) if migrated.get("oracle") else migrated.get("oracle_hash")
    )
    return migrated


def migrate_records(records: Iterable[dict]) -> list[dict]:
    result = [migrate_record(record) for record in records]
    return sorted(result, key=lambda row: row.get("id", ""))


def migrate_paths(paths: Iterable[str | Path], output: str | Path) -> int:
    records = migrate_records(read_records(paths))
    write_jsonl(output, records)
    return len(records)


def write_records_atomic(path: str | Path, records: Iterable[dict]) -> None:
    """Write canonical JSONL atomically, with stable record ordering."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(
        (deepcopy(row) for row in records), key=lambda row: row.get("id", "")
    )
    fd, temporary = tempfile.mkstemp(
        prefix=f".{target.name}.", dir=target.parent, text=True
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            for record in ordered:
                clean = {
                    key: value
                    for key, value in record.items()
                    if not key.startswith("_")
                }
                handle.write(
                    json.dumps(clean, ensure_ascii=False, sort_keys=True) + "\n"
                )
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def attach_source_observations(
    records: list[dict], observations: Iterable[dict]
) -> tuple[list[dict], list[dict]]:
    """Attach matching new observations; return records and conflicting cases."""
    by_key = {
        sentence_key(
            row.get("language", ""), row.get("locale", ""), row.get("input", "")
        ): row
        for row in records
    }
    conflicts: list[dict] = []
    for observation in observations:
        key = sentence_key(
            observation.get("language", ""),
            observation.get("locale", ""),
            observation.get("input", ""),
        )
        record = by_key.get(key)
        if record is None:
            continue
        sources = record.setdefault("source_observations", [])
        known = {source_key(source) for source in sources if isinstance(source, dict)}
        source = observation.get("source") or observation.get("source_observation")
        if not isinstance(source, dict) or source_key(source) in known:
            continue
        sources.append(source_observation(source))
        upstream = source.get("upstream_expected")
        canonical = (record.get("oracle") or {}).get("canonical_output")
        if (
            isinstance(upstream, str)
            and isinstance(canonical, str)
            and upstream != canonical
        ):
            conflicts.append(
                {
                    "record_id": record.get("id"),
                    "source_key": source_key(source),
                    "reason": "conflicting_upstream_expected",
                }
            )
    for record in records:
        record["source_observations"] = sorted(
            record.get("source_observations", []), key=source_key
        )
    return records, conflicts


def corpus_source_keys(records: Iterable[dict]) -> set[str]:
    return {
        source_key(source)
        for record in records
        for source in record.get("source_observations", [])
        if isinstance(source, dict)
    }


def corpus_identity_map(records: Iterable[dict]) -> dict[tuple[str, str, str], dict]:
    return {
        sentence_key(
            row.get("language", ""), row.get("locale", ""), row.get("input", "")
        ): row
        for row in records
    }
