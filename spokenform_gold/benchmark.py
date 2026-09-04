from __future__ import annotations

import importlib
import inspect
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .adapter import build_prediction_records
from .corpus import read_corpus
from .corpus_status import canonical_corpus_hash
from .evaluation_profiles import (
    load_registry,
    profile_hash,
    registry_hash,
    resolve_profile,
)
from .gold_audit import audit_records
from .io import read_json, read_records, sha256_file, write_json, write_jsonl
from .scoring import score_records
from .source_resolver import SourceTextLoader, resolve_release_record
from .validation import validate_corpus

PrepareCallable = Callable[[str, str, str, dict[str, Any] | None], str]

GOLD_PROFILE_V1 = resolve_profile("gold-v1")
BENCHMARK_PROFILES = {
    name: resolve_profile(name) for name in load_registry()["profiles"]
}


def benchmark_profile(
    name: str = GOLD_PROFILE_V1["name"],
    registry_path: str | Path | None = None,
) -> dict[str, Any]:
    return resolve_profile(name, registry_path)


def load_release_manifest(gold_root: str | Path) -> dict:
    root = Path(gold_root)
    manifest_path = root / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"missing release manifest: {manifest_path}")
    return read_json(manifest_path)


def load_canonical_corpus_records(
    corpus_root: str | Path,
    *,
    language: str | None = None,
    locale: str | None = None,
    category: str | None = None,
    status: str | None = None,
    case_ids: set[str] | None = None,
    audit_path: str | Path | None = None,
    audit_hash: str | None = None,
) -> tuple[dict, list[dict]]:
    """Load validated canonical v2 shards for local, non-publishable use."""
    root = Path(corpus_root)
    layout_errors = validate_corpus(root)
    if layout_errors:
        raise ValueError(
            "canonical corpus validation failed: " + "; ".join(layout_errors)
        )
    records = read_corpus(root)
    corpus_hash = canonical_corpus_hash(records)
    if audit_path is not None:
        audit = read_json(audit_path)
        expected = audit.get("corpus_hash") or audit.get("canonical_corpus_hash")
        if expected and expected != corpus_hash:
            raise ValueError("canonical audit does not match corpus hash")
        if audit.get("errors") or audit.get("oracle_complete") is False:
            raise ValueError("canonical strict Gold audit is not clean")
    else:
        audit = audit_records(records, strict=True)
        if audit["errors"]:
            raise ValueError(
                "canonical strict Gold audit failed: " + "; ".join(audit["errors"])
            )
    if audit_hash is not None and audit_hash != corpus_hash:
        raise ValueError("provided canonical audit hash does not match corpus hash")
    filtered = []
    for record in records:
        if language and record.get("language") != language:
            continue
        if locale and record.get("locale") != locale:
            continue
        if status and record.get("status") != status:
            continue
        if case_ids and record.get("id") not in case_ids:
            continue
        if category and category not in {
            unit.get("category") for unit in record.get("units", [])
        }:
            continue
        filtered.append(record)
    filtered.sort(key=lambda record: record.get("id", ""))
    manifest = {
        "artifact_kind": "local_canonical_benchmark",
        "publishable": False,
        "records": len(filtered),
        "canonical_records": len(records),
        "corpus_hash": corpus_hash,
        "source_policy_enforced": False,
        "audit": audit,
        "filters": {
            "language": language,
            "locale": locale,
            "category": category,
            "status": status,
            "case_ids": sorted(case_ids) if case_ids else None,
        },
    }
    return manifest, filtered


def verify_release(gold_root: str | Path) -> dict:
    root = Path(gold_root)
    manifest = load_release_manifest(root)
    file_hashes = manifest.get("file_hashes", {})
    if not isinstance(file_hashes, dict) or not file_hashes:
        raise ValueError("release manifest is missing file hashes")
    for relative_path, expected_hash in sorted(file_hashes.items()):
        target = root / relative_path
        if not target.exists():
            raise ValueError(f"release file missing: {relative_path}")
        actual_hash = sha256_file(target)
        if actual_hash != expected_hash:
            raise ValueError(
                f"release hash mismatch for {relative_path}: "
                f"expected {expected_hash} got {actual_hash}"
            )
    manifest_hash = sha256_file(root / "manifest.json")
    return {"manifest": manifest, "manifest_hash": manifest_hash}


def _release_record_paths(
    root: Path, manifest: dict, *, key: str, fallback_directories: tuple[str, ...]
) -> list[Path]:
    configured = manifest.get(key)
    if configured is None:
        return [
            root / "data" / directory
            for directory in fallback_directories
            if (root / "data" / directory).exists()
        ]
    if not isinstance(configured, list) or not all(
        isinstance(path, str) and path for path in configured
    ):
        raise ValueError(f"release manifest field {key} must be a list of paths")
    root = root.resolve()
    paths = []
    for relative in configured:
        path = (root / relative).resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise ValueError(
                f"release manifest field {key} contains non-local path: {relative}"
            ) from exc
        paths.append(path)
    return paths


def load_release_records(
    gold_root: str | Path,
    *,
    split: str | None = None,
    language: str | None = None,
    locale: str | None = None,
    category: str | None = None,
    status: str | None = None,
    case_ids: set[str] | None = None,
    source_loader: SourceTextLoader | None = None,
) -> tuple[dict, list[dict]]:
    verification = verify_release(gold_root)
    root = Path(gold_root)
    records = read_records(
        _release_record_paths(
            root,
            verification["manifest"],
            key="record_files",
            fallback_directories=("train", "dev", "test", "challenge"),
        )
    )
    filtered: list[dict] = []
    for record in records:
        hydrated = resolve_release_record(record, source_loader=source_loader)
        if (
            split
            and split not in {"all", "corpus"}
            and "split" in record
            and record.get("split") != split
        ):
            continue
        if language and hydrated.get("language") != language:
            continue
        if locale and hydrated.get("locale") != locale:
            continue
        if status and hydrated.get("status") != status:
            continue
        if case_ids and hydrated.get("id") not in case_ids:
            continue
        if category and category not in {
            unit.get("category") for unit in hydrated.get("units", [])
        }:
            continue
        filtered.append(hydrated)
    filtered.sort(key=lambda record: record.get("id", ""))
    return verification["manifest"] | {
        "manifest_hash": verification["manifest_hash"]
    }, filtered


def load_release_control_records(gold_root: str | Path) -> tuple[dict, list[dict]]:
    verification = verify_release(gold_root)
    root = Path(gold_root)
    records = read_records(
        _release_record_paths(
            root,
            verification["manifest"],
            key="control_files",
            fallback_directories=("controls",),
        )
    )
    records.sort(key=lambda record: record.get("id", ""))
    return verification["manifest"] | {
        "manifest_hash": verification["manifest_hash"]
    }, records


def load_prepare_callable(reference: str) -> Callable[..., str]:
    module_name, separator, function_name = reference.partition(":")
    if not separator:
        raise ValueError("prepare module must use module:function syntax")
    module = importlib.import_module(module_name)
    prepare_fn = getattr(module, function_name)
    if not callable(prepare_fn):
        raise TypeError(f"{reference} is not callable")
    return prepare_fn


def _prepare_wrapper(
    prepare_fn: Callable[..., str], profile: dict[str, Any]
) -> Callable[[str, str, str], str]:
    signature = inspect.signature(prepare_fn)
    parameter_count = len(signature.parameters)
    if parameter_count >= 4:
        return lambda text, language, locale: prepare_fn(
            text, language, locale, profile
        )
    return lambda text, language, locale: prepare_fn(text, language, locale)


def _resolve_prepare_callable(
    *,
    prepare_module: str | None,
    prepare: Callable[..., str] | None,
) -> Callable[..., str]:
    if prepare is not None and prepare_module is not None:
        raise ValueError("provide either prepare or prepare_module, not both")
    if prepare is not None:
        return prepare
    if prepare_module is not None:
        return load_prepare_callable(prepare_module)
    raise ValueError("either prepare or prepare_module is required")


def _render_failures_markdown(failures: list[dict[str, Any]]) -> str:
    lines = [
        "# Spokenform Gold Failures",
        "",
        "| id | status | prediction | expected |",
        "| --- | --- | --- | --- |",
    ]
    for item in failures:
        lines.append(
            f"| {item['id']} | {item['status']} | "
            f"{item['prediction']} | {item['expected_output']} |"
        )
    return "\n".join(lines) + "\n"


def run_benchmark(
    *,
    results_dir: str | Path,
    gold_root: str | Path | None = None,
    corpus_root: str | Path | None = None,
    split: str | None = None,
    prepare_module: str | None = None,
    prepare: Callable[..., str] | None = None,
    language: str | None = None,
    locale: str | None = None,
    category: str | None = None,
    status: str | None = None,
    case_ids: set[str] | None = None,
    mode: str = "canonical",
    profile_name: str = GOLD_PROFILE_V1["name"],
    spokenform_version: str = "unknown",
    spokenform_commit: str = "unknown",
    source_loader: SourceTextLoader | None = None,
) -> dict:
    if (gold_root is None) == (corpus_root is None):
        raise ValueError("provide exactly one of gold_root or corpus_root")
    registry_root = Path(gold_root or corpus_root)
    registry_path = registry_root / "taxonomy" / "evaluation_profiles.json"
    if not registry_path.exists():
        registry_path = None
    profile = benchmark_profile(profile_name, registry_path)
    if corpus_root is not None:
        manifest, records = load_canonical_corpus_records(
            corpus_root,
            language=language,
            locale=locale,
            category=category,
            status=status,
            case_ids=case_ids,
        )
        manifest = {
            **manifest,
            "benchmark_version": "local-canonical",
            "manifest_hash": manifest["corpus_hash"],
        }
    else:
        manifest, records = load_release_records(
            gold_root,
            split=split,
            language=language,
            locale=locale,
            category=category,
            status=status,
            case_ids=case_ids,
            source_loader=source_loader,
        )
    prepare_fn = _resolve_prepare_callable(
        prepare_module=prepare_module, prepare=prepare
    )
    predictions = build_prediction_records(
        records, _prepare_wrapper(prepare_fn, profile)
    )
    prediction_map = {item["id"]: item["output"] for item in predictions}
    summary = score_records(records, prediction_map, mode=mode)

    output_root = Path(results_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    if manifest.get("artifact_kind") == "local_canonical_benchmark":
        write_json(output_root / "manifest.json", manifest)
    write_jsonl(output_root / "predictions.jsonl", predictions)

    failures: list[dict[str, Any]] = []
    for result in summary["record_results"]:
        failed = (
            not result["accepted_match"]
            if mode == "accepted"
            else not result["canonical_match"]
        )
        if failed:
            failures.append(result)
    write_jsonl(output_root / "failures.jsonl", failures)
    (output_root / "failures.md").write_text(
        _render_failures_markdown(failures), encoding="utf-8"
    )

    now = datetime.now(timezone.utc)
    artifact = {
        "run_id": f"spokenform-gold-{now.strftime('%Y%m%dT%H%M%SZ')}",
        "timestamp_utc": now.isoformat(),
        "spokenform_version": spokenform_version,
        "spokenform_commit": spokenform_commit,
        "spokenform_gold_version": manifest["benchmark_version"],
        "gold_manifest_hash": manifest["manifest_hash"],
        "split": split,
        "record_count": len(records),
        "profile_name": profile["name"],
        "profile_id": profile["name"],
        "profile_config": profile,
        "profile_hash": profile_hash(profile),
        "profile_registry_version": load_registry(registry_path)["version"],
        "profile_registry_hash": registry_hash(load_registry(registry_path)),
        "policy_expansion": profile["policy_expansion"],
        "mode": mode,
        "canonical_score": summary["sentence_canonical_accuracy"],
        "accepted_score": summary["accepted_variant_accuracy"],
        "no_change_score": summary["no_change_accuracy"],
        "false_positive_rate": summary["false_positive_normalization_rate"],
        "summary": summary,
    }
    write_json(output_root / "summary.json", artifact)
    return artifact
