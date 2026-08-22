from __future__ import annotations

import argparse
import json
from pathlib import Path

from .adjudication import build_adjudication_queue
from .conflicts import find_conflicts
from .census import build_upstream_census, write_census_artifacts
from .control_benchmark import load_control_predictions, score_control_records
from .control_validation import validate_control_records
from .coverage import build_control_coverage, build_coverage, load_targets
from .deduplication import deduplicate_candidates
from .exclusions import build_exclusion_analysis, load_exclusions
from .families import suggest_families
from .importers import import_async, import_polynorm, import_proteno
from .ingestion import run_upstream_ingestion
from .io import (
    expand_jsonl_paths,
    read_json,
    read_jsonl,
    read_records,
    write_json,
    write_jsonl,
)
from .judge_calibration import build_judge_calibration, load_judge_predictions
from .merge import merge_candidate_files
from .gold_audit import audit_records
from .oracle_diff import diff_records
from .migration import migrate_jsonl
from .pool import build_candidate_pool_summary
from .promotion import build_promoted_records
from .ranking import build_candidate_ranking, export_review_batch
from .release import build_release
from .review import blind_review_batch
from .scoring import load_predictions, score_records
from .source_lock import build_source_lock
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


def cmd_migrate_oracle(args):
    count = migrate_jsonl(args.input, args.out)
    print(f"migrated {count} records to {args.out}")
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


def cmd_blind_review(args):
    batch = blind_review_batch(read_records(args.paths), reviewer_slot=args.reviewer_slot)
    write_jsonl(args.out, batch)
    print(f"wrote {len(batch)} blind review records to {args.out}")
    return 0


def cmd_census_upstreams(args):
    candidates = read_records(args.candidates)
    exclusions = []
    for path in args.exclusions or []:
        payload = read_json(path)
        exclusions.extend(payload if isinstance(payload, list) else payload.get("exclusions", []))
    reports = [read_json(path) for path in args.reports or []]
    census = build_upstream_census(candidates, exclusions, reports)
    if not census["summary"]["row_accounting_ok"]:
        raise ValueError("upstream census failed row accounting")
    artifacts = write_census_artifacts(args.out_root, census)
    print(json.dumps({"summary": census["summary"], "artifacts": artifacts}, ensure_ascii=False))
    return 0


def cmd_census_stats(args):
    report = read_json(args.path)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def cmd_gold_audit(args):
    report = audit_records(read_records(args.paths), strict=args.strict)
    if args.json:
        write_json(args.json, report)
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report["errors"] else 0


def cmd_oracle_diff(args):
    report = diff_records(read_records(args.old), read_records(args.new))
    if args.json:
        write_json(args.json, report)
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))
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


def cmd_control_coverage(args):
    records = read_records(args.paths)
    errors = validate_control_records(records, registry_path=args.registry)
    if errors:
        raise ValueError("control validation failed: " + "; ".join(errors))
    result = build_control_coverage(records, load_targets(args.targets))
    if args.json:
        write_json(args.json, result)
    print(
        f"records={result['records']} observed_controls={result['controls_observed']} gaps={len(result['gaps'])}"
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


def _write_import_outputs(args, result):
    write_jsonl(args.out, result.records)
    if args.exclusions_out:
        write_json(args.exclusions_out, result.exclusions)
    if args.report_out:
        write_json(args.report_out, result.diagnostics)
    print(
        f"wrote {len(result.records)} candidate records to {args.out} from {result.source_rows} source rows"
    )
    return 0


def cmd_import_async(args):
    return _write_import_outputs(args, import_async(args.path, suite=args.suite))


def cmd_import_polynorm(args):
    return _write_import_outputs(args, import_polynorm(args.path, format=args.format))


def cmd_import_proteno(args):
    return _write_import_outputs(args, import_proteno(args.path, format=args.format))


def cmd_dedupe_candidates(args):
    result = deduplicate_candidates(read_records(args.paths))
    if args.out:
        write_json(args.out, result)
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_family_suggestions(args):
    result = suggest_families(read_records(args.paths))
    if args.out:
        write_json(args.out, result)
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_merge_candidates(args):
    merged = merge_candidate_files(args.paths, args.out)
    print(f"merged {len(merged)} candidates to {args.out}")
    return 0

def cmd_rank_candidates(args):
    candidates = read_records(args.paths)
    reviewed = read_records(args.against)
    targets = load_targets(args.targets)
    dedupe = read_json(args.dedupe) if args.dedupe else {}
    conflicts = read_json(args.conflicts) if args.conflicts else []
    ranked = build_candidate_ranking(
        candidates,
        reviewed,
        targets=targets,
        dedupe=dedupe,
        conflicts=conflicts,
    )
    write_jsonl(args.out, ranked)
    print(f"ranked {len(ranked)} candidates to {args.out}")
    return 0

def cmd_analyze_exclusions(args):
    result = build_exclusion_analysis(load_exclusions(args.paths))
    if args.out:
        write_json(args.out, result)
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_pool_stats(args):
    candidates = read_records(args.paths)
    exclusions = load_exclusions(args.exclusions) if args.exclusions else []
    reports = [read_json(path) for path in args.reports] if args.reports else []
    conflicts = read_json(args.conflicts) if args.conflicts else []
    result = build_candidate_pool_summary(
        candidates, exclusions=exclusions, conflicts=conflicts, import_reports=reports
    )
    if args.out:
        write_json(args.out, result)
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_review_batch(args):
    ranked = []
    for path in expand_jsonl_paths(args.ranked):
        ranked.extend(read_jsonl(path))
    batch = export_review_batch(
        ranked,
        limit=args.limit,
        languages=set(args.languages or []),
        max_per_category=args.max_per_category,
        max_per_family_suggestion=args.max_per_family_suggestion,
    )
    write_jsonl(args.out, batch)
    print(f"exported {len(batch)} review candidates to {args.out}")
    return 0

def cmd_ingest_upstreams(args):
    summary = run_upstream_ingestion(
        args.source_cache,
        args.work_root,
        sources=args.sources,
        languages=args.languages,
        reviewed_paths=args.reviewed,
        targets_path=args.targets,
        batch_limit=args.batch_limit,
        batch_name=args.batch_name,
    )
    print(
        f"ingested {summary['records']} candidates and {summary['exclusions']} exclusions "
        f"into {summary['work_root']}"
    )
    return 0
def cmd_source_lock(args):
    write_json(args.out, build_source_lock(args.manifest))
    print(f"wrote source lock to {args.out}")
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
        control_paths=args.controls,
    )
    print(
        "release={version} records={records} families={families}".format(
            version=manifest["benchmark_version"],
            records=manifest["counts"]["records"],
            families=manifest["counts"]["families"],
        )
    )
    return 0


def cmd_promote_reviewed(args):
    candidates = read_records(args.candidates)
    decisions = read_records(args.decisions)
    existing = read_records(args.against)
    promoted, report = build_promoted_records(
        candidates, decisions, existing
    )
    write_jsonl(args.out, promoted)
    write_json(args.report, report)
    print(
        f"promoted {len(promoted)} of {len(candidates)} candidates to {args.out}; "
        f"report={args.report}"
    )
    return 0


def cmd_validate_controls(args):
    records = read_records(args.paths)
    errors = validate_control_records(records, registry_path=args.registry)
    if errors:
        print(f"INVALID: {len(errors)} error(s)")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"OK: {len(records)} control record(s)")
    return 0


def cmd_score_controls(args):
    records = read_records(args.paths)
    errors = validate_control_records(records, registry_path=args.registry)
    if errors:
        raise ValueError("control validation failed: " + "; ".join(errors))
    result = score_control_records(records, load_control_predictions(args.predictions), validate=False)
    if args.json:
        write_json(args.json, result)
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
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

    migrate = sub.add_parser("migrate-oracle")
    migrate.add_argument("input")
    migrate.add_argument("--out", required=True)
    migrate.set_defaults(func=cmd_migrate_oracle)

    validate = sub.add_parser("validate")
    validate.add_argument("paths", nargs="+")
    validate.add_argument("--judge", action="store_true")
    validate.add_argument("--categories")
    validate.set_defaults(func=cmd_validate)

    blind = sub.add_parser("blind-review")
    blind.add_argument("paths", nargs="+")
    blind.add_argument("--reviewer-slot", choices=["A", "B"], required=True)
    blind.add_argument("--out", required=True)
    blind.set_defaults(func=cmd_blind_review)

    census = sub.add_parser("census-upstreams")
    census.add_argument("candidates", nargs="+")
    census.add_argument("--exclusions", nargs="*")
    census.add_argument("--reports", nargs="*")
    census.add_argument("--out-root", required=True)
    census.set_defaults(func=cmd_census_upstreams)

    census_stats = sub.add_parser("census-stats")
    census_stats.add_argument("path")
    census_stats.set_defaults(func=cmd_census_stats)

    audit = sub.add_parser("gold-audit")
    audit.add_argument("paths", nargs="+")
    audit.add_argument("--strict", action="store_true")
    audit.add_argument("--json")
    audit.set_defaults(func=cmd_gold_audit)

    oracle_diff = sub.add_parser("oracle-diff")
    oracle_diff.add_argument("old", nargs="+")
    oracle_diff.add_argument("--new", nargs="+", required=True)
    oracle_diff.add_argument("--json")
    oracle_diff.set_defaults(func=cmd_oracle_diff)

    coverage = sub.add_parser("coverage")
    coverage.add_argument("paths", nargs="+")
    coverage.add_argument("--targets")
    coverage.add_argument("--json")
    coverage.set_defaults(func=cmd_coverage)

    control_coverage = sub.add_parser("control-coverage")
    control_coverage.add_argument("paths", nargs="+")
    control_coverage.add_argument("--targets")
    control_coverage.add_argument("--registry")
    control_coverage.add_argument("--json")
    control_coverage.set_defaults(func=cmd_control_coverage)

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
    async_import.add_argument("--report-out")
    async_import.set_defaults(func=cmd_import_async)

    polynorm_import = sub.add_parser("import-polynorm")
    polynorm_import.add_argument("path")
    polynorm_import.add_argument(
        "--format", choices=["auto", "raw", "projection", "official"], default="auto"
    )
    polynorm_import.add_argument("--out", required=True)
    polynorm_import.add_argument("--exclusions-out")
    polynorm_import.add_argument("--report-out")
    polynorm_import.set_defaults(func=cmd_import_polynorm)

    proteno_import = sub.add_parser("import-proteno")
    proteno_import.add_argument("path")
    proteno_import.add_argument(
        "--format", choices=["auto", "raw", "projection", "official"], default="auto"
    )
    proteno_import.add_argument("--out", required=True)
    proteno_import.add_argument("--exclusions-out")
    proteno_import.add_argument("--report-out")
    proteno_import.set_defaults(func=cmd_import_proteno)

    merge = sub.add_parser("merge-candidates")
    merge.add_argument("paths", nargs="+")
    merge.add_argument("--out", required=True)
    merge.set_defaults(func=cmd_merge_candidates)

    ranking = sub.add_parser("rank-candidates")
    ranking.add_argument("paths", nargs="+")
    ranking.add_argument("--against", nargs="+", required=True)
    ranking.add_argument("--targets")
    ranking.add_argument("--dedupe")
    ranking.add_argument("--conflicts")
    ranking.add_argument("--out", required=True)
    ranking.set_defaults(func=cmd_rank_candidates)

    exclusions = sub.add_parser("analyze-exclusions")
    exclusions.add_argument("paths", nargs="+")
    exclusions.add_argument("--out")
    exclusions.set_defaults(func=cmd_analyze_exclusions)

    pool = sub.add_parser("pool-stats")
    pool.add_argument("paths", nargs="+")
    pool.add_argument("--exclusions", nargs="*")
    pool.add_argument("--reports", nargs="*")
    pool.add_argument("--conflicts")
    pool.add_argument("--out")
    pool.set_defaults(func=cmd_pool_stats)

    batch = sub.add_parser("review-batch")
    batch.add_argument("ranked", nargs="+")
    batch.add_argument("--limit", type=int, default=100)
    batch.add_argument("--max-per-category", type=int)
    batch.add_argument("--max-per-family-suggestion", type=int)
    batch.add_argument("--languages", nargs="*")
    batch.add_argument("--out", required=True)
    batch.set_defaults(func=cmd_review_batch)

    ingest = sub.add_parser("ingest-upstreams")
    ingest.add_argument("--source-cache", required=True)
    ingest.add_argument("--work-root", required=True)
    ingest.add_argument("--sources", nargs="+", default=["async_tn", "polynorm", "proteno"])
    ingest.add_argument("--languages", nargs="+", default=["en", "de", "es", "fr", "it", "pt"])
    ingest.add_argument("--reviewed", nargs="+", default=None)
    ingest.add_argument("--targets")
    ingest.add_argument("--batch-limit", type=int, default=100)
    ingest.add_argument("--batch-name", default="batch-0001")
    ingest.set_defaults(func=cmd_ingest_upstreams)

    dedupe = sub.add_parser("dedupe-candidates")
    dedupe.add_argument("paths", nargs="+")
    dedupe.add_argument("--out")
    dedupe.set_defaults(func=cmd_dedupe_candidates)

    families = sub.add_parser("family-suggestions")
    families.add_argument("paths", nargs="+")
    families.add_argument("--out")
    families.set_defaults(func=cmd_family_suggestions)

    source_lock = sub.add_parser("source-lock")
    source_lock.add_argument("--manifest")
    source_lock.add_argument("--out", required=True)
    source_lock.set_defaults(func=cmd_source_lock)

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
    release.add_argument("--controls", nargs="+")
    release.set_defaults(func=cmd_release_check)

    promote = sub.add_parser("promote-reviewed")
    promote.add_argument("--candidates", nargs="+", required=True)
    promote.add_argument("--decisions", nargs="+", required=True)
    promote.add_argument("--against", nargs="+", required=True)
    promote.add_argument("--out", required=True)
    promote.add_argument("--report", required=True)
    promote.set_defaults(func=cmd_promote_reviewed)


    validate_controls = sub.add_parser("validate-controls")
    validate_controls.add_argument("paths", nargs="+")
    validate_controls.add_argument("--registry")
    validate_controls.set_defaults(func=cmd_validate_controls)
    score_controls = sub.add_parser("score-controls")
    score_controls.add_argument("paths", nargs="+")
    score_controls.add_argument("--predictions", nargs="+", required=True)
    score_controls.add_argument("--registry")
    score_controls.add_argument("--json")
    score_controls.set_defaults(func=cmd_score_controls)

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
