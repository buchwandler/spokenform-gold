from __future__ import annotations

import hashlib
import json
import os
import shutil
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


def exact_surface_hash(input_text: str) -> str:
    """Hash the exact input surface without compatibility normalization."""
    if not isinstance(input_text, str):
        raise TypeError("input_text must be a string")
    return "sha256:" + hashlib.sha256(input_text.encode("utf-8")).hexdigest()


def _nfkc_surface_key(input_text: str) -> str:
    """Normalize compatibility characters while preserving whitespace."""
    return unicodedata.normalize(
        "NFKC", input_text.replace("\r\n", "\n").replace("\r", "\n")
    )


def find_identity_collisions(records: Iterable[dict]) -> list[dict]:
    """Find distinct compatibility surfaces that share a legacy sentence key."""
    groups: dict[tuple[str, str, str], dict[str, list[dict]]] = {}
    for record in records:
        if not isinstance(record, dict) or not isinstance(record.get("input"), str):
            continue
        key = sentence_key(
            record.get("language", ""), record.get("locale", ""), record["input"]
        )
        surface_key = _nfkc_surface_key(record["input"])
        groups.setdefault(key, {}).setdefault(surface_key, []).append(record)

    collisions = []
    for key, surfaces in sorted(groups.items()):
        exact_inputs = {
            record["input"] for members in surfaces.values() for record in members
        }
        if len(exact_inputs) < 2 or len(surfaces) != 1:
            continue
        rows = [record for members in surfaces.values() for record in members]
        collisions.append(
            {
                "language": key[0],
                "locale": key[1],
                "legacy_normalized_input": key[2],
                "exact_inputs": sorted(exact_inputs),
                "exact_surface_hashes": sorted(
                    {exact_surface_hash(record["input"]) for record in rows}
                ),
                "record_ids": sorted(
                    record["id"] for record in rows if record.get("id")
                ),
            }
        )
    return collisions


class IdentityCollisionError(ValueError):
    """Raised when compatibility-distinct inputs would share one legacy case."""

    def __init__(self, collisions: list[dict]):
        self.collisions = collisions
        super().__init__(
            f"identity collision detected for {len(collisions)} sentence case(s)"
        )


# Descriptive aliases for callers that use the normalization-specific name.
find_nfkc_collisions = find_identity_collisions
detect_identity_collisions = find_identity_collisions


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


def canonical_corpus_path(repo_root: str | Path = Path(".")) -> Path:
    """Return the repository's canonical authoring corpus directory."""
    return Path(repo_root) / "data" / "corpus"


def _language_filename(language: object) -> str:
    if not isinstance(language, str) or not language.isascii():
        raise ValueError(f"invalid language identifier: {language!r}")
    normalized = language.strip().lower()
    if (
        normalized != language
        or not normalized.isalpha()
        or len(normalized) not in {2, 3}
    ):
        raise ValueError(f"invalid language identifier: {language!r}")
    return normalized


def shard_records_by_language(records: Iterable[dict]) -> dict[str, list[dict]]:
    """Group records by their validated ISO 639 language identifier."""
    shards: dict[str, list[dict]] = {}
    for record in records:
        language = _language_filename(record.get("language"))
        shards.setdefault(language, []).append(deepcopy(record))
    for language, shard in shards.items():
        shard.sort(key=lambda row: row.get("id", ""))
    return dict(sorted(shards.items()))


def _corpus_jsonl_files(root: Path) -> list[Path]:
    return sorted(
        path for path in root.iterdir() if path.is_file() and path.suffix == ".jsonl"
    )


def validate_corpus_layout(root: str | Path) -> list[str]:
    """Validate shard filenames and global layout invariants."""
    corpus_root = Path(root)
    if not corpus_root.exists():
        return [f"corpus directory does not exist: {corpus_root}"]
    if not corpus_root.is_dir():
        return [f"corpus path must be a directory: {corpus_root}"]
    errors: list[str] = []
    files = _corpus_jsonl_files(corpus_root)
    for path in sorted(corpus_root.iterdir()):
        if path.is_file() and path.suffix != ".jsonl":
            errors.append(f"corpus directory contains non-JSONL file: {path.name}")
        elif path.is_dir():
            errors.append(f"corpus directory contains nested path: {path.name}")
    for path in files:
        try:
            language = _language_filename(path.stem)
        except ValueError as exc:
            errors.append(f"invalid corpus shard filename {path.name}: {exc}")
            continue
        try:
            records = read_records([path])
        except (OSError, TypeError, ValueError) as exc:
            errors.append(str(exc))
            continue
        for record in records:
            if record.get("language") != language:
                errors.append(
                    f"{path}: record {record.get('id', '?')} language "
                    f"{record.get('language')!r} does not match shard {language!r}"
                )
    try:
        records = read_records(files)
    except (OSError, TypeError, ValueError):
        return sorted(set(errors))
    ids: dict[str, Path] = {}
    identities: dict[tuple[str, str, str], str] = {}
    for record in records:
        record_id = record.get("id")
        if isinstance(record_id, str) and record_id:
            previous = ids.get(record_id)
            if previous is not None:
                errors.append(
                    f"duplicate id: {record_id} ({previous} and corpus shard)"
                )
            else:
                ids[record_id] = Path(record.get("_source_file", "?"))
        if isinstance(record.get("input"), str):
            identity = sentence_key(
                record.get("language", ""),
                record.get("locale", ""),
                record["input"],
            )
            previous_id = identities.get(identity)
            if previous_id is not None and previous_id != record.get("id"):
                errors.append(
                    f"duplicate sentence identity: {identity!r} "
                    f"({previous_id} and {record.get('id', '?')})"
                )
            else:
                identities[identity] = record.get("id", "")
    return sorted(set(errors))


def read_corpus(root: str | Path) -> list[dict]:
    """Read and layout-check the complete canonical corpus directory."""
    corpus_root = Path(root)
    if corpus_root.is_file():
        return read_records([corpus_root])
    errors = validate_corpus_layout(corpus_root)
    if errors:
        raise ValueError("invalid corpus layout: " + "; ".join(errors))
    return read_records(_corpus_jsonl_files(corpus_root))


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def write_corpus_atomic(root: str | Path, records: Iterable[dict]) -> None:
    """Replace the complete canonical corpus with deterministic language shards."""
    corpus_root = Path(root)
    if corpus_root.exists() and not corpus_root.is_dir():
        raise ValueError(f"corpus path must be a directory: {corpus_root}")
    corpus_root.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{corpus_root.name}.next-", dir=corpus_root.parent)
    )
    backup: Path | None = None
    try:
        shards = shard_records_by_language(records)
        for language, shard in shards.items():
            write_records_atomic(staging / f"{language}.jsonl", shard)
        layout_errors = validate_corpus_layout(staging)
        if layout_errors:
            raise ValueError(
                "invalid staged corpus layout: " + "; ".join(layout_errors)
            )
        _fsync_directory(staging)
        if corpus_root.exists():
            backup = Path(
                tempfile.mkdtemp(
                    prefix=f".{corpus_root.name}.previous-", dir=corpus_root.parent
                )
            )
            backup.rmdir()
            os.replace(corpus_root, backup)
        try:
            os.replace(staging, corpus_root)
        except BaseException:
            if backup is not None and not corpus_root.exists():
                os.replace(backup, corpus_root)
            raise
        _fsync_directory(corpus_root.parent)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
        if backup is not None and backup.exists():
            shutil.rmtree(backup)


def replace_corpus_record_atomic(
    root: str | Path, record_id: str, replacement: dict
) -> list[dict]:
    """Replace one permanent ID after validating the complete proposed corpus."""
    records = read_corpus(root)
    matches = [row for row in records if row.get("id") == record_id]
    if len(matches) != 1:
        raise ValueError(
            f"expected one canonical record for {record_id}, found {len(matches)}"
        )
    updated = [
        deepcopy(replacement) if row.get("id") == record_id else row for row in records
    ]
    from .validation import validate_records

    errors = validate_records(updated)
    if errors:
        raise ValueError("updated corpus is invalid: " + "; ".join(errors))
    write_corpus_atomic(root, updated)
    return updated


def shard_corpus(input_path: str | Path, output_root: str | Path) -> int:
    """Migrate one legacy corpus JSONL file into language shards."""
    source = Path(input_path)
    destination = Path(output_root)
    if not source.is_file():
        raise ValueError(f"legacy corpus file not found: {source}")
    if destination.exists():
        raise ValueError(f"corpus output already exists: {destination}")
    original = read_records([source])
    from .validation import validate_records

    validation_errors = validate_records(original)
    if validation_errors:
        raise ValueError(
            "legacy corpus validation failed: " + "; ".join(validation_errors)
        )
    original_by_id = {row.get("id"): row for row in original}
    original_hashes = {row.get("id"): row.get("oracle_hash") for row in original}
    original_semantic = {
        row.get("id"): json.dumps(
            {key: value for key, value in row.items() if not key.startswith("_")},
            ensure_ascii=False,
            sort_keys=True,
        )
        for row in original
    }
    try:
        write_corpus_atomic(destination, original)
        migrated = read_corpus(destination)
        migrated_by_id = {row.get("id"): row for row in migrated}
        migrated_hashes = {row.get("id"): row.get("oracle_hash") for row in migrated}
        migrated_semantic = {
            row.get("id"): json.dumps(
                {key: value for key, value in row.items() if not key.startswith("_")},
                ensure_ascii=False,
                sort_keys=True,
            )
            for row in migrated
        }
        if len(original) != len(migrated):
            raise ValueError("shard migration changed record count")
        if set(original_by_id) != set(migrated_by_id):
            raise ValueError("shard migration changed record ids")
        if original_hashes != migrated_hashes:
            raise ValueError("shard migration changed oracle hashes")
        if original_semantic != migrated_semantic:
            raise ValueError("shard migration changed semantic records")
    except BaseException:
        if destination.exists():
            shutil.rmtree(destination)
        raise
    source.unlink()
    return len(migrated)


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
