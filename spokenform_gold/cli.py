from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .adjudication import build_adjudication_queue
from .adjudication_quality import validate_adjudication_batch
from .campaign import campaign_finalize, campaign_next, campaign_status, create_campaign
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
from .corpus import canonical_corpus_path, shard_corpus
from .corpus_site import DEFAULT_ISSUES_URL, generate_corpus_site
from .corpus_status import build_corpus_status
from .corrections import (
    apply_correction,
    apply_correction_to_corpus,
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
from .ingestion import (
    DEFAULT_INGEST_LANGUAGES,
    prepare_observations,
    run_upstream_ingestion,
)
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
from .migration import (
    classify_work_root,
    migrate_jsonl,
    migrate_work_root,
)
from .oracle_diff import diff_records
from .packets import (
    adjudication_packet_rows,
    adjudication_repair_packet_rows,
    finalize_adjudication,
    merge_adjudication_repairs,
    merge_adjudication_rows,
    merge_review_rows,
    review_packet_rows,
    serialized_row_bytes,
)
from .pool import build_candidate_pool_summary
from .promotion import build_promoted_records
from .ranking import build_candidate_ranking, export_review_batch
from .release import build_release, build_release_preflight
from .rereview import (
    REVIEW_BATCH_LIMIT,
    build_rereview_batch,
    load_retry_pool,
    migrate_legacy_adjudication,
    rebuild_retry_pool,
    retry_pool_summary,
    select_retry_cases,
    write_retry_pool_atomic,
)
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
    find_evidence_conflicts,
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
from .source_manifest import (
    build_source_materialization_census,
    load_and_validate_source_manifest,
    referenced_source_names,
)
from .source_policy import (
    apply_source_decision,
    build_source_policy_packet,
    build_source_policy_status,
    source_manifest_hash,
    validate_source_decision,
)
from .splitting import split_records
from .stats import build_stats
from .translation import (
    check_translation_batch,
    finalize_translations,
    merge_translation_adjudication_rows,
    merge_translation_rows,
    prepare_translation_batch,
    translation_adjudication_packet_rows,
    translation_packet_rows,
    validate_target_locale,
)
from .validation import load_categories, validate_corpus, validate_records
from .work_layout import BatchLayout, WorkLayout
from .workflow import (
    batch_preflight,
    check_reviews,
    finalize_batch,
    integrate_batch,
    integration_matches_current,
)


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


def _canonical_cli_records(args):
    paths = args.records or [canonical_corpus_path()]
    if len(paths) == 1 and Path(paths[0]).is_dir():
        errors = validate_corpus(paths[0])
    else:
        errors = validate_records(read_records(paths))
    records = read_records(paths)
    if errors:
        raise ValueError("canonical corpus validation failed: " + "; ".join(errors))
    return records


def cmd_corpus_status(args):
    records = _canonical_cli_records(args)
    manifest_path = Path(args.source_manifest)
    source_manifest = (
        load_and_validate_source_manifest(
            manifest_path,
            repo_root=Path.cwd(),
            source_names=referenced_source_names(records),
        )
        if manifest_path.is_file()
        else {"sources": []}
    )
    preflight = read_json(args.preflight) if args.preflight else None
    partition = (
        {
            "embedded": preflight.get("embedded", 0),
            "external_ref": preflight.get("external_ref", 0),
            "blocked": preflight.get("blocked", 0),
            "blockers": preflight.get("blockers", {}),
        }
        if preflight
        else None
    )
    result = build_corpus_status(
        records,
        source_manifest=source_manifest,
        retry_backlog=args.retry_backlog,
        release_partition=partition,
    )
    if args.json:
        write_json(args.json, result)
    for key in (
        "canonical",
        "review_complete",
        "review_gaps",
        "retry_backlog",
        "release_embedded",
        "release_external_ref",
        "release_blocked",
        "local_benchmark_records",
    ):
        print(f"{key}={result[key]}")
    return 0


def _campaign_work_root(args):
    return args.work_root if args.work_root else None


def cmd_campaign_create(args):
    metadata = create_campaign(
        args.campaign,
        work_root=_campaign_work_root(args),
        batch_size=args.batch_size,
        batch_roots=args.batches,
    )
    print(
        f"campaign={metadata['campaign_id']} batches={len(metadata['batches'])} batch_size={metadata['batch_size']}"
    )
    return 0


def cmd_campaign_status(args):
    result = campaign_status(args.campaign, work_root=_campaign_work_root(args))
    if args.json:
        write_json(args.json, result)
    totals = result["totals"]
    print(
        "campaign={} batches={} cases={} review_ready={} finalized={} complete={}".format(
            result["campaign_id"],
            totals["batches"],
            totals["cases"],
            totals["review_ready"],
            totals["finalized"],
            "yes" if result["complete"] else "no",
        )
    )
    return 0


def cmd_campaign_next(args):
    result = campaign_next(
        args.campaign, args.role, work_root=_campaign_work_root(args), out=args.out
    )
    if result is None:
        print(f"campaign={args.campaign} role={args.role} packet=none")
        return 0
    print(
        f"campaign={result['campaign_id']} role={result['role']} batch={result['batch_id']} cases={result['cases']} packet={result['packet']} template={result['template']}"
    )
    return 0


def cmd_campaign_finalize(args):
    result = campaign_finalize(
        args.campaign,
        corpus=args.corpus,
        retry_pool=args.retry_pool,
        work_root=_campaign_work_root(args),
        write=args.write,
    )
    print(
        f"campaign={result['campaign_id']} finalized={result['finalized']} write={'yes' if args.write else 'no'}"
    )
    return 0


def _source_policy_inputs(args):
    records = read_records(args.records or [canonical_corpus_path()])
    manifest_path = Path(args.source_manifest)
    manifest = load_and_validate_source_manifest(
        manifest_path,
        repo_root=Path.cwd(),
        source_names=referenced_source_names(records),
    )
    decisions = read_json(args.decisions) if getattr(args, "decisions", None) else None
    return records, manifest, manifest_path, decisions


def cmd_source_policy_status(args):
    records, manifest, _path, decisions = _source_policy_inputs(args)
    result = build_source_policy_status(records, manifest, decisions)
    if args.out:
        write_json(args.out, result)
    print(
        "sources={} {}".format(
            result["source_count"],
            " ".join(f"{key}={value}" for key, value in result["counts"].items()),
        )
    )
    return 0


def cmd_source_policy_packet(args):
    records, manifest, _path, _decisions = _source_policy_inputs(args)
    packet = build_source_policy_packet(args.source, args.slot, records, manifest)
    write_json(args.out, packet)
    print(
        f"source={args.source} slot={args.slot} records={sum(row.get('records', 0) for row in packet['source_census'])} packet={args.out}"
    )
    return 0


def cmd_source_policy_review_merge(args):
    packet = read_json(args.packet)
    result = read_json(args.result)
    if (
        not isinstance(result, dict)
        or not result.get("reviewer_id")
        or not result.get("result")
    ):
        raise ValueError("source-policy review result requires reviewer_id and result")
    output = {
        "schema_version": "1.0.0",
        "source": packet["source"]["name"],
        "manifest_hash": packet["manifest_hash"],
        "slot": packet["slot"],
        **result,
    }
    write_json(args.out, output)
    print(f"merged source-policy review for {output['source']} slot={output['slot']}")
    return 0


def cmd_source_policy_check(args):
    _records, manifest, _path, decisions = _source_policy_inputs(args)
    rows = (
        decisions
        if isinstance(decisions, list)
        else (decisions or {}).get("decisions", [])
        if isinstance(decisions, dict)
        else []
    )
    source_map = {row.get("name"): row for row in manifest.get("sources", [])}
    errors = []
    for decision in rows:
        source = source_map.get(decision.get("source"))
        if source is None:
            errors.append(f"unknown source: {decision.get('source')}")
            continue
        errors.extend(
            f"{decision.get('source')}: {error}"
            for error in validate_source_decision(
                decision,
                source,
                manifest_hash=source_manifest_hash(manifest),
                repo_root=Path.cwd(),
            )
        )
    result = {
        "manifest_hash": source_manifest_hash(manifest),
        "decisions": len(rows),
        "ready": not errors,
        "errors": sorted(errors),
    }
    if args.out:
        write_json(args.out, result)
    print(
        f"decisions={result['decisions']} ready={'yes' if result['ready'] else 'no'} errors={len(errors)}"
    )
    return 0 if result["ready"] else 1


def cmd_source_policy_adjudication_packet(args):
    packet = read_json(args.packet)
    review_a = read_json(args.review_a)
    review_b = read_json(args.review_b)
    if review_a.get("source") != review_b.get("source") or review_a.get(
        "manifest_hash"
    ) != review_b.get("manifest_hash"):
        raise ValueError(
            "source-policy reviews do not describe the same source snapshot"
        )
    write_json(
        args.out,
        {
            "schema_version": "1.0.0",
            "packet_kind": "source_policy_adjudication",
            "source": packet["source"],
            "manifest_hash": packet["manifest_hash"],
            "review_a": review_a,
            "review_b": review_b,
        },
    )
    print(f"source={packet['source']['name']} adjudication_packet={args.out}")
    return 0


def cmd_source_policy_adjudication_merge(args):
    packet = read_json(args.packet)
    result = read_json(args.result)
    if result.get("decision") not in {
        "embedded_public",
        "external_ref_only",
        "exclude_public",
        "needs_human_legal_review",
    }:
        raise ValueError("invalid source-policy adjudication decision")
    output = {
        "schema_version": "1.0.0",
        "source": packet["source"]["name"],
        "source_revision": packet["source"].get("revision"),
        "manifest_hash": packet["manifest_hash"],
        **result,
    }
    write_json(args.out, output)
    print(f"merged source-policy adjudication for {output['source']}")
    return 0


def cmd_source_policy_apply(args):
    decision = read_json(args.decision)
    if isinstance(decision, dict) and isinstance(decision.get("decisions"), list):
        if len(decision["decisions"]) != 1:
            raise ValueError("source-policy-apply requires exactly one decision")
        decision = decision["decisions"][0]
    updated = apply_source_decision(args.source_manifest, decision, write=args.write)
    print(
        f"source={decision['source']} release_ready={next(row for row in updated['sources'] if row['name'] == decision['source'])['release_ready']} written={'yes' if args.write else 'no'}"
    )
    return 0


def cmd_release_preflight(args):
    result = build_release_preflight(
        data_paths=args.data,
        source_manifest_path=args.source_manifest,
        source_decisions_path=args.source_decisions,
        release_sources=args.release_sources,
    )
    write_json(args.out, result)
    print(
        "canonical={canonical_records} embedded={embedded} "
        "external_ref={external_ref} blocked={blocked} accounted={accounted}".format(
            **result
        )
    )
    if result["blockers"]:
        print("blockers=" + json.dumps(result["blockers"], sort_keys=True))
    return 0 if result["ready"] else 1


def cmd_migrate_oracle(args):
    count = migrate_jsonl(args.input, args.out)
    print(f"migrated {count} records to {args.out}")
    return 0


def cmd_shard_corpus(args):
    count = shard_corpus(args.input, args.out)
    print(f"sharded {count} records into {args.out}")
    return 0


def cmd_validate(args):
    if not args.paths:
        canonical = canonical_corpus_path()
        legacy = canonical.with_suffix(".jsonl")
        args.paths = (
            [canonical]
            if canonical.exists()
            else [legacy]
            if legacy.exists()
            else [Path("data/train"), Path("data/dev"), Path("data/test")]
        )
    categories = load_categories(args.categories) if args.categories else None
    if len(args.paths) == 1 and Path(args.paths[0]).is_dir():
        errors = validate_corpus(args.paths[0], judge=args.judge, categories=categories)
        records = read_records([args.paths[0]])
    else:
        records = read_records(args.paths)
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
    result = build_coverage(
        records, load_targets(args.targets, profile=args.language_profile)
    )
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


def cmd_source_census(args):
    records = read_records(args.records)
    manifest = load_and_validate_source_manifest(
        args.source_manifest,
        repo_root=Path.cwd(),
        source_names=referenced_source_names(records),
    )
    census = build_source_materialization_census(records, manifest)
    if args.out:
        write_json(args.out, census)
    print("source materialization census")
    print(
        "benchmark | source_version | materialization | records | unique_source_ids | policy | release_ready"
    )
    for row in census["groups"]:
        print(
            "{benchmark} | {source_version} | {materialization} | {records} | "
            "{unique_source_ids} | {manifest_policy} | {release_ready}".format(**row)
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


def _translation_target(value: str) -> tuple[str, str]:
    language, separator, locale_tail = value.partition("-")
    locale = f"{language}-{locale_tail}" if separator else ""
    validate_target_locale(language, locale)
    return language, locale


def cmd_translation_prepare(args):
    language, locale = _translation_target(args.target)
    records = read_records(args.records)
    if args.limit is not None:
        records = records[: args.limit]
    result = prepare_translation_batch(
        records,
        args.out_root,
        target_language=language,
        target_locale=locale,
        batch_id=args.batch,
        requested_mode=args.mode.replace("-", "_"),
    )
    print(f"prepared {result['case_count']} translation cases under {args.out_root}")
    return 0


def _translation_root(path: str | Path) -> Path:
    root = Path(path)
    if not root.is_dir():
        raise ValueError(f"translation batch is not a directory: {root}")
    return root


def cmd_translation_packet(args):
    root = _translation_root(args.batch)
    blind_path = root / f"{args.slot.lower()}.blind.jsonl"
    completed_path = (
        Path(args.completed)
        if args.completed
        else root / f"{args.slot.lower()}.complete.jsonl"
    )
    completed = read_records([completed_path]) if completed_path.is_file() else []
    rows = translation_packet_rows(
        read_records([blind_path]),
        completed,
        max_cases=args.max_cases,
        max_bytes=args.max_bytes,
    )
    write_jsonl(args.out, rows)
    print(f"wrote {len(rows)} translation packet rows to {args.out}")
    return 0


def cmd_translation_merge(args):
    root = _translation_root(args.batch)
    blind_path = (
        Path(args.blind) if args.blind else root / f"{args.slot.lower()}.blind.jsonl"
    )
    blind = read_records([blind_path])
    existing_path = (
        Path(args.existing)
        if args.existing
        else root / f"{args.slot.lower()}.complete.partial.jsonl"
    )
    existing = read_records([existing_path]) if existing_path.is_file() else []
    rows = merge_translation_rows(
        blind, existing, read_records([args.results]), slot=args.slot, output=args.out
    )
    print(f"merged={args.out} translations={len(rows)}")
    return 0


def cmd_translation_check(args):
    root = _translation_root(args.batch)
    report = check_translation_batch(
        read_records([root / "tasks.jsonl"]),
        read_records([args.translation_a]),
        read_records([args.translation_b]),
    )
    if args.json:
        write_json(args.json, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ready"] else 1


def cmd_translation_adjudication_packet(args):
    root = _translation_root(args.batch)
    rows = translation_adjudication_packet_rows(
        read_records([root / "tasks.jsonl"]),
        read_records([args.translation_a]),
        read_records([args.translation_b]),
        read_records([args.decisions]) if args.decisions else [],
        max_cases=args.max_cases,
        max_bytes=args.max_bytes,
    )
    write_jsonl(args.out, rows)
    print(f"wrote {len(rows)} translation adjudication rows to {args.out}")
    return 0


def cmd_translation_adjudication_merge(args):
    root = _translation_root(args.batch)
    existing_path = (
        Path(args.decisions) if args.decisions else root / "adjudicated.partial.jsonl"
    )
    existing = read_records([existing_path]) if existing_path.is_file() else []
    rows = merge_translation_adjudication_rows(
        existing, read_records([args.packet_result]), output=args.out
    )
    print(f"merged={args.out} decisions={len(rows)}")
    return 0


def cmd_translation_finalize(args):
    root = _translation_root(args.batch)
    candidates = finalize_translations(
        read_records([root / "tasks.jsonl"]),
        read_records([args.translation_a]),
        read_records([args.translation_b]),
        read_records([args.decisions]),
        output=args.out,
    )
    print(f"wrote {len(candidates)} translation candidate observations to {args.out}")
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
        release_sources=getattr(args, "release_sources", None),
        source_decisions_path=getattr(args, "source_decisions", None),
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
    corpus = canonical_corpus_path(repo_root)
    batches_root = paths.work_root / "batches" if paths.work_root else None
    reports_root = paths.work_root / "reports" if paths.work_root else None
    lineage = _canonical_lineage_path(repo_root)
    report = {
        "config": _path_info(config.path or config_path.resolve()),
        "repo_root": str(repo_root),
        "corpus": _path_info(corpus),
        "lineage": _path_info(lineage),
        "source_cache": _path_info(paths.source_cache),
        "work_root": _path_info(paths.work_root),
        "batches_root": _path_info(batches_root),
        "reports_root": _path_info(reports_root),
        "source_lock": _path_info(source_lock),
    }
    if corpus.is_dir():
        try:
            records = read_records([corpus])
            manifest_path = repo_root / "sources" / "manifest.json"
            source_manifest = (
                load_and_validate_source_manifest(
                    manifest_path,
                    repo_root=repo_root,
                    source_names=referenced_source_names(records),
                )
                if manifest_path.is_file()
                else {"sources": []}
            )
            report["corpus_status"] = build_corpus_status(
                records, source_manifest=source_manifest
            )
        except (OSError, TypeError, ValueError) as exc:
            report["corpus_status_error"] = str(exc)
    if args.json:
        write_json(args.json, report)
    print(f"repo_root: {repo_root}")
    print(f"corpus: {corpus}")
    if "corpus_status" in report:
        status = report["corpus_status"]
        print(
            "canonical_status: canonical={} review_complete={} review_gaps={} local_benchmark={}".format(
                status["canonical"],
                status["review_complete"],
                status["review_gaps"],
                status["local_benchmark_records"],
            )
        )
    for key in (
        "lineage",
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


def _work_root_from_args(args) -> Path:
    config_path = args.config if args.config is not None else default_config_path()
    config = load_config(config_path, explicit=args.config is not None)
    runtime = resolve_runtime_paths(
        config=config, source_cache=None, work_root=args.work_root
    )
    if runtime.work_root is None:
        raise ConfigError("work root is not configured; use --work-root or config.toml")
    return runtime.work_root


def cmd_work_status(args):
    report = classify_work_root(_work_root_from_args(args))
    for section in ("batches", "corrections", "legacy", "loose_artifacts"):
        print(f"{section}:")
        for item in report[section]:
            if isinstance(item, dict):
                values = " ".join(
                    f"{key}={value}" for key, value in item.items() if key != "root"
                )
                print(f"  {values}")
            else:
                print(f"  {item}")
    return 0


def cmd_work_migrate(args):
    root = _work_root_from_args(args)
    actions = migrate_work_root(root, apply=args.apply)
    for action in actions:
        print(f"{action['action']}: {action['source']} -> {action['target']}")
    if not actions:
        print("no migration actions")
    return 0


def cmd_batch_status(args):
    root, work_root = _resolve_batch_root(args)
    layout = BatchLayout(root)
    metadata = read_json(layout.metadata) if layout.metadata.is_file() else {}
    batch_id = metadata.get("batch_id") or root.name
    review_check_path = (
        layout.review_check
        if layout.review_check.is_file()
        else root / "review-check.json"
    )
    review_check = read_json(review_check_path) if review_check_path.is_file() else {}
    decisions_path = (
        layout.adjudication_decisions
        if layout.adjudication_decisions.is_file()
        else root / "adjudicated.jsonl"
    )
    decisions = read_jsonl(decisions_path) if decisions_path.is_file() else []
    decision_counts = {decision: 0 for decision in ("accept", "exclude", "unresolved")}
    for row in decisions:
        decision = row.get("decision")
        if decision in decision_counts:
            decision_counts[decision] += 1
    handoff_candidates = [layout.handoff]
    if work_root is not None:
        handoff_candidates.append(work_root / f"{batch_id}-handoff.md")
    handoff = next((path for path in handoff_candidates if path.is_file()), None)
    cases_path = layout.cases if layout.cases.is_file() else root / "cases.jsonl"
    review_a_path = (
        layout.review_complete("A")
        if layout.review_complete("A").is_file()
        else root / "a.complete.jsonl"
    )
    review_b_path = (
        layout.review_complete("B")
        if layout.review_complete("B").is_file()
        else root / "b.complete.jsonl"
    )
    accounting = metadata.get("accounting", {})
    status = {
        "batch_id": batch_id,
        "root": str(root),
        "state": metadata.get("state"),
        "cases": _jsonl_count(cases_path),
        "review_a": _jsonl_count(review_a_path),
        "review_b": _jsonl_count(review_b_path),
        "review_ready": bool(review_check.get("ready")),
        "review_issues": len(review_check.get("issues", []))
        if isinstance(review_check.get("issues", []), list)
        else 0,
        "adjudicated": len(decisions),
        **decision_counts,
        "integrated": integration_matches_current(
            root, args.corpus or canonical_corpus_path()
        ),
        "handoff": str(handoff) if handoff else None,
    }
    status.update(
        {
            key: accounting[key]
            for key in (
                "input_observations",
                "invalid_observations",
                "excluded_observations",
                "already_reviewed_observations",
                "duplicate_observations",
                "candidate_observations",
                "available_cases",
                "selected_cases",
                "selected_source_observations",
            )
            if key in accounting
        }
    )
    if args.json:
        write_json(args.json, status)
    for key, value in status.items():
        if key in {"review_ready", "integrated"}:
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


def _canonical_lineage_path(repo_root: Path) -> Path:
    return repo_root / "data" / "lineage" / "review-evidence.jsonl"


def _default_review_evidence_paths(
    repo_root: Path, work_root: Path | None = None
) -> list[Path]:
    """Return only the configured canonical lineage, never work-root snapshots."""
    lineage = _canonical_lineage_path(repo_root)
    return [lineage] if lineage.is_file() else []


def _default_canonical_paths(repo_root: Path) -> list[Path]:
    corpus = canonical_corpus_path(repo_root)
    if corpus.exists():
        return [corpus]
    legacy = corpus.with_suffix(".jsonl")
    if legacy.exists():
        return [legacy]
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
    conflicts = find_evidence_conflicts(args.record_id, evidence)
    if conflicts:
        diagnostic = {
            "record_id": args.record_id,
            "record_status": "found",
            "lineage_status": "conflict",
            "conflicts": [item.to_dict() for item in conflicts],
            "evidence_paths": [str(path) for path in evidence_paths],
            "authoritative_lineage": str(_canonical_lineage_path(repo_root)),
        }
        if args.json:
            print(json.dumps(diagnostic, ensure_ascii=False, indent=2))
        else:
            print(f"record_id={args.record_id}")
            print("record_status=found")
            print("lineage_status=conflict")
            for conflict in conflicts:
                print(f"conflicting_revision={conflict.revision}")
                print(f"sources={len(conflict.variants)}")
                for variant in conflict.variants:
                    print(f"  path={variant.source}")
                    print(f"  hash={variant.artifact_hash}")
                    print(f"  final_record_hash={variant.final_record_hash}")
            print("hint=These files contain conflicting evidence for one revision.")
            print(f"authoritative_lineage={_canonical_lineage_path(repo_root)}")
        return 2
    result = resolve_record_evidence(args.record_id, records, evidence)
    latest = max(
        result["evidence"], key=lambda row: row.get("review_revision", -1), default={}
    )
    result["evidence_paths"] = [str(path) for path in evidence_paths]
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    record = result["record"]
    raw_decision = latest.get("decision") if isinstance(latest, dict) else None
    decision = raw_decision if isinstance(raw_decision, dict) else {}
    raw_comparison = latest.get("comparison") if isinstance(latest, dict) else None
    comparison = raw_comparison if isinstance(raw_comparison, dict) else None
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
        if comparison is None:
            comparison_status = "missing"
        elif comparison.get("disagreement"):
            comparison_status = "disagreement"
        else:
            comparison_status = "agreement"
        print(f"  A/B: {comparison_status}")
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
        out_root = WorkLayout(runtime.work_root).correction(args.record_id).root
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
    _config, runtime, repo_root, records, evidence = _correction_inputs(args)
    correction = read_json(args.correction)
    original = next((row for row in records if row.get("id") == args.record_id), None)
    if original is None:
        raise ValueError(f"unknown canonical record id: {args.record_id}")
    updated, history_item = apply_correction(original, correction, evidence=evidence)
    if args.out_root:
        out_root = Path(args.out_root)
    elif runtime.work_root is not None:
        out_root = (
            WorkLayout(runtime.work_root)
            .correction(args.record_id, history_item["review_revision"])
            .root
        )
    else:
        raise ConfigError(
            "apply-correction requires --out-root or a configured work root"
        )
    if args.write:
        corpus_root = canonical_corpus_path(repo_root)
        paths = apply_correction_to_corpus(
            corpus_root,
            _canonical_lineage_path(repo_root),
            original,
            correction,
            evidence,
            out_root,
        )
    else:
        paths = write_correction_application(
            out_root, records, updated, history_item, evidence
        )
    print(f"Corrected {args.record_id}.")
    print(f"Old oracle hash: {history_item['old_oracle_hash']}")
    print(f"New oracle hash: {history_item['new_oracle_hash']}")
    print(f"Revision: {history_item['review_revision']}")
    print(f"Preview: {paths['report']}#record={args.record_id}")
    return 0


def _packet_output_summary(path: Path, rows: list[dict]) -> None:
    size = sum(serialized_row_bytes(row) for row in rows)
    print(f"packet={path} cases={len(rows)} bytes={size}")


def _next_packet_number(directory: Path) -> int:
    numbers = []
    for path in directory.glob("*.input.jsonl") if directory.is_dir() else []:
        try:
            numbers.append(int(path.name.split(".", 1)[0]))
        except ValueError:
            continue
    return max(numbers, default=0) + 1


def cmd_review_packet(args):
    root, _work_root = _resolve_batch_root(args)
    layout = BatchLayout(root)
    metadata = read_json(layout.metadata) if layout.metadata.is_file() else {}
    if metadata.get("state") == "empty":
        print(
            f"batch={metadata.get('batch_id', root.name)} state=empty no_review_packet"
        )
        return 0
    blind_path = (
        layout.review_blind(args.slot)
        if layout.review_blind(args.slot).is_file()
        else root / f"{'a' if args.slot == 'A' else 'b'}.blind.jsonl"
    )
    completed_path = args.completed or layout.review_complete(args.slot)
    completed = read_records([completed_path]) if Path(completed_path).is_file() else []
    rows = review_packet_rows(
        read_records([blind_path]),
        completed,
        max_cases=args.max_cases,
        max_bytes=args.max_bytes,
    )
    packet_number = _next_packet_number(layout.review_packet_dir(args.slot))
    output = (
        Path(args.out) if args.out else layout.review_packet(args.slot, packet_number)
    )
    write_jsonl(output, rows)
    _packet_output_summary(output, rows)
    return 0


def cmd_review_merge(args):
    root, _work_root = _resolve_batch_root(args)
    layout = BatchLayout(root)
    blind_path = (
        layout.review_blind(args.slot)
        if layout.review_blind(args.slot).is_file()
        else root / f"{'a' if args.slot == 'A' else 'b'}.blind.jsonl"
    )
    existing_path = (
        Path(args.completed)
        if args.completed
        else layout.review_complete(args.slot)
        if layout.review_complete(args.slot).is_file()
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


def cmd_batch_migrate_adjudication(args):
    root, _work_root = _resolve_batch_root(args)
    result = migrate_legacy_adjudication(root, write=args.write)
    print(f"batch_id={result['batch_id']}")
    print(f"rows={result['rows']}")
    print(f"legacy_unresolved_missing_blocker={result['rows_changed']}")
    print(f"rows_changed={result['rows_changed']}")
    print(f"rule={result['rule']}")
    print(
        f"ready_to_write={'yes' if not args.write or result['rows_changed'] >= 0 else 'no'}"
    )
    return 0


def cmd_adjudication_repair_packet(args):
    root, _work_root = _resolve_batch_root(args)
    layout = BatchLayout(root)
    preflight = batch_preflight(root, args.corpus or canonical_corpus_path())
    diagnostics = preflight["invalid_accepts"]
    if not diagnostics:
        raise ValueError("batch preflight found no invalid accepted decisions")
    cases = read_records(
        [layout.cases if layout.cases.is_file() else root / "cases.jsonl"]
    )
    contexts = read_records([layout.context]) if layout.context.is_file() else cases
    review_a_path = (
        layout.review_complete("A")
        if layout.review_complete("A").is_file()
        else root / "a.complete.jsonl"
    )
    review_b_path = (
        layout.review_complete("B")
        if layout.review_complete("B").is_file()
        else root / "b.complete.jsonl"
    )
    decisions_path = (
        layout.adjudication_decisions
        if layout.adjudication_decisions.is_file()
        else root / "adjudicated.jsonl"
    )
    review_a = read_records([review_a_path])
    review_b = read_records([review_b_path])
    decisions = read_records([decisions_path])
    rows = adjudication_repair_packet_rows(
        cases,
        contexts,
        review_a,
        review_b,
        decisions,
        diagnostics,
        max_cases=args.max_cases,
        max_bytes=args.max_bytes,
    )
    output = args.out or layout.adjudication_dir / "repair-packet-001.jsonl"
    write_jsonl(output, rows)
    _packet_output_summary(output, rows)
    return 0


def cmd_adjudication_repair_merge(args):
    root, _work_root = _resolve_batch_root(args)
    layout = BatchLayout(root)
    cases = read_records(
        [layout.cases if layout.cases.is_file() else root / "cases.jsonl"]
    )
    decisions_path = (
        layout.adjudication_decisions
        if layout.adjudication_decisions.is_file()
        else root / "adjudicated.jsonl"
    )
    existing = read_records([decisions_path])
    packet = read_records([args.packet])
    result_rows = read_records([args.packet_result])
    selected = [row.get("case_id") for row in packet]
    output = args.out or decisions_path
    manifest = args.manifest or root / "adjudication-repair-manifest.json"
    merged = merge_adjudication_repairs(
        existing, result_rows, selected, cases, output=output, manifest=manifest
    )
    print(f"merged={output} decisions={len(merged)} repaired={len(selected)}")
    print(f"manifest={manifest}")
    return 0


def cmd_adjudication_packet(args):
    root, _work_root = _resolve_batch_root(args)
    layout = BatchLayout(root)
    cases_path = layout.cases if layout.cases.is_file() else root / "cases.jsonl"
    cases = read_records([cases_path])
    review_a = read_records([args.review_a])
    review_b = read_records([args.review_b])
    review_report = check_reviews(cases, review_a, review_b)
    if not review_report["ready"]:
        raise ValueError("review-check failed: " + "; ".join(review_report["issues"]))
    context_path = (
        layout.context if layout.context.is_file() else root / "context.jsonl"
    )
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
    packet_number = _next_packet_number(layout.adjudication_dir / "packets")
    output = Path(args.out) if args.out else layout.adjudication_packet(packet_number)
    write_jsonl(output, rows)
    _packet_output_summary(output, rows)
    return 0


def cmd_adjudication_merge(args):
    root, _work_root = _resolve_batch_root(args)
    layout = BatchLayout(root)
    existing_path = (
        Path(args.decisions)
        if args.decisions
        else layout.adjudication_partial
        if layout.adjudication_partial.is_file()
        else root / "adjudicated.partial.jsonl"
    )
    existing = read_records([existing_path]) if existing_path.is_file() else []
    merged = merge_adjudication_rows(existing, read_records([args.packet_result]))
    cases_path = layout.cases if layout.cases.is_file() else root / "cases.jsonl"
    if args.finalize:
        merged = finalize_adjudication(read_records([cases_path]), merged)
    output = Path(args.out)
    write_jsonl(output, merged)
    if args.finalize:
        merged = finalize_adjudication(
            read_records([cases_path]), merged, output=output
        )
    print(f"merged={output} decisions={len(merged)}")
    return 0


def cmd_batch_create(args):
    config_path = args.config if args.config is not None else default_config_path()
    config = load_config(config_path, explicit=args.config is not None)
    runtime = require_runtime_paths(
        resolve_runtime_paths(
            config=config,
            source_cache=args.source_cache,
            work_root=args.work_root,
        )
    )
    layout = WorkLayout(runtime.work_root)
    batch = layout.batch(args.batch)
    if batch.root.exists() and any(batch.root.iterdir()):
        raise ValueError(f"batch output root must be new or empty: {batch.root}")
    batch.root.mkdir(parents=True, exist_ok=True)
    prepared = prepare_observations(
        runtime.source_cache,
        batch.source_dir,
        reviewed_paths=args.reviewed,
        languages=args.languages,
        sources=args.sources,
        targets_path=args.targets,
        batch_name=args.batch,
    )
    with __import__("tempfile").TemporaryDirectory(
        prefix="spokenform-gold-batch-"
    ) as temporary:
        result = collect_batch(
            [prepared["observations"]],
            reviewed_paths=args.reviewed or [canonical_corpus_path()],
            exclusion_paths=[prepared["exclusions"]],
            output_root=temporary,
            batch_id=args.batch,
            limit=args.limit,
            source_lock_hash=args.source_lock_hash,
        )
        write_jsonl(batch.cases, read_jsonl(Path(temporary) / "cases.jsonl"))
        write_jsonl(batch.context, read_jsonl(Path(temporary) / "context.jsonl"))
        if result["case_count"]:
            write_jsonl(
                batch.review_blind("A"), read_jsonl(Path(temporary) / "a.blind.jsonl")
            )
            write_jsonl(
                batch.review_blind("B"), read_jsonl(Path(temporary) / "b.blind.jsonl")
            )
        result["source"] = {
            label: str(path) for label, path in prepared.items() if label != "summary"
        }
        write_json(batch.metadata, result)
    print(
        f"batch_id={args.batch} state={result['state']} "
        f"input_observations={result['accounting']['input_observations']} "
        f"unseen_observations={result['accounting']['candidate_observations']} "
        f"available_cases={result['accounting']['available_cases']} "
        f"selected_cases={result['accounting']['selected_cases']}"
    )
    if result["state"] == "empty":
        print("reason=no_unreviewed_cases")
    else:
        print(f"next=review-packet --batch {args.batch} --slot A")
    return 0


def cmd_collect(args):
    reviewed = args.reviewed or [canonical_corpus_path()]
    result = collect_batch(
        args.observations,
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
    layout = BatchLayout(args.batch)
    cases_path = layout.cases if layout.cases.is_file() else args.batch / "cases.jsonl"
    result = check_reviews(
        read_records([cases_path]),
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


def _print_retry_summary(summary: dict) -> None:
    for key in (
        "total_unique",
        "needs_triage",
        "blocked",
        "ready",
        "in_retry_batch",
        "resolved",
        "terminal",
        "duplicate_failure_events",
    ):
        if key in summary:
            print(f"{key}={summary[key]}")
    for code, count in sorted((summary.get("blockers") or {}).items()):
        print(f"blocker.{code}={count}")


def cmd_exclusions_rebuild(args):
    work_root = _work_root_from_args(args)
    corpus = args.corpus or canonical_corpus_path()
    summary = rebuild_retry_pool(work_root, corpus)
    if args.json:
        write_json(args.json, summary)
    _print_retry_summary(summary)
    print(f"pool={summary['pool']}")
    return 0


def cmd_exclusions_status(args):
    work_root = _work_root_from_args(args)
    layout = WorkLayout(work_root)
    rows = load_retry_pool(layout.retry_pool)
    summary = retry_pool_summary(rows).to_dict()
    if args.json:
        write_json(args.json, summary)
    _print_retry_summary(summary)
    print(f"pool={layout.retry_pool}")
    return 0


def cmd_rereview_batch_create(args):
    work_root = _work_root_from_args(args)
    layout = WorkLayout(work_root)
    rows = load_retry_pool(args.pool or layout.retry_pool)
    selected = select_retry_cases(
        rows,
        limit=min(args.limit, REVIEW_BATCH_LIMIT),
        blocker_codes=set(args.blocker or []),
        languages=set(args.languages or []),
    )
    if not selected:
        raise ValueError("no retry cases are ready for re-review")
    metadata = build_rereview_batch(
        selected,
        work_root=work_root,
        batch_id=args.batch,
        corpus_path=args.corpus or canonical_corpus_path(),
    )
    selected_ids = {row["case_id"] for row in selected}
    updated = []
    for row in rows:
        item = dict(row)
        if item.get("case_id") in selected_ids:
            item["state"] = "in_retry_batch"
            item["active_retry_batch"] = args.batch
        updated.append(item)
    write_retry_pool_atomic(args.pool or layout.retry_pool, updated)
    print(
        f"batch={metadata['batch_id']} kind={metadata['batch_kind']} cases={metadata['case_count']} state={metadata['state']}"
    )
    print(f"selection_hash={metadata['rereview']['selection_hash']}")
    return 0


def cmd_batch_preflight(args):
    root, _work_root = _resolve_batch_root(args)
    result = batch_preflight(root, args.corpus or canonical_corpus_path())
    if args.json:
        write_json(args.json, result)
    print(f"batch_id={result['batch_id']}")
    print(f"cases={result['cases']}")
    print(f"reviews_ready={'yes' if result['reviews_ready'] else 'no'}")
    print(f"adjudication_complete={'yes' if result['adjudication_complete'] else 'no'}")
    print(f"accept={result['accept']}")
    print(f"exclude={result['exclude']}")
    print(f"unresolved={result['unresolved']}")
    print(f"invalid_accepts={len(result['invalid_accepts'])}")
    print(f"invalid_units={result['invalid_units']}")
    print(
        "legacy_unresolved_missing_blocker="
        f"{result['legacy_unresolved_missing_blocker']}"
    )
    print(f"ready_to_finalize={'yes' if result['ready_to_finalize'] else 'no'}")
    if result.get("next"):
        print(f"next={result['next']}")
    return 0 if result["ready_to_finalize"] else 2


def cmd_batch_finalize(args):
    root, work_root = _resolve_batch_root(args)
    corpus = args.corpus or canonical_corpus_path()
    pool = args.retry_pool
    if pool is None and work_root is not None:
        pool = WorkLayout(work_root).retry_pool
    result = finalize_batch(root, corpus, pool, write=args.write)
    print(
        f"state={result['state']} accepted={result['accepted']} "
        f"terminal_excluded={result['terminal_excluded']} "
        f"retry_deferred={result['retry_deferred']} "
        f"records_added={result['records_added']}"
    )
    return 0


def cmd_report(args):
    record_paths = args.records or [canonical_corpus_path()]
    records = read_records(record_paths)
    errors = (
        validate_corpus(record_paths[0])
        if len(record_paths) == 1 and Path(record_paths[0]).is_dir()
        else validate_records(records)
    )
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
    review_paths = _default_review_evidence_paths(Path.cwd())
    review_evidence = read_records(review_paths) if review_paths else []
    output = render_release_html(
        args.out,
        version=args.version,
        maturity="corpus",
        records=records,
        coverage=coverage,
        control_coverage={},
        counts=counts,
        review_evidence=review_evidence,
    )
    print(f"wrote corpus report for {len(records)} records to {output}")
    return 0


def cmd_corpus_site(args):
    record_paths = args.records or [canonical_corpus_path()]
    records = read_records(record_paths)
    errors = (
        validate_corpus(record_paths[0])
        if len(record_paths) == 1 and Path(record_paths[0]).is_dir()
        else validate_records(records)
    )
    if errors:
        raise ValueError(
            "cannot generate corpus site for invalid corpus: " + "; ".join(errors)
        )
    evidence_path = args.review_evidence
    evidence = (
        read_records([evidence_path])
        if evidence_path and Path(evidence_path).is_file()
        else []
    )
    result = generate_corpus_site(
        records,
        args.out_dir,
        review_evidence=evidence,
        issues_url=args.issues_url or None,
        max_records_per_page=args.max_records_per_page,
        write=args.write,
        check=args.check,
    )
    print(
        f"corpus_site={result['corpus_site']} changed={result['changed']} "
        f"missing={result['missing']} extra={result['extra']} files={result['files']}"
    )
    if args.check and result["corpus_site"] == "stale":
        print(f"next=spokenform-gold corpus-site --out-dir {args.out_dir} --write")
        return 1
    return 0


def cmd_export(args):
    records = read_records(args.records or [canonical_corpus_path()])
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

    if bool(args.gold_root) == bool(args.corpus):
        raise ValueError("provide exactly one of --gold-root or --corpus")
    summary = run_benchmark(
        gold_root=args.gold_root,
        corpus_root=args.corpus,
        split=args.split,
        results_dir=args.results_dir,
        prepare_module=args.prepare_module,
        language=args.language,
        locale=args.locale,
        category=args.category,
        status=args.status,
        case_ids=set(args.case_id or []),
        mode=args.mode,
    )
    print(
        json.dumps(
            {
                "records": summary["record_count"],
                "results_dir": str(args.results_dir),
                "split": args.split,
                "artifact_kind": "local_canonical_benchmark"
                if args.corpus
                else "release",
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

    corpus_status = sub.add_parser("corpus-status")
    corpus_status.add_argument("--records", nargs="*")
    corpus_status.add_argument("--source-manifest", default="sources/manifest.json")
    corpus_status.add_argument("--preflight")
    corpus_status.add_argument("--retry-backlog", type=int, default=0)
    corpus_status.add_argument("--json")
    corpus_status.set_defaults(func=cmd_corpus_status)
    migrate = sub.add_parser("migrate-oracle")
    migrate.add_argument("input")
    migrate.add_argument("--out", required=True)
    migrate.set_defaults(func=cmd_migrate_oracle)

    shard = sub.add_parser("shard-corpus")
    shard.add_argument("--input", type=Path, required=True)
    shard.add_argument("--out", type=Path, required=True)
    shard.set_defaults(func=cmd_shard_corpus)

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
    coverage.add_argument(
        "--language-profile",
        choices=["stable", "cjk-experimental", "all-active"],
        default="stable",
    )
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

    source_policy_status = sub.add_parser("source-policy-status")
    source_policy_status.add_argument("--records", nargs="*")
    source_policy_status.add_argument(
        "--source-manifest", default="sources/manifest.json"
    )
    source_policy_status.add_argument("--decisions")
    source_policy_status.add_argument("--out")
    source_policy_status.set_defaults(func=cmd_source_policy_status)
    source_policy_packet = sub.add_parser("source-policy-packet")
    source_policy_packet.add_argument("--source", required=True)
    source_policy_packet.add_argument("--slot", choices=["A", "B"], required=True)
    source_policy_packet.add_argument("--records", nargs="*")
    source_policy_packet.add_argument(
        "--source-manifest", default="sources/manifest.json"
    )
    source_policy_packet.add_argument("--out", required=True)
    source_policy_packet.set_defaults(func=cmd_source_policy_packet)
    source_policy_review_merge = sub.add_parser("source-policy-review-merge")
    source_policy_review_merge.add_argument("--packet", required=True)
    source_policy_review_merge.add_argument("--result", required=True)
    source_policy_review_merge.add_argument("--out", required=True)
    source_policy_review_merge.set_defaults(func=cmd_source_policy_review_merge)
    source_policy_check = sub.add_parser("source-policy-check")
    source_policy_check.add_argument("--records", nargs="*")
    source_policy_check.add_argument(
        "--source-manifest", default="sources/manifest.json"
    )
    source_policy_check.add_argument("--decisions", required=True)
    source_policy_check.add_argument("--out")
    source_policy_check.set_defaults(func=cmd_source_policy_check)
    source_policy_adjudication_packet = sub.add_parser(
        "source-policy-adjudication-packet"
    )
    source_policy_adjudication_packet.add_argument("--packet", required=True)
    source_policy_adjudication_packet.add_argument("--review-a", required=True)
    source_policy_adjudication_packet.add_argument("--review-b", required=True)
    source_policy_adjudication_packet.add_argument("--out", required=True)
    source_policy_adjudication_packet.set_defaults(
        func=cmd_source_policy_adjudication_packet
    )
    source_policy_adjudication_merge = sub.add_parser(
        "source-policy-adjudication-merge"
    )
    source_policy_adjudication_merge.add_argument("--packet", required=True)
    source_policy_adjudication_merge.add_argument("--result", required=True)
    source_policy_adjudication_merge.add_argument("--out", required=True)
    source_policy_adjudication_merge.set_defaults(
        func=cmd_source_policy_adjudication_merge
    )
    source_policy_apply = sub.add_parser("source-policy-apply")
    source_policy_apply.add_argument("--decision", required=True)
    source_policy_apply.add_argument(
        "--source-manifest", default="sources/manifest.json"
    )
    source_policy_apply.add_argument("--write", action="store_true")
    source_policy_apply.set_defaults(func=cmd_source_policy_apply)

    source_census = sub.add_parser("source-census")
    source_census.add_argument("records", nargs="+")
    source_census.add_argument("--source-manifest", default="sources/manifest.json")
    source_census.add_argument("--out", required=True)
    source_census.set_defaults(func=cmd_source_census)

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

    translation_prepare = sub.add_parser("translation-prepare")
    translation_prepare.add_argument("--records", nargs="+", required=True)
    translation_prepare.add_argument(
        "--target", required=True, help="Target locale such as ja-JP"
    )
    translation_prepare.add_argument("--limit", type=int)
    translation_prepare.add_argument(
        "--mode",
        choices=["semantic_translation", "locale_transplant", "locale-transplant"],
        default="locale_transplant",
    )
    translation_prepare.add_argument("--batch", required=True)
    translation_prepare.add_argument("--out-root", type=Path, required=True)
    translation_prepare.set_defaults(func=cmd_translation_prepare)

    translation_packet = sub.add_parser("translation-packet")
    translation_packet.add_argument("--batch", required=True)
    translation_packet.add_argument("--slot", choices=["A", "B"], required=True)
    translation_packet.add_argument("--completed", type=Path)
    translation_packet.add_argument("--max-cases", type=int, default=25)
    translation_packet.add_argument("--max-bytes", type=int, default=100000)
    translation_packet.add_argument("--out", type=Path, required=True)
    translation_packet.set_defaults(func=cmd_translation_packet)

    translation_merge = sub.add_parser("translation-merge")
    translation_merge.add_argument("--batch", required=True)
    translation_merge.add_argument("--blind", type=Path)
    translation_merge.add_argument("--existing", type=Path)
    translation_merge.add_argument("--results", type=Path, required=True)
    translation_merge.add_argument("--slot", choices=["A", "B"], required=True)
    translation_merge.add_argument("--out", type=Path, required=True)
    translation_merge.set_defaults(func=cmd_translation_merge)

    translation_check = sub.add_parser("translation-check")
    translation_check.add_argument("--batch", required=True)
    translation_check.add_argument("--translation-a", type=Path, required=True)
    translation_check.add_argument("--translation-b", type=Path, required=True)
    translation_check.add_argument("--json", type=Path)
    translation_check.set_defaults(func=cmd_translation_check)

    translation_adj_packet = sub.add_parser("translation-adjudication-packet")
    translation_adj_packet.add_argument("--batch", required=True)
    translation_adj_packet.add_argument("--translation-a", type=Path, required=True)
    translation_adj_packet.add_argument("--translation-b", type=Path, required=True)
    translation_adj_packet.add_argument("--decisions", type=Path)
    translation_adj_packet.add_argument("--max-cases", type=int, default=100)
    translation_adj_packet.add_argument("--max-bytes", type=int, default=98304)
    translation_adj_packet.add_argument("--out", type=Path, required=True)
    translation_adj_packet.set_defaults(func=cmd_translation_adjudication_packet)

    translation_adj_merge = sub.add_parser("translation-adjudication-merge")
    translation_adj_merge.add_argument("--batch", required=True)
    translation_adj_merge.add_argument("--packet-result", type=Path, required=True)
    translation_adj_merge.add_argument("--decisions", type=Path)
    translation_adj_merge.add_argument("--out", type=Path, required=True)
    translation_adj_merge.set_defaults(func=cmd_translation_adjudication_merge)

    translation_finalize = sub.add_parser("translation-finalize")
    translation_finalize.add_argument("--batch", required=True)
    translation_finalize.add_argument("--translation-a", type=Path, required=True)
    translation_finalize.add_argument("--translation-b", type=Path, required=True)
    translation_finalize.add_argument("--decisions", type=Path, required=True)
    translation_finalize.add_argument("--out", type=Path, required=True)
    translation_finalize.set_defaults(func=cmd_translation_finalize)

    ingest = sub.add_parser("ingest-upstreams")
    ingest.add_argument("--source-cache", type=Path, default=None)
    ingest.add_argument("--work-root", type=Path, default=None)
    ingest.add_argument(
        "--sources", nargs="+", default=["async_tn", "polynorm", "proteno"]
    )
    ingest.add_argument(
        "--languages", nargs="+", default=list(DEFAULT_INGEST_LANGUAGES)
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
    release.add_argument("--release-sources", nargs="+")
    release.add_argument("--source-decisions")
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
    work_status = sub.add_parser("work-status")
    work_status.add_argument("--work-root", type=Path)
    work_status.set_defaults(func=cmd_work_status)

    exclusions_rebuild = sub.add_parser("exclusions-rebuild")
    exclusions_rebuild.add_argument("--work-root", type=Path)
    exclusions_rebuild.add_argument("--corpus", type=Path)
    exclusions_rebuild.add_argument("--json", type=Path)
    exclusions_rebuild.set_defaults(func=cmd_exclusions_rebuild)
    exclusions_status = sub.add_parser("exclusions-status")
    exclusions_status.add_argument("--work-root", type=Path)
    exclusions_status.add_argument("--json", type=Path)
    exclusions_status.set_defaults(func=cmd_exclusions_status)
    rereview_create = sub.add_parser("rereview-batch-create")
    rereview_create.add_argument("--batch", required=True)
    rereview_create.add_argument("--limit", type=int, default=REVIEW_BATCH_LIMIT)
    rereview_create.add_argument("--blocker", action="append")
    rereview_create.add_argument("--languages", nargs="*")
    rereview_create.add_argument("--include-needs-triage", action="store_true")
    rereview_create.add_argument("--work-root", type=Path)
    rereview_create.add_argument("--pool", type=Path)
    rereview_create.add_argument("--corpus", type=Path)
    rereview_create.set_defaults(func=cmd_rereview_batch_create)
    batch_finalize = sub.add_parser("batch-finalize")
    batch_finalize.add_argument("--batch", required=True)
    batch_finalize.add_argument("--corpus", type=Path)
    batch_finalize.add_argument("--retry-pool", type=Path)
    batch_finalize.add_argument("--write", action="store_true")
    batch_finalize.add_argument("--work-root", type=Path)
    batch_finalize.set_defaults(func=cmd_batch_finalize)
    work_migrate = sub.add_parser("work-migrate")
    work_migrate.add_argument("--work-root", type=Path)
    work_migrate.add_argument("--dry-run", action="store_true")
    work_migrate.add_argument("--apply", action="store_true")
    work_migrate.set_defaults(func=cmd_work_migrate)
    batch_status = sub.add_parser("batch-status")
    batch_status.add_argument("--batch", required=True)
    batch_status.add_argument("--work-root", type=Path)
    batch_status.add_argument("--corpus", type=Path, default=canonical_corpus_path())
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
    apply_correction.add_argument("--write", action="store_true")
    apply_correction.set_defaults(func=cmd_apply_correction)
    batch_create = sub.add_parser("batch-create")
    batch_create.add_argument("--batch", required=True)
    batch_create.add_argument("--limit", type=int, default=DEFAULT_V2_COLLECTION_LIMIT)
    batch_create.add_argument("--source-cache", type=Path, default=None)
    batch_create.add_argument("--work-root", type=Path, default=None)
    batch_create.add_argument(
        "--sources", nargs="+", default=["async_tn", "polynorm", "proteno"]
    )
    batch_create.add_argument(
        "--languages", nargs="+", default=list(DEFAULT_INGEST_LANGUAGES)
    )
    batch_create.add_argument("--reviewed", nargs="+")
    batch_create.add_argument("--targets")
    batch_create.add_argument("--source-lock-hash")
    batch_create.set_defaults(func=cmd_batch_create)

    collect = sub.add_parser("collect")
    collect.add_argument("--observations", nargs="+", required=True)
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
    review_packet.add_argument("--out", type=Path)
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
    batch_migrate = sub.add_parser("batch-migrate-adjudication")
    batch_migrate.add_argument("--batch", required=True)
    batch_migrate.add_argument("--write", action="store_true")
    batch_migrate.add_argument("--work-root", type=Path)
    batch_migrate.set_defaults(func=cmd_batch_migrate_adjudication)
    repair_packet = sub.add_parser("adjudication-repair-packet")
    repair_packet.add_argument("--batch", required=True)
    repair_packet.add_argument("--corpus", type=Path, default=canonical_corpus_path())
    repair_packet.add_argument("--max-cases", type=int, default=50)
    repair_packet.add_argument("--max-bytes", type=int, default=98304)
    repair_packet.add_argument("--out", type=Path)
    repair_packet.add_argument("--work-root", type=Path)
    repair_packet.set_defaults(func=cmd_adjudication_repair_packet)
    repair_merge = sub.add_parser("adjudication-repair-merge")
    repair_merge.add_argument("--batch", required=True)
    repair_merge.add_argument("--packet", type=Path, required=True)
    repair_merge.add_argument("--packet-result", type=Path, required=True)
    repair_merge.add_argument("--out", type=Path)
    repair_merge.add_argument("--manifest", type=Path)
    repair_merge.add_argument("--work-root", type=Path)
    repair_merge.set_defaults(func=cmd_adjudication_repair_merge)
    adjudication_packet = sub.add_parser("adjudication-packet")
    adjudication_packet.add_argument("--batch", required=True)
    adjudication_packet.add_argument("--review-a", type=Path, required=True)
    adjudication_packet.add_argument("--review-b", type=Path, required=True)
    adjudication_packet.add_argument("--decisions", type=Path)
    adjudication_packet.add_argument("--max-cases", type=int, default=100)
    adjudication_packet.add_argument("--max-bytes", type=int, default=98304)
    adjudication_packet.add_argument("--out", type=Path)
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
    batch_preflight_parser = sub.add_parser("batch-preflight")
    batch_preflight_parser.add_argument("--batch", type=Path, required=True)
    batch_preflight_parser.add_argument(
        "--corpus", type=Path, default=canonical_corpus_path()
    )
    batch_preflight_parser.add_argument("--json", type=Path)
    batch_preflight_parser.set_defaults(func=cmd_batch_preflight)
    integrate = sub.add_parser("integrate")
    integrate.add_argument("--batch", type=Path, required=True)
    integrate.add_argument("--corpus", type=Path, default=canonical_corpus_path())
    integrate.add_argument("--write", action="store_true")
    integrate.set_defaults(func=cmd_integrate)
    corpus_site = sub.add_parser("corpus-site")
    corpus_site.add_argument("--records", nargs="*")
    corpus_site.add_argument(
        "--review-evidence",
        type=Path,
        default=Path("data/lineage/review-evidence.jsonl"),
    )
    corpus_site.add_argument(
        "--targets", type=Path, default=Path("taxonomy/coverage_targets.json")
    )
    corpus_site.add_argument("--out-dir", type=Path, default=Path("docs/corpus"))
    corpus_site.add_argument("--issues-url", default=DEFAULT_ISSUES_URL)
    corpus_site.add_argument("--max-records-per-page", type=int, default=3000)
    corpus_site.add_argument("--write", action="store_true")
    corpus_site.add_argument("--check", action="store_true")
    corpus_site.set_defaults(func=cmd_corpus_site)
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
    preflight_release = sub.add_parser("release-preflight")
    preflight_release.add_argument("--data", nargs="+", required=True)
    preflight_release.add_argument("--source-manifest")
    preflight_release.add_argument("--source-decisions")
    preflight_release.add_argument("--release-sources", nargs="+")
    preflight_release.add_argument("--out", required=True)
    preflight_release.set_defaults(func=cmd_release_preflight)

    release_v2 = sub.add_parser("release")
    release_v2.add_argument("--version", required=True)
    release_v2.add_argument("--data", nargs="+", default=[str(canonical_corpus_path())])
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
    release_v2.add_argument("--release-sources", nargs="+")
    release_v2.add_argument("--source-decisions")
    release_v2.set_defaults(func=cmd_release_check)
    benchmark = sub.add_parser("benchmark")
    benchmark.add_argument("--gold-root")
    benchmark.add_argument("--corpus")
    benchmark.add_argument("--split")
    benchmark.add_argument("--prepare-module", required=True)
    benchmark.add_argument("--results-dir", required=True)
    benchmark.add_argument("--language")
    benchmark.add_argument("--locale")
    benchmark.add_argument("--category")
    benchmark.add_argument("--status")
    benchmark.add_argument("--case-id", action="append")
    benchmark.add_argument(
        "--mode", choices=["canonical", "accepted"], default="canonical"
    )
    benchmark.set_defaults(func=cmd_benchmark)
    campaign_create = sub.add_parser("campaign-create")
    campaign_create.add_argument("--campaign", required=True)
    campaign_create.add_argument("--work-root", type=Path)
    campaign_create.add_argument("--batch-size", type=int, default=1000)
    campaign_create.add_argument("--batches", nargs="*")
    campaign_create.set_defaults(func=cmd_campaign_create)
    campaign_status_parser = sub.add_parser("campaign-status")
    campaign_status_parser.add_argument("--campaign", required=True)
    campaign_status_parser.add_argument("--work-root", type=Path)
    campaign_status_parser.add_argument("--json", type=Path)
    campaign_status_parser.set_defaults(func=cmd_campaign_status)
    campaign_next_parser = sub.add_parser("campaign-next")
    campaign_next_parser.add_argument("--campaign", required=True)
    campaign_next_parser.add_argument(
        "--role", choices=["review-a", "review-b", "adjudicator"], required=True
    )
    campaign_next_parser.add_argument("--work-root", type=Path)
    campaign_next_parser.add_argument("--out", type=Path)
    campaign_next_parser.set_defaults(func=cmd_campaign_next)
    campaign_finalize_parser = sub.add_parser("campaign-finalize")
    campaign_finalize_parser.add_argument("--campaign", required=True)
    campaign_finalize_parser.add_argument(
        "--corpus", type=Path, default=canonical_corpus_path()
    )
    campaign_finalize_parser.add_argument("--retry-pool", type=Path)
    campaign_finalize_parser.add_argument("--work-root", type=Path)
    campaign_finalize_parser.add_argument("--write", action="store_true")
    campaign_finalize_parser.set_defaults(func=cmd_campaign_finalize)
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
