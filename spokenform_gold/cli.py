from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .adjudication import build_adjudication_queue
from .census import build_upstream_census, write_census_artifacts
from .config import (
    ConfigError,
    default_config_path,
    load_config,
    require_runtime_paths,
    resolve_runtime_paths,
)
from .conflicts import find_conflicts
from .control_benchmark import load_control_predictions, score_control_records
from .control_validation import validate_control_records
from .coverage import build_control_coverage, build_coverage, load_targets
from .deduplication import deduplicate_candidates
from .exclusions import build_exclusion_analysis, load_exclusions
from .families import suggest_families
from .gold_audit import audit_records
from .importers import import_async, import_polynorm, import_proteno
from .ingestion import run_upstream_ingestion
from .io import (
    expand_jsonl_paths,
    read_json,
    read_jsonl,
    read_records,
    sha256_file,
    write_json,
    write_jsonl,
)
from .judge_calibration import build_judge_calibration, load_judge_predictions
from .merge import merge_candidate_files
from .migration import migrate_jsonl
from .oracle_diff import diff_records
from .pool import build_candidate_pool_summary
from .promotion import build_promoted_records
from .ranking import build_candidate_ranking, export_review_batch
from .release import build_release
from .review import (
    apply_reviewed_oracles,
    blind_review_batch,
    compare_review_batches,
    review_preflight,
    validate_review_rows,
    write_review_application,
)
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
    batch = blind_review_batch(
        read_records(args.paths), reviewer_slot=args.reviewer_slot
    )
    write_jsonl(args.out, batch)
    print(f"wrote {len(batch)} blind review records to {args.out}")
    return 0


def cmd_prepare_canonical_rereview(args):
    records = read_records(args.records)
    if not records:
        raise ValueError("canonical re-review preparation requires at least one record")
    output_root = Path(args.out_root)
    if output_root.exists() and any(output_root.iterdir()):
        raise ValueError(f"output root must be new or empty: {output_root}")
    output_root.mkdir(parents=True, exist_ok=True)
    review_a_path = output_root / "canonical-a.blind.jsonl"
    review_b_path = output_root / "canonical-b.blind.jsonl"
    write_jsonl(review_a_path, blind_review_batch(records, reviewer_slot="A"))
    write_jsonl(review_b_path, blind_review_batch(records, reviewer_slot="B"))
    manifest = {
        "schema_version": "1",
        "review_id": args.review_id,
        "canonical_inputs": [str(path) for path in args.records],
        "review_a": {"path": str(review_a_path), "sha256": sha256_file(review_a_path)},
        "review_b": {"path": str(review_b_path), "sha256": sha256_file(review_b_path)},
    }
    manifest_path = output_root / "manifest.json"
    write_json(manifest_path, manifest)
    print(f"prepared canonical re-review artifacts under {output_root}")
    print(f"review A: {review_a_path}")
    print(f"review B: {review_b_path}")
    print(f"manifest: {manifest_path}")
    return 0


def cmd_compare_reviews(args):
    comparisons = compare_review_batches(
        read_records([args.review_a]), read_records([args.review_b])
    )
    write_jsonl(args.out, comparisons)
    print(f"compared {len(comparisons)} review records to {args.out}")
    return 0


def _review_preflight_human(report: dict) -> str:
    lines = [
        f"canonical_review_state={report['canonical_review_state']}",
        f"canonical_records={report['canonical_records']}",
        f"sentence_oracles={report['sentence_oracles']}",
    ]
    for name in ("review_a", "review_b"):
        review = report[name]
        reviewer_id = review.get("reviewer_id") or "missing"
        lines.extend(
            [
                f"{name}.rows={review['rows']}",
                f"{name}.slot={review['slot']}",
                f"{name}.reviewer_id={reviewer_id}",
                f"{name}.completed={review['completed']}",
                f"{name}.unreviewed={review['unreviewed']}",
            ]
        )
    lines.extend(
        [
            f"id_sets_match={'yes' if report['id_sets_match'] else 'no'}",
            f"context_match={'yes' if report['context_match'] else 'no'}",
            f"canonical_identity_match={'yes' if report['canonical_identity_match'] else 'no'}",
            f"ready={'yes' if report['ready'] else 'no'}",
        ]
    )
    if report["issues"]:
        lines.append("issues:")
        lines.extend(f"- {issue['message']}" for issue in report["issues"])
    return "\n".join(lines)


def _artifact_issue(scope: str, path: Path, code: str, detail: str) -> dict:
    return {
        "scope": scope,
        "code": code,
        "message": f"{scope} artifact {path}: {detail}",
    }


def _read_review_artifact(path: Path, *, scope: str) -> tuple[list[dict], list[dict]]:
    """Read one review artifact while preserving aggregate preflight diagnostics."""
    if not path.is_file():
        return [], [
            _artifact_issue(
                scope, path, "file_not_readable", "file is missing or not readable"
            )
        ]
    try:
        return read_jsonl(path), []
    except (OSError, TypeError, ValueError) as exc:
        return [], [_artifact_issue(scope, path, "invalid_jsonl", str(exc))]


def _add_path_issue(report: dict, scope: str, path: str) -> None:
    report["issues"].append(
        {
            "scope": scope,
            "code": "file_not_readable",
            "message": f"{scope} artifact is not a readable file: {path}",
        }
    )
    report["issues"].sort(
        key=lambda item: (
            item.get("scope", ""),
            item.get("code", ""),
            item.get("message", ""),
        )
    )
    report["ready"] = False
    report["canonical_review_state"] = "blocked"


def cmd_review_preflight(args):
    records = read_records(args.records)
    review_a_path = Path(args.review_a)
    review_b_path = Path(args.review_b)
    review_a, issues_a = _read_review_artifact(review_a_path, scope="review_a")
    review_b, issues_b = _read_review_artifact(review_b_path, scope="review_b")
    report = review_preflight(records, review_a, review_b)
    report["issues"].extend(issues_a + issues_b)
    report["issues"].sort(
        key=lambda item: (
            item.get("scope", ""),
            item.get("code", ""),
            item.get("sentence_oracle_id", ""),
            item.get("message", ""),
        )
    )
    if report["issues"]:
        report["ready"] = False
        report["canonical_review_state"] = "blocked"
    if args.json:
        write_json(args.json, report)
    print(_review_preflight_human(report))
    return 0 if report["ready"] else 2


def cmd_validate_review(args):
    path = Path(args.review)
    rows, artifact_issues = _read_review_artifact(
        path, scope=f"review_{args.slot.lower()}"
    )
    report = validate_review_rows(rows, slot=args.slot)
    report["issues"].extend(artifact_issues)
    report["issues"].sort(
        key=lambda item: (
            item.get("scope", ""),
            item.get("code", ""),
            item.get("sentence_oracle_id", ""),
            item.get("message", ""),
        )
    )
    if report["issues"]:
        report["ready"] = False
    if args.json:
        write_json(
            args.json,
            {key: value for key, value in report.items() if key != "_indexed"},
        )
    print(
        _review_preflight_human(
            {
                "canonical_review_state": "ready" if report["ready"] else "blocked",
                "canonical_records": 0,
                "sentence_oracles": report["rows"],
                "review_a": report
                if args.slot == "A"
                else {
                    "slot": "A",
                    "rows": 0,
                    "reviewer_id": None,
                    "completed": 0,
                    "unreviewed": 0,
                },
                "review_b": report
                if args.slot == "B"
                else {
                    "slot": "B",
                    "rows": 0,
                    "reviewer_id": None,
                    "completed": 0,
                    "unreviewed": 0,
                },
                "id_sets_match": True,
                "context_match": True,
                "canonical_identity_match": True,
                "ready": report["ready"],
                "issues": report["issues"],
            }
        )
    )
    return 0 if report["ready"] else 2


def cmd_apply_reviewed_oracles(args):
    records = read_records(args.records)
    review_a = read_records([args.review_a])
    review_b = read_records([args.review_b])
    decisions = read_records(args.decisions)
    updated, comparisons, report = apply_reviewed_oracles(
        records, review_a, review_b, decisions
    )
    write_review_application(
        args.out_root,
        updated,
        comparisons,
        report,
        input_paths=[*args.records, args.review_a, args.review_b, *args.decisions],
    )
    print(
        f"applied {len(updated)} reviewed oracles to {args.out_root}; "
        f"agreement={report['agreement']} disagreement={report['disagreement']}"
    )
    return 0


def cmd_census_upstreams(args):
    candidates = read_records(args.candidates)
    exclusions = []
    for path in args.exclusions or []:
        payload = read_json(path)
        exclusions.extend(
            payload if isinstance(payload, list) else payload.get("exclusions", [])
        )
    reports = [read_json(path) for path in args.reports or []]
    census = build_upstream_census(candidates, exclusions, reports)
    if not census["summary"]["row_accounting_ok"]:
        raise ValueError("upstream census failed row accounting")
    artifacts = write_census_artifacts(args.out_root, census)
    print(
        json.dumps(
            {"summary": census["summary"], "artifacts": artifacts}, ensure_ascii=False
        )
    )
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
    config_path = args.config if args.config is not None else default_config_path()
    config = load_config(config_path, explicit=args.config is not None)
    paths = require_runtime_paths(
        resolve_runtime_paths(
            config=config,
            source_cache=args.source_cache,
            work_root=args.work_root,
        )
    )
    summary = run_upstream_ingestion(
        paths.source_cache,
        paths.work_root,
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
    promoted, report = build_promoted_records(candidates, decisions, existing)
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
    result = score_control_records(
        records, load_control_predictions(args.predictions), validate=False
    )
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


def _path_info(path: Path | None) -> dict:
    if path is None:
        return {"path": None, "exists": False, "writable": False}
    exists = path.exists()
    probe = path if exists else path.parent
    return {
        "path": str(path),
        "exists": exists,
        "writable": bool(probe.exists() and os.access(probe, os.W_OK)),
    }


def cmd_doctor(args):
    config_path = args.config if args.config is not None else default_config_path()
    config = load_config(config_path, explicit=args.config is not None)
    repo_root = (config.path.parent if config.path else Path.cwd()).resolve()
    paths = resolve_runtime_paths(config=config, source_cache=None, work_root=None)
    source_lock = repo_root / "sources" / "source-lock.json"
    canonical = [repo_root / "data" / name for name in ("train", "dev", "test")]
    review_root = paths.work_root / "reviews" / "canonical" if paths.work_root else None
    report = {
        "config": _path_info(config.path or config_path.resolve()),
        "repo_root": str(repo_root),
        "source_cache": _path_info(paths.source_cache),
        "work_root": _path_info(paths.work_root),
        "source_lock": _path_info(source_lock),
        "canonical_records": [str(path) for path in canonical],
        "canonical_record_roots": [_path_info(path) for path in canonical],
        "canonical_review_root": _path_info(review_root),
    }
    if args.json:
        write_json(args.json, report)
    print(f"config: {report['config']['path']}")
    print(f"repo_root: {report['repo_root']}")
    for key in ("source_cache", "work_root", "source_lock"):
        item = report[key]
        print(f"{key}: {item['path']}")
        print(f"{key}_exists: {'yes' if item['exists'] else 'no'}")
        print(f"{key}_writable: {'yes' if item['writable'] else 'no'}")
    print("canonical_records:")
    for path in report["canonical_records"]:
        print(f"  {path}")
    return 0


def build_parser():
    parser = argparse.ArgumentParser(prog="spokenform-gold")
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Project-local TOML configuration file for runtime paths.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Show tracebacks for expected workflow errors.",
    )
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
    prepare = sub.add_parser("prepare-canonical-rereview")
    prepare.add_argument("--records", nargs="+", required=True)
    prepare.add_argument("--out-root", required=True)
    prepare.add_argument("--review-id", required=True)
    prepare.set_defaults(func=cmd_prepare_canonical_rereview)

    preflight = sub.add_parser("review-preflight")
    preflight.add_argument("--records", nargs="+", required=True)
    preflight.add_argument("--review-a", required=True)
    preflight.add_argument("--review-b", required=True)
    preflight.add_argument("--json")
    preflight.set_defaults(func=cmd_review_preflight)

    validate_review = sub.add_parser("validate-review")
    validate_review.add_argument("review")
    validate_review.add_argument("--slot", choices=["A", "B"], required=True)
    validate_review.add_argument("--json")
    validate_review.set_defaults(func=cmd_validate_review)

    compare_reviews = sub.add_parser("compare-reviews")
    compare_reviews.add_argument("review_a")
    compare_reviews.add_argument("review_b")
    compare_reviews.add_argument("--out", required=True)
    compare_reviews.set_defaults(func=cmd_compare_reviews)

    apply_reviews = sub.add_parser("apply-reviewed-oracles")
    apply_reviews.add_argument("--records", nargs="+", required=True)
    apply_reviews.add_argument("--review-a", required=True)
    apply_reviews.add_argument("--review-b", required=True)
    apply_reviews.add_argument("--decisions", nargs="+", required=True)
    apply_reviews.add_argument("--out-root", required=True)
    apply_reviews.set_defaults(func=cmd_apply_reviewed_oracles)

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
    ingest.add_argument("--source-cache", type=Path, default=None)
    ingest.add_argument("--work-root", type=Path, default=None)
    ingest.add_argument(
        "--sources", nargs="+", default=["async_tn", "polynorm", "proteno"]
    )
    ingest.add_argument(
        "--languages", nargs="+", default=["en", "de", "es", "fr", "it", "pt"]
    )
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
    doctor = sub.add_parser("doctor", aliases=["paths"])
    doctor.add_argument("--json")
    doctor.set_defaults(func=cmd_doctor)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except (ValueError, TypeError, OSError) as exc:
        workflow_commands = {
            "review-preflight",
            "validate-review",
            "compare-reviews",
            "apply-reviewed-oracles",
        }
        if args.cmd not in workflow_commands or args.debug:
            raise
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
