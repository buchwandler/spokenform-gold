from __future__ import annotations

import importlib
import inspect
from datetime import datetime, timezone
from pathlib import Path

from spokenform_gold.adapter import build_prediction_records
from spokenform_gold.io import write_json, write_jsonl
from spokenform_gold.scoring import score_records

from .spokenform_gold_data import load_release_records


GOLD_PROFILE_V1 = {
    "name": "gold-v1",
    "use_spacy": False,
    "normalize_literals": True,
    "generic_acronym_mode": "letters",
    "generic_acronym_case": "preserve",
    "registered_acronym_mode": "letters",
    "symbol_mode": "normalize",
    "long_number_mode": "digitwise",
}


def load_prepare_callable(reference: str):
    module_name, separator, function_name = reference.partition(":")
    if not separator:
        raise ValueError("prepare module must use module:function syntax")
    module = importlib.import_module(module_name)
    prepare_fn = getattr(module, function_name)
    if not callable(prepare_fn):
        raise TypeError(f"{reference} is not callable")
    return prepare_fn


def _prepare_wrapper(prepare_fn, profile: dict):
    signature = inspect.signature(prepare_fn)
    parameter_count = len(signature.parameters)
    if parameter_count >= 4:
        return lambda text, language, locale: prepare_fn(
            text, language, locale, profile
        )
    return lambda text, language, locale: prepare_fn(text, language, locale)


def run_benchmark(
    *,
    gold_root: str | Path,
    split: str | None,
    prepare_module: str,
    results_dir: str | Path,
    language: str | None = None,
    locale: str | None = None,
    category: str | None = None,
    case_ids: set[str] | None = None,
    mode: str = "canonical",
    profile_name: str = "gold-v1",
    spokenform_version: str = "unknown",
    spokenform_commit: str = "unknown",
) -> dict:
    if profile_name != GOLD_PROFILE_V1["name"]:
        raise ValueError(f"unsupported profile {profile_name!r}")
    manifest, records = load_release_records(
        gold_root,
        split=split,
        language=language,
        locale=locale,
        category=category,
        case_ids=case_ids,
    )
    prepare_fn = load_prepare_callable(prepare_module)
    predictions = build_prediction_records(
        records, _prepare_wrapper(prepare_fn, GOLD_PROFILE_V1)
    )
    prediction_map = {item["id"]: item["output"] for item in predictions}
    summary = score_records(records, prediction_map, mode=mode)

    output_root = Path(results_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    write_jsonl(output_root / "predictions.jsonl", predictions)

    failures = []
    for result in summary["record_results"]:
        failed = (
            not result["accepted_match"]
            if mode == "accepted"
            else not result["canonical_match"]
        )
        if failed:
            failures.append(result)
    write_jsonl(output_root / "failures.jsonl", failures)
    failure_lines = [
        "# Spokenform Gold Failures",
        "",
        "| id | status | prediction | expected |",
        "| --- | --- | --- | --- |",
    ]
    for item in failures:
        failure_lines.append(
            f"| {item['id']} | {item['status']} | {item['prediction']} | {item['expected_output']} |"
        )
    (output_root / "failures.md").write_text(
        "\n".join(failure_lines) + "\n", encoding="utf-8"
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
        "profile_name": GOLD_PROFILE_V1["name"],
        "profile_config": GOLD_PROFILE_V1,
        "mode": mode,
        "canonical_score": summary["sentence_canonical_accuracy"],
        "accepted_score": summary["accepted_variant_accuracy"],
        "no_change_score": summary["no_change_accuracy"],
        "false_positive_rate": summary["false_positive_normalization_rate"],
        "summary": summary,
    }
    write_json(output_root / "summary.json", artifact)
    return artifact
