from __future__ import annotations

import copy
import importlib
import inspect
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .adapter import build_prediction_records
from .io import read_json, read_records, sha256_file, write_json, write_jsonl
from .scoring import score_records
from .source_resolver import SourceTextLoader, resolve_release_record


PrepareCallable = Callable[[str, str, str, dict[str, Any] | None], str]

GOLD_PROFILE_V1 = {
    "name": "gold-v1",
    "prepare_kwargs": {
        "use_spacy": False,
        "normalize_literals": True,
        "generic_acronym_mode": "spell_unknown",
        "generic_acronym_case": "upper",
        "registered_acronym_mode": "spell",
        "symbol_mode": "none",
        "long_number_mode": "contextual",
    },
}
BENCHMARK_PROFILES = {GOLD_PROFILE_V1["name"]: GOLD_PROFILE_V1}


def benchmark_profile(name: str = GOLD_PROFILE_V1["name"]) -> dict[str, Any]:
    try:
        return copy.deepcopy(BENCHMARK_PROFILES[name])
    except KeyError as exc:
        raise ValueError(f"unsupported profile {name!r}") from exc


def load_release_manifest(gold_root: str | Path) -> dict:
    root = Path(gold_root)
    manifest_path = root / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"missing release manifest: {manifest_path}")
    return read_json(manifest_path)


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
    records = read_records([root / "data"])
    filtered: list[dict] = []
    for record in records:
        hydrated = resolve_release_record(record, source_loader=source_loader)
        if split and record.get("split") != split:
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
    gold_root: str | Path,
    split: str | None,
    results_dir: str | Path,
    prepare_module: str | None = None,
    prepare: Callable[..., str] | None = None,
    language: str | None = None,
    locale: str | None = None,
    category: str | None = None,
    case_ids: set[str] | None = None,
    mode: str = "canonical",
    profile_name: str = GOLD_PROFILE_V1["name"],
    spokenform_version: str = "unknown",
    spokenform_commit: str = "unknown",
    source_loader: SourceTextLoader | None = None,
) -> dict:
    profile = benchmark_profile(profile_name)
    manifest, records = load_release_records(
        gold_root,
        split=split,
        language=language,
        locale=locale,
        category=category,
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
        "profile_config": profile,
        "mode": mode,
        "canonical_score": summary["sentence_canonical_accuracy"],
        "accepted_score": summary["accepted_variant_accuracy"],
        "no_change_score": summary["no_change_accuracy"],
        "false_positive_rate": summary["false_positive_normalization_rate"],
        "summary": summary,
    }
    write_json(output_root / "summary.json", artifact)
    return artifact
