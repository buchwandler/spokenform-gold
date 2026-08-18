from __future__ import annotations

import argparse
import json
from pathlib import Path

from .adjudication import build_adjudication_queue
from .conflicts import find_conflicts
from .coverage import build_coverage, load_targets
from .importers import import_async, import_polynorm, import_proteno
from .io import expand_jsonl_paths, read_json, read_records, write_json, write_jsonl
from .judge_calibration import build_judge_calibration, load_judge_predictions
from .release import build_release
from .scoring import load_predictions, score_records
from .splitting import split_records
from .stats import build_stats
from .validation import load_categories, validate_records


def cmd_stats(args):
    files = args.paths
    record_files = [str(path) for path in expand_jsonl_paths(files)]
    records = read_records(files)
    result = build_stats(records, record_files)
    if args.json:
        write_json(args.json, result)
    print(
        "records={records} families={families} files={files}".format(
            records=result["records"],
            families=result["families"],
            files=result["file_count"],
        )
    )
    return 0


def cmd_validate(args):
    records = read_records(args.paths)
    categories = load_categories(args.categories) if args.categories else None
    errors = validate_records(records, judge=args.judge, categories=categories)
    if errors:
        print(f"INVALID: {len(errors)} error(s)")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"OK: {len(records)} record(s)")
    return 0


def cmd_coverage(args):
    records = read_records(args.paths)
    result = build_coverage(records, load_targets(args.targets))
    if args.json:
        write_json(args.json, result)
    print(
        f"records={result['records']} observed_categories={result['categories_observed']} gaps={len(result['gaps'])}"
    )
    return 0


def cmd_conflicts(args):
    records = read_records(args.paths)
    conflicts = find_conflicts(records, args.mode)
    if args.out:
        write_json(args.out, conflicts)
    else:
        print(json.dumps(conflicts, ensure_ascii=False, indent=2))
    return 2 if conflicts and args.fail_on_conflict else 0


def cmd_discover(args):
    records = read_records([args.against])
    text = Path(args.corpus).read_text(encoding="utf-8")
    from .discover import discover

    items = discover(text, records, args.rare_below)
    if args.out:
        write_jsonl(args.out, items)
    else:
        for item in items:
            print(json.dumps(item, ensure_ascii=False))
    return 0


def cmd_import_async(args):
    result = import_async(args.path, suite=args.suite)
    write_jsonl(args.out, result.records)
    if args.exclusions_out:
        write_json(args.exclusions_out, result.exclusions)
    print(
        f"wrote {len(result.records)} candidate records to {args.out} from {result.source_rows} source rows"
    )
    return 0


def cmd_import_polynorm(args):
    result = import_polynorm(args.path, format=args.format)
    write_jsonl(args.out, result.records)
    if args.exclusions_out:
        write_json(args.exclusions_out, result.exclusions)
    print(
        f"wrote {len(result.records)} candidate records to {args.out} from {result.source_rows} source rows"
    )
    return 0


def cmd_import_proteno(args):
    result = import_proteno(args.path, format=args.format)
    write_jsonl(args.out, result.records)
    if args.exclusions_out:
        write_json(args.exclusions_out, result.exclusions)
    print(
        f"wrote {len(result.records)} candidate records to {args.out} from {result.source_rows} source rows"
    )
    return 0


def cmd_split(args):
    records = read_records(args.paths)
    split_map = split_records(
        records,
        registry_path=args.registry,
        seed=args.seed,
        train_ratio=args.train,
        dev_ratio=args.dev,
        test_ratio=args.test,
    )
    output_root = Path(args.out_root)
    for split_name, split_records_list in split_map.items():
        write_jsonl(output_root / split_name / "sample.jsonl", split_records_list)
    print(
        "train={train} dev={dev} test={test}".format(
            train=len(split_map["train"]),
            dev=len(split_map["dev"]),
            test=len(split_map["test"]),
        )
    )
    return 0


def cmd_score(args):
    records = read_records(args.paths)
    predictions = load_predictions(args.predictions)
    result = score_records(records, predictions, mode=args.mode)
    if args.json:
        write_json(args.json, result)
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_adjudicate_queue(args):
    records = read_records(args.paths)
    conflicts = read_json(args.conflicts) if args.conflicts else []
    coverage = read_json(args.coverage) if args.coverage else {}
    queue = build_adjudication_queue(records, conflicts=conflicts, coverage=coverage)
    write_jsonl(args.out, queue)
    print(f"queued {len(queue)} records to {args.out}")
    return 0


def cmd_release_check(args):
    manifest = build_release(
        version=args.version,
        data_paths=args.data,
        out_root=args.out,
        maturity=args.maturity,
        registry_path=args.registry,
        source_manifest_path=args.source_manifest,
        coverage_profile=args.coverage_profile,
    )
    print(
        "release={version} records={records} families={families}".format(
            version=manifest["benchmark_version"],
            records=manifest["counts"]["records"],
            families=manifest["counts"]["families"],
        )
    )
    return 0


def cmd_judge_calibrate(args):
    records = read_records(args.paths)
    errors = validate_records(records, judge=True)
    if errors:
        raise ValueError("judge calibration input is invalid: " + "; ".join(errors))
    predictions = load_judge_predictions(args.predictions)
    result = build_judge_calibration(records, predictions)
    if args.json:
        write_json(args.json, result)
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def build_parser():
    parser = argparse.ArgumentParser(prog="spokenform-gold")
    sub = parser.add_subparsers(dest="cmd", required=True)

    stats = sub.add_parser("stats")
    stats.add_argument("paths", nargs="+")
    stats.add_argument("--json")
    stats.set_defaults(func=cmd_stats)

    validate = sub.add_parser("validate")
    validate.add_argument("paths", nargs="+")
    validate.add_argument("--judge", action="store_true")
    validate.add_argument("--categories")
    validate.set_defaults(func=cmd_validate)

    coverage = sub.add_parser("coverage")
    coverage.add_argument("paths", nargs="+")
    coverage.add_argument("--targets")
    coverage.add_argument("--json")
    coverage.set_defaults(func=cmd_coverage)

    conflicts = sub.add_parser("conflicts")
    conflicts.add_argument("paths", nargs="+")
    conflicts.add_argument("--mode", choices=["unit", "record"], default="unit")
    conflicts.add_argument("--out")
    conflicts.add_argument("--fail-on-conflict", action="store_true")
    conflicts.set_defaults(func=cmd_conflicts)

    discover = sub.add_parser("discover")
    discover.add_argument("corpus")
    discover.add_argument("--against", required=True)
    discover.add_argument("--out")
    discover.add_argument("--rare-below", type=int, default=3)
    discover.set_defaults(func=cmd_discover)

    async_import = sub.add_parser("import-async")
    async_import.add_argument("path")
    async_import.add_argument(
        "--suite", choices=["english", "multilingual"], default="english"
    )
    async_import.add_argument("--out", required=True)
    async_import.add_argument("--exclusions-out")
    async_import.set_defaults(func=cmd_import_async)

    polynorm_import = sub.add_parser("import-polynorm")
    polynorm_import.add_argument("path")
    polynorm_import.add_argument(
        "--format", choices=["auto", "raw", "projection", "official"], default="auto"
    )
    polynorm_import.add_argument("--out", required=True)
    polynorm_import.add_argument("--exclusions-out")
    polynorm_import.set_defaults(func=cmd_import_polynorm)

    proteno_import = sub.add_parser("import-proteno")
    proteno_import.add_argument("path")
    proteno_import.add_argument(
        "--format", choices=["auto", "raw", "projection", "official"], default="auto"
    )
    proteno_import.add_argument("--out", required=True)
    proteno_import.add_argument("--exclusions-out")
    proteno_import.set_defaults(func=cmd_import_proteno)

    split = sub.add_parser("split")
    split.add_argument("paths", nargs="+")
    split.add_argument("--train", type=float, default=0.70)
    split.add_argument("--dev", type=float, default=0.15)
    split.add_argument("--test", type=float, default=0.15)
    split.add_argument("--seed", type=int, default=20260818)
    split.add_argument("--registry", required=True)
    split.add_argument("--out-root", required=True)
    split.set_defaults(func=cmd_split)

    score = sub.add_parser("score")
    score.add_argument("paths", nargs="+")
    score.add_argument("--predictions", required=True)
    score.add_argument("--mode", choices=["canonical", "accepted"], default="canonical")
    score.add_argument("--json")
    score.set_defaults(func=cmd_score)

    adjudication = sub.add_parser("adjudicate-queue")
    adjudication.add_argument("paths", nargs="+")
    adjudication.add_argument("--conflicts")
    adjudication.add_argument("--coverage")
    adjudication.add_argument("--out", required=True)
    adjudication.set_defaults(func=cmd_adjudicate_queue)

    release = sub.add_parser("release-check")
    release.add_argument("--version", required=True)
    release.add_argument("--data", nargs="+", required=True)
    release.add_argument("--out", required=True)
    release.add_argument(
        "--maturity",
        choices=["experimental", "candidate", "stable"],
        default="experimental",
    )
    release.add_argument("--registry")
    release.add_argument("--source-manifest")
    release.add_argument("--coverage-profile", default="none")
    release.set_defaults(func=cmd_release_check)

    judge_calibrate = sub.add_parser("judge-calibrate")
    judge_calibrate.add_argument("paths", nargs="+")
    judge_calibrate.add_argument("--predictions", required=True)
    judge_calibrate.add_argument("--json")
    judge_calibrate.set_defaults(func=cmd_judge_calibrate)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
