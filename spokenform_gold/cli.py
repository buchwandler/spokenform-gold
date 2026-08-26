from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .adjudication import build_adjudication_queue
from .adjudication_quality import validate_adjudication_batch
from .census import build_upstream_census, write_census_artifacts
from .collection import DEFAULT_V2_COLLECTION_LIMIT, collect_batch
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
from .corrections import (
    apply_correction,
    prepare_correction_context,
    write_correction_application,
)
from .coverage import build_control_coverage, build_coverage, load_targets
from .deduplication import deduplicate_candidates
from .exclusions import build_exclusion_analysis, load_exclusions
from .export import export_family_safe_splits
from .families import suggest_families
from .gold_audit import audit_records
from .html_report import render_release_html
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
from .packets import (
    adjudication_packet_rows,
    finalize_adjudication,
    merge_adjudication_rows,
    merge_review_rows,
    review_packet_rows,
    serialized_row_bytes,
)
from .pool import build_candidate_pool_summary
from .promotion import build_promoted_records
from .ranking import build_candidate_ranking, export_review_batch
from .release import build_release
from .review import (
    apply_reviewed_oracles,
    blind_review_batch,
    compare_review_batches,
    detect_review_contract,
    review_preflight,
    validate_review_rows,
    validate_v2_review_rows,
    write_review_application,
)
from .review_html import render_review_html
from .review_lineage import (
    backfill_legacy_evidence,
    build_review_evidence,
    resolve_record_evidence,
    write_review_evidence,
)
from .safe_search import (
    DEFAULT_MAX_CHARS_PER_LINE,
    DEFAULT_MAX_MATCHES,
    DEFAULT_MAX_OUTPUT,
    search_text,
)
from .scoring import load_predictions, score_records
from .source_lock import build_source_lock
from .splitting import split_records
from .stats import build_stats
from .validation import load_categories, validate_records
from .workflow import check_reviews, integrate_batch


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
    if not args.paths:
        args.paths = (
            [Path("data/corpus.jsonl")]
            if Path("data/corpus.jsonl").exists()
            else [Path("data/train"), Path("data/dev"), Path("data/test")]
        )
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


def _v2_review_human(report: dict) -> str:
    lines = [
        "review_contract=sentence-centric-v2",
        f"review_state={'ready' if report['ready'] else 'blocked'}",
        f"rows={report['rows']}",
        f"slot={report['slot']}",
        f"reviewer_id={report.get('reviewer_id') or 'missing'}",
        f"completed={report['completed']}",
        f"unreviewed={report['unreviewed']}",
        f"duplicate_case_ids={len(report.get('duplicate_case_ids', []))}",
        f"ready={'yes' if report['ready'] else 'no'}",
    ]
    if report.get("issues"):
        lines.append("issues:")
        lines.extend(f"- {issue['message']}" for issue in report["issues"])
    return "\n".join(lines)


def cmd_validate_review(args):
    path = Path(args.review)
    rows, artifact_issues = _read_review_artifact(
        path, scope=f"review_{args.slot.lower()}"
    )
    contract = detect_review_contract(rows, requested=args.contract)
    if contract == "v2":
        report = validate_v2_review_rows(rows, slot=args.slot)
    elif contract == "canonical":
        report = validate_review_rows(rows, slot=args.slot)
        report["contract"] = "canonical"
    else:
        message = (
            "review artifact mixes sentence-centric v2 and canonical re-review identities"
            if rows
            else "unable to determine review artifact contract"
        )
        report = {
            "contract": "indeterminate",
            "slot": args.slot,
            "rows": len(rows),
            "reviewer_id": None,
            "reviewer_ids": [],
            "completed": 0,
            "unreviewed": 0,
            "issues": [
                {
                    "scope": f"review {args.slot.lower()}",
                    "code": "mixed_review_contract",
                    "message": message,
                }
            ],
            "ready": False,
            "_indexed": {},
        }
    report["issues"].extend(artifact_issues)
    report["issues"].sort(
        key=lambda item: (
            item.get("scope", ""),
            item.get("code", ""),
            item.get("case_id", item.get("sentence_oracle_id", "")),
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
    if contract == "v2":
        print(_v2_review_human(report))
    else:
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
    evidence = build_review_evidence(
        records,
        review_a,
        review_b,
        comparisons,
        decisions,
        records=updated,
    )
    write_review_evidence(Path(args.out_root) / "review-evidence.jsonl", evidence)
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


def cmd_adjudication_check(args):
    result = validate_adjudication_batch(
        read_records([args.candidates]),
        read_records([args.review_a]),
        read_records([args.review_b]),
        read_records([args.comparison]),
        read_records([args.decisions]),
        max_unresolved_percent=args.max_unresolved_percent,
    )
    if args.json:
        write_json(args.json, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ready"] else 1


def cmd_review_report(args):
    candidates = read_records([args.candidates])
    review_a = read_records([args.review_a])
    review_b = read_records([args.review_b])
    comparison = read_records([args.comparison])
    decisions = read_records([args.decisions])
    validation = validate_adjudication_batch(
        candidates,
        review_a,
        review_b,
        comparison,
        decisions,
    )
    output = render_review_html(
        args.out,
        candidates=candidates,
        review_a=review_a,
        review_b=review_b,
        comparisons=comparison,
        decisions=decisions,
        validation=validation,
        batch_id=args.batch_id,
    )
    print(f"wrote review report for {len(candidates)} candidates to {output}")
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
        conflict_adjudication_path=args.conflict_adjudication,
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


def cmd_agent_search(args):
    config_path = args.config if args.config is not None else default_config_path()
    config = load_config(config_path, explicit=args.config is not None)
    runtime = resolve_runtime_paths(config=config, source_cache=None, work_root=None)
    output = search_text(
        args.pattern,
        root=args.root,
        include_data=args.include_data,
        literal=args.literal,
        max_matches=args.max_matches,
        max_chars_per_line=args.max_chars_per_line,
        max_output=args.max_output,
        excluded_roots=[
            path
            for path in (runtime.work_root, runtime.source_cache)
            if path is not None
        ],
    )
    sys.stdout.write(output)
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
    corpus = repo_root / "data" / "corpus.jsonl"
    batches_root = paths.work_root / "batches" if paths.work_root else None
    reports_root = paths.work_root / "reports" if paths.work_root else None
    report = {
        "config": _path_info(config.path or config_path.resolve()),
        "repo_root": str(repo_root),
        "corpus": _path_info(corpus),
        "source_cache": _path_info(paths.source_cache),
        "work_root": _path_info(paths.work_root),
        "batches_root": _path_info(batches_root),
        "reports_root": _path_info(reports_root),
        "source_lock": _path_info(source_lock),
    }
    if args.json:
        write_json(args.json, report)
    print(f"repo_root: {repo_root}")
    print(f"corpus: {corpus}")
    for key in (
        "source_cache",
        "work_root",
        "batches_root",
        "reports_root",
        "source_lock",
    ):
        item = report[key]
        print(f"{key}: {item['path']}")
        print(f"{key}_exists: {'yes' if item['exists'] else 'no'}")
    return 0


def _resolve_batch_root(args) -> tuple[Path, Path | None]:
    config_path = args.config if args.config is not None else default_config_path()
    config = load_config(config_path, explicit=args.config is not None)
    runtime = resolve_runtime_paths(
        config=config,
        source_cache=None,
        work_root=getattr(args, "work_root", None),
    )
    requested = Path(args.batch).expanduser()
    if requested.exists():
        root = requested.resolve()
    elif runtime.work_root is not None:
        root = (runtime.work_root / "batches" / str(args.batch)).resolve()
    else:
        raise ConfigError(
            "batch path is not configured; use a batch root or configure the work root"
        )
    if not root.is_dir():
        raise ValueError(f"batch root not found: {root}")
    return root, runtime.work_root


def _jsonl_count(path: Path) -> int:
    return len(read_jsonl(path)) if path.is_file() else 0


def cmd_batch_status(args):
    root, work_root = _resolve_batch_root(args)
    batch_path = root / "batch.json"
    metadata = read_json(batch_path) if batch_path.is_file() else {}
    batch_id = metadata.get("batch_id") or root.name
    review_check_path = root / "review-check.json"
    review_check = read_json(review_check_path) if review_check_path.is_file() else {}
    decisions_path = root / "adjudicated.jsonl"
    decisions = read_jsonl(decisions_path) if decisions_path.is_file() else []
    decision_counts = {decision: 0 for decision in ("accept", "exclude", "unresolved")}
    for row in decisions:
        decision = row.get("decision")
        if decision in decision_counts:
            decision_counts[decision] += 1
    handoff_candidates = [root / "handoff.md"]
    if work_root is not None:
        handoff_candidates.append(work_root / f"{batch_id}-handoff.md")
    handoff = next((path for path in handoff_candidates if path.is_file()), None)
    integration = root / "integration.json"
    status = {
        "batch_id": batch_id,
        "root": str(root),
        "cases": _jsonl_count(root / "cases.jsonl"),
        "review_a": _jsonl_count(root / "a.complete.jsonl"),
        "review_b": _jsonl_count(root / "b.complete.jsonl"),
        "review_ready": bool(review_check.get("ready")),
        "review_issues": len(review_check.get("issues", []))
        if isinstance(review_check.get("issues", []), list)
        else 0,
        "adjudicated": len(decisions),
        **decision_counts,
        "integrated": bool(
            integration.is_file()
            and read_json(integration).get("state") == "integrated"
        ),
        "handoff": str(handoff) if handoff else None,
    }
    if args.json:
        write_json(args.json, status)
    for key, value in status.items():
        if key == "review_ready" or key == "integrated":
            value = "yes" if value else "no"
        print(f"{key}={value}")
    return 0


def cmd_trace_case(args):
    root, _work_root = _resolve_batch_root(args)
    cases_path = root / "cases.jsonl"
    for case in read_jsonl(cases_path):
        if case.get("case_id") == args.case_id:
            result = {
                "batch_id": root.name,
                "batch_root": str(root),
                "case_id": case.get("case_id"),
                "language": case.get("language"),
                "locale": case.get("locale"),
                "input": case.get("input"),
                "source_observation_count": len(case.get("source_observations", [])),
            }
            if args.json:
                write_json(args.json, case)
            print("case_id={case_id}".format(**result))
            print("batch_id={batch_id}".format(**result))
            print("language={language}".format(**result))
            print("locale={locale}".format(**result))
            print("input={input}".format(**result))
            print(
                "source_observation_count={source_observation_count}".format(**result)
            )
            return 0
    raise ValueError(f"case_id not found in {root}: {args.case_id}")


def _default_review_evidence_paths(
    repo_root: Path, work_root: Path | None
) -> list[Path]:
    roots = [repo_root]
    if work_root is not None:
        roots.append(work_root)
    paths: set[Path] = set()
    for root in roots:
        if root.exists():
            paths.update(root.rglob("review-evidence.jsonl"))
    return sorted(path for path in paths if path.is_file())


def _default_canonical_paths(repo_root: Path) -> list[Path]:
    corpus = repo_root / "data" / "corpus.jsonl"
    if corpus.exists():
        return [corpus]
    return [repo_root / "data" / name for name in ("train", "dev", "test")]


def cmd_trace_record(args):
    config_path = args.config if args.config is not None else default_config_path()
    config = load_config(config_path, explicit=args.config is not None)
    runtime = resolve_runtime_paths(
        config=config, source_cache=None, work_root=args.work_root
    )
    repo_root = (config.path.parent if config.path else Path.cwd()).resolve()
    record_paths = args.records or _default_canonical_paths(repo_root)
    records = read_records(record_paths)
    evidence_paths = (
        [Path(path) for path in args.evidence]
        if args.evidence
        else _default_review_evidence_paths(repo_root, runtime.work_root)
    )
    evidence = read_records(evidence_paths) if evidence_paths else []
    if not evidence:
        evidence = backfill_legacy_evidence(records)
    result = resolve_record_evidence(args.record_id, records, evidence)
    latest = max(
        result["evidence"], key=lambda row: row.get("review_revision", -1), default={}
    )
    result["evidence_paths"] = [str(path) for path in evidence_paths]
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    record = result["record"]
    decision = latest.get("decision", {}) if isinstance(latest, dict) else {}
    comparison = latest.get("comparison", {}) if isinstance(latest, dict) else {}
    print(f"record_id: {args.record_id}")
    print(f"family_id: {record.get('family_id', '')}")
    print(f"input: {record.get('input', '')}")
    print(
        f"canonical: {(record.get('oracle') or {}).get('canonical_output', record.get('expected_output'))}"
    )
    print(
        f"oracle_hash: {record.get('oracle_hash') or latest.get('final_oracle_hash', '')}"
    )
    print(f"review revisions: {result['review_revisions']}")
    if latest:
        print("latest review:")
        print(
            f"  reviewer_a: {(latest.get('review_a') or {}).get('reviewer_id', 'missing')}"
        )
        print(
            f"  reviewer_b: {(latest.get('review_b') or {}).get('reviewer_id', 'missing')}"
        )
        print(f"  adjudicator: {decision.get('adjudicator', 'missing')}")
        print(
            f"  A/B: {'disagreement' if comparison.get('disagreement') else 'agreement'}"
        )
        print(f"  decision: {decision.get('disposition', 'legacy')}")
    print(f"source_refs: {len(latest.get('source_refs', [])) if latest else 0}")
    print(f"evidence_files: {len(result['evidence_paths'])}")
    return 0


def _correction_inputs(args):
    config_path = args.config if args.config is not None else default_config_path()
    config = load_config(config_path, explicit=args.config is not None)
    runtime = resolve_runtime_paths(
        config=config, source_cache=None, work_root=getattr(args, "work_root", None)
    )
    repo_root = (config.path.parent if config.path else Path.cwd()).resolve()
    record_paths = args.records or _default_canonical_paths(repo_root)
    records = read_records(record_paths)
    evidence_paths = (
        [Path(path) for path in args.evidence]
        if args.evidence
        else _default_review_evidence_paths(repo_root, runtime.work_root)
    )
    evidence = read_records(evidence_paths) if evidence_paths else []
    if not evidence:
        evidence = backfill_legacy_evidence(records)
    return config, runtime, repo_root, records, evidence


def cmd_prepare_correction(args):
    _config, runtime, repo_root, records, evidence = _correction_inputs(args)
    record = next((row for row in records if row.get("id") == args.record_id), None)
    if record is None:
        raise ValueError(f"unknown canonical record id: {args.record_id}")
    if args.out_root:
        out_root = Path(args.out_root)
    elif runtime.work_root is not None:
        out_root = runtime.work_root / "corrections" / args.record_id
    else:
        raise ConfigError(
            "prepare-correction requires --out-root or a configured work root"
        )
    template = (repo_root / "templates" / "correction-task.md").read_text(
        encoding="utf-8"
    )
    paths = prepare_correction_context(record, evidence, out_root, template=template)
    for label, path in paths.items():
        print(f"{label}: {path}")
    return 0


def cmd_apply_correction(args):
    _config, runtime, _repo_root, records, evidence = _correction_inputs(args)
    correction = read_json(args.correction)
    original = next((row for row in records if row.get("id") == args.record_id), None)
    if original is None:
        raise ValueError(f"unknown canonical record id: {args.record_id}")
    updated, history_item = apply_correction(original, correction)
    if args.out_root:
        out_root = Path(args.out_root)
    elif runtime.work_root is not None:
        out_root = runtime.work_root / "corrections" / args.record_id / "applied"
    else:
        raise ConfigError(
            "apply-correction requires --out-root or a configured work root"
        )
    paths = write_correction_application(
        out_root, records, updated, history_item, evidence
    )
    print(f"Corrected {args.record_id}.")
    print(f"Old oracle hash: {history_item['old_oracle_hash']}")
    print(f"New oracle hash: {history_item['new_oracle_hash']}")
    print(f"Preview: {paths['report']}#record={args.record_id}")
    return 0


def _packet_output_summary(path: Path, rows: list[dict]) -> None:
    size = sum(serialized_row_bytes(row) for row in rows)
    print(f"packet={path} cases={len(rows)} bytes={size}")


def cmd_review_packet(args):
    root, _work_root = _resolve_batch_root(args)
    blind_path = root / f"{'a' if args.slot == 'A' else 'b'}.blind.jsonl"
    completed = (
        read_records([args.completed])
        if args.completed and Path(args.completed).is_file()
        else []
    )
    rows = review_packet_rows(
        read_records([blind_path]),
        completed,
        max_cases=args.max_cases,
        max_bytes=args.max_bytes,
    )
    output = Path(args.out)
    write_jsonl(output, rows)
    _packet_output_summary(output, rows)
    return 0


def cmd_review_merge(args):
    root, _work_root = _resolve_batch_root(args)
    blind_path = root / f"{'a' if args.slot == 'A' else 'b'}.blind.jsonl"
    existing_path = (
        Path(args.completed)
        if args.completed
        else root / f"{args.slot.lower()}.complete.jsonl"
    )
    existing = read_records([existing_path]) if existing_path.is_file() else []
    rows = merge_review_rows(
        read_records([blind_path]),
        existing,
        read_records([args.packet_result]),
        slot=args.slot,
        output=args.out,
    )
    print(
        f"merged={args.out} completed={len(rows)} remaining={len(read_records([blind_path])) - len(rows)}"
    )
    return 0


def cmd_adjudication_packet(args):
    root, _work_root = _resolve_batch_root(args)
    cases = read_records([root / "cases.jsonl"])
    review_a = read_records([args.review_a])
    review_b = read_records([args.review_b])
    review_report = check_reviews(cases, review_a, review_b)
    if not review_report["ready"]:
        raise ValueError("review-check failed: " + "; ".join(review_report["issues"]))
    context_path = root / "context.jsonl"
    contexts = read_records([context_path]) if context_path.is_file() else cases
    decisions = (
        read_records([args.decisions])
        if args.decisions and Path(args.decisions).is_file()
        else []
    )
    rows = adjudication_packet_rows(
        cases,
        contexts,
        review_a,
        review_b,
        decisions,
        max_cases=args.max_cases,
        max_bytes=args.max_bytes,
    )
    output = Path(args.out)
    write_jsonl(output, rows)
    _packet_output_summary(output, rows)
    return 0


def cmd_adjudication_merge(args):
    root, _work_root = _resolve_batch_root(args)
    existing_path = (
        Path(args.decisions) if args.decisions else root / "adjudicated.partial.jsonl"
    )
    existing = read_records([existing_path]) if existing_path.is_file() else []
    merged = merge_adjudication_rows(existing, read_records([args.packet_result]))
    if args.finalize:
        merged = finalize_adjudication(
            read_records([root / "cases.jsonl"]),
            merged,
        )
    write_jsonl(args.out, merged)
    if args.finalize:
        finalized = finalize_adjudication(
            read_records([root / "cases.jsonl"]), merged, output=args.out
        )
        merged = finalized
    print(f"merged={args.out} decisions={len(merged)}")
    return 0


def cmd_collect(args):
    observations = args.observations or sorted(Path("data/candidates").glob("*.jsonl"))
    reviewed = args.reviewed or (
        ["data/corpus.jsonl"] if Path("data/corpus.jsonl").exists() else []
    )
    result = collect_batch(
        observations,
        reviewed_paths=reviewed,
        exclusion_paths=args.exclusions or [],
        output_root=args.out_root,
        batch_id=args.batch,
        limit=args.limit,
        source_lock_hash=args.source_lock_hash,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


def cmd_review_check(args):
    result = check_reviews(
        read_records([args.batch / "cases.jsonl"]),
        read_records([args.review_a]),
        read_records([args.review_b]),
    )
    if args.json:
        write_json(args.json, result)
    if result["ready"]:
        print(
            f"ready=yes cases={result['cases']} "
            f"a_rows={result['review_a']['rows']} "
            f"b_rows={result['review_b']['rows']} issues=0"
        )
        print(f"reviewer_a={result['review_a']['reviewer_id']}")
        print(f"reviewer_b={result['review_b']['reviewer_id']}")
    else:
        issues = result["issues"]
        print(f"ready=no issues={len(issues)}")
        print("first_issues:")
        for issue in issues[:20]:
            print(f"  {issue}")
        if args.json:
            print(f"details={args.json}")
    return 0 if result["ready"] else 2


def cmd_integrate(args):
    result = integrate_batch(args.batch, args.corpus, write=args.write)
    print(
        f"ready=yes records={result['records']} "
        f"excluded={len(result['excluded'])} "
        f"synthetic_candidates={len(result['synthetic_candidates'])}"
    )
    return 0


def cmd_report(args):
    records = read_records(
        args.records
        or (["data/corpus.jsonl"] if Path("data/corpus.jsonl").exists() else [])
    )
    errors = validate_records(records)
    if errors:
        raise ValueError("cannot report invalid corpus: " + "; ".join(errors))
    targets = (
        load_targets(args.targets)
        if args.targets
        else load_targets("taxonomy/coverage_targets.json")
    )
    coverage = build_coverage(records, targets)
    counts = {
        "records": len(records),
        "families": len({row.get("family_id") for row in records}),
    }
    output = render_release_html(
        args.out,
        version=args.version,
        maturity="corpus",
        records=records,
        coverage=coverage,
        control_coverage={},
        counts=counts,
    )
    print(f"wrote corpus report for {len(records)} records to {output}")
    return 0


def cmd_export(args):
    records = read_records(args.records or ["data/corpus.jsonl"])
    result = export_family_safe_splits(
        records,
        out_root=args.out_root,
        seed=args.seed,
        ratios=(args.train, args.dev, args.test),
    )
    print(" ".join(f"{name}={len(rows)}" for name, rows in result.items()))
    return 0


def cmd_benchmark(args):
    from .benchmark import run_benchmark

    summary = run_benchmark(
        gold_root=args.gold_root,
        split=args.split,
        results_dir=args.results_dir,
        prepare_module=args.prepare_module,
        mode=args.mode,
    )
    print(
        json.dumps(
            {
                "records": summary["record_count"],
                "results_dir": str(args.results_dir),
                "split": args.split,
            },
            ensure_ascii=False,
        )
    )
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
    validate.add_argument("paths", nargs="*")
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
    validate_review.add_argument(
        "--contract",
        choices=["auto", "v2", "canonical"],
        default="auto",
        help="Review contract to validate; auto detects v2 or canonical artifacts.",
    )
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
    adjudication_check = sub.add_parser("adjudication-check")
    adjudication_check.add_argument("--candidates", required=True)
    adjudication_check.add_argument("--review-a", required=True)
    adjudication_check.add_argument("--review-b", required=True)
    adjudication_check.add_argument("--comparison", required=True)
    adjudication_check.add_argument("--decisions", required=True)
    adjudication_check.add_argument("--max-unresolved-percent", type=float)
    adjudication_check.add_argument("--json")
    adjudication_check.set_defaults(func=cmd_adjudication_check)
    review_report = sub.add_parser("review-report")
    review_report.add_argument("--candidates", required=True)
    review_report.add_argument("--review-a", required=True)
    review_report.add_argument("--review-b", required=True)
    review_report.add_argument("--comparison", required=True)
    review_report.add_argument("--decisions", required=True)
    review_report.add_argument("--out", required=True)
    review_report.add_argument("--batch-id")
    review_report.set_defaults(func=cmd_review_report)

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
    release.add_argument("--conflict-adjudication")
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
    agent_search = sub.add_parser("agent-search")
    agent_search.add_argument("pattern")
    agent_search.add_argument("--root", type=Path, default=Path.cwd())
    agent_search.add_argument("--include-data", action="store_true")
    agent_search.add_argument("--literal", action="store_true")
    agent_search.add_argument("--max-matches", type=int, default=DEFAULT_MAX_MATCHES)
    agent_search.add_argument(
        "--max-chars-per-line", type=int, default=DEFAULT_MAX_CHARS_PER_LINE
    )
    agent_search.add_argument("--max-output", type=int, default=DEFAULT_MAX_OUTPUT)
    agent_search.set_defaults(func=cmd_agent_search)
    batch_status = sub.add_parser("batch-status")
    batch_status.add_argument("--batch", required=True)
    batch_status.add_argument("--work-root", type=Path)
    batch_status.add_argument("--json")
    batch_status.set_defaults(func=cmd_batch_status)
    trace_case = sub.add_parser("trace-case")
    trace_case.add_argument("case_id")
    trace_case.add_argument("--batch", required=True)
    trace_case.add_argument("--work-root", type=Path)
    trace_case.add_argument("--json")
    trace_case.set_defaults(func=cmd_trace_case)
    doctor = sub.add_parser("doctor", aliases=["paths"])
    doctor.add_argument("--json")
    doctor.set_defaults(func=cmd_doctor)
    trace = sub.add_parser("trace-record")
    trace.add_argument("record_id")
    trace.add_argument("--records", nargs="+")
    trace.add_argument("--evidence", nargs="+")
    trace.add_argument("--work-root", type=Path)
    trace.add_argument("--json", action="store_true")
    trace.set_defaults(func=cmd_trace_record)
    prepare_correction = sub.add_parser("prepare-correction")
    prepare_correction.add_argument("record_id")
    prepare_correction.add_argument("--records", nargs="+")
    prepare_correction.add_argument("--evidence", nargs="+")
    prepare_correction.add_argument("--work-root", type=Path)
    prepare_correction.add_argument("--out-root", type=Path)
    prepare_correction.set_defaults(func=cmd_prepare_correction)
    apply_correction = sub.add_parser("apply-correction")
    apply_correction.add_argument("record_id")
    apply_correction.add_argument("--correction", required=True)
    apply_correction.add_argument("--records", nargs="+")
    apply_correction.add_argument("--evidence", nargs="+")
    apply_correction.add_argument("--work-root", type=Path)
    apply_correction.add_argument("--out-root", type=Path)
    apply_correction.set_defaults(func=cmd_apply_correction)
    collect = sub.add_parser("collect")
    collect.add_argument("--observations", nargs="+")
    collect.add_argument("--reviewed", nargs="+")
    collect.add_argument("--exclusions", nargs="+")
    collect.add_argument("--limit", type=int, default=DEFAULT_V2_COLLECTION_LIMIT)
    collect.add_argument("--batch", required=True)
    collect.add_argument("--out-root", type=Path, required=True)
    collect.add_argument("--source-lock-hash")
    collect.set_defaults(func=cmd_collect)
    review_packet = sub.add_parser("review-packet")
    review_packet.add_argument("--batch", required=True)
    review_packet.add_argument("--slot", choices=["A", "B"], required=True)
    review_packet.add_argument("--completed", type=Path)
    review_packet.add_argument("--max-cases", type=int, default=200)
    review_packet.add_argument("--max-bytes", type=int, default=98304)
    review_packet.add_argument("--out", type=Path, required=True)
    review_packet.add_argument("--work-root", type=Path)
    review_packet.set_defaults(func=cmd_review_packet)
    review_merge = sub.add_parser("review-merge")
    review_merge.add_argument("--batch", required=True)
    review_merge.add_argument("--slot", choices=["A", "B"], required=True)
    review_merge.add_argument("--packet-result", type=Path, required=True)
    review_merge.add_argument("--completed", type=Path)
    review_merge.add_argument("--out", type=Path, required=True)
    review_merge.add_argument("--work-root", type=Path)
    review_merge.set_defaults(func=cmd_review_merge)
    adjudication_packet = sub.add_parser("adjudication-packet")
    adjudication_packet.add_argument("--batch", required=True)
    adjudication_packet.add_argument("--review-a", type=Path, required=True)
    adjudication_packet.add_argument("--review-b", type=Path, required=True)
    adjudication_packet.add_argument("--decisions", type=Path)
    adjudication_packet.add_argument("--max-cases", type=int, default=100)
    adjudication_packet.add_argument("--max-bytes", type=int, default=98304)
    adjudication_packet.add_argument("--out", type=Path, required=True)
    adjudication_packet.add_argument("--work-root", type=Path)
    adjudication_packet.set_defaults(func=cmd_adjudication_packet)
    adjudication_merge = sub.add_parser(
        "adjudication-merge", aliases=["adjudication-finalize"]
    )
    adjudication_merge.add_argument("--batch", required=True)
    adjudication_merge.add_argument("--packet-result", type=Path, required=True)
    adjudication_merge.add_argument("--decisions", type=Path)
    adjudication_merge.add_argument("--out", type=Path, required=True)
    adjudication_merge.add_argument("--finalize", action="store_true")
    adjudication_merge.add_argument("--work-root", type=Path)
    adjudication_merge.set_defaults(func=cmd_adjudication_merge)
    review_check = sub.add_parser("review-check")
    review_check.add_argument("--batch", type=Path, required=True)
    review_check.add_argument("--review-a", type=Path, required=True)
    review_check.add_argument("--review-b", type=Path, required=True)
    review_check.add_argument("--json")
    review_check.set_defaults(func=cmd_review_check)
    integrate = sub.add_parser("integrate")
    integrate.add_argument("--batch", type=Path, required=True)
    integrate.add_argument("--corpus", type=Path, default=Path("data/corpus.jsonl"))
    integrate.add_argument("--write", action="store_true")
    integrate.set_defaults(func=cmd_integrate)
    report = sub.add_parser("report")
    report.add_argument("--records", nargs="*")
    report.add_argument("--out", required=True)
    report.add_argument("--targets")
    report.add_argument("--version", default="corpus")
    report.set_defaults(func=cmd_report)
    export = sub.add_parser("export")
    export.add_argument("--records", nargs="*")
    export.add_argument("--out-root", type=Path, required=True)
    export.add_argument("--seed", default="spokenform-gold-v2")
    export.add_argument("--train", type=float, default=0.70)
    export.add_argument("--dev", type=float, default=0.15)
    export.add_argument("--test", type=float, default=0.15)
    export.set_defaults(func=cmd_export)
    release_v2 = sub.add_parser("release")
    release_v2.add_argument("--version", required=True)
    release_v2.add_argument("--data", nargs="+", default=["data/corpus.jsonl"])
    release_v2.add_argument("--out", required=True)
    release_v2.add_argument(
        "--maturity",
        choices=["experimental", "candidate", "stable"],
        default="experimental",
    )
    release_v2.add_argument("--registry")
    release_v2.add_argument("--source-manifest")
    release_v2.add_argument("--coverage-profile", default="none")
    release_v2.add_argument("--controls", nargs="+")
    release_v2.add_argument("--conflict-adjudication")
    release_v2.set_defaults(func=cmd_release_check)
    benchmark = sub.add_parser("benchmark")
    benchmark.add_argument("--gold-root", required=True)
    benchmark.add_argument("--split")
    benchmark.add_argument("--prepare-module", required=True)
    benchmark.add_argument("--results-dir", required=True)
    benchmark.add_argument(
        "--mode", choices=["canonical", "accepted"], default="canonical"
    )
    benchmark.set_defaults(func=cmd_benchmark)
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
            "prepare-correction",
            "apply-correction",
        }
        if args.cmd not in workflow_commands or args.debug:
            raise
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
