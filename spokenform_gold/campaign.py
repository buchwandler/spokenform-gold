"""Deterministic orchestration across bounded semantic-review batches."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from pathlib import Path

from .io import read_json, read_jsonl, write_json, write_jsonl
from .packets import (
    adjudication_packet_rows,
    merge_adjudication_rows,
    merge_review_rows,
    review_packet_rows,
)
from .work_layout import BatchLayout
from .workflow import check_reviews

ROLES = {"review-a", "review-b", "adjudicator"}


def _rows_digest(rows: Iterable[dict]) -> str:
    payload = json.dumps(
        sorted(rows, key=lambda row: str(row.get("case_id", row.get("id", "")))),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def resolve_campaign_root(
    campaign: str | Path, work_root: str | Path | None = None
) -> Path:
    path = Path(campaign).expanduser()
    if path.exists() or path.is_absolute():
        return path.resolve()
    if work_root is None:
        raise ValueError("campaign ID requires --work-root")
    return (Path(work_root) / "campaigns" / path).resolve()


def create_campaign(
    campaign: str | Path,
    *,
    work_root: str | Path | None = None,
    batch_size: int = 1000,
    batch_roots: list[str | Path] | None = None,
    review_packet_max_cases: int = 200,
    review_packet_max_bytes: int = 98304,
    adjudication_packet_max_cases: int = 100,
    adjudication_packet_max_bytes: int = 98304,
    source: str | None = None,
    source_revision: str | None = None,
    languages: list[str] | None = None,
    language_routing: bool = True,
) -> dict:
    if batch_size < 1 or batch_size > 1000:
        raise ValueError("batch_size must be between 1 and 1000")
    root = resolve_campaign_root(campaign, work_root)
    if root.exists() and any(root.iterdir()):
        raise ValueError(f"campaign root must be new or empty: {root}")
    if batch_roots is None and work_root is not None:
        batch_root = Path(work_root) / "batches"
        batch_roots = (
            sorted(path for path in batch_root.iterdir() if path.is_dir())
            if batch_root.is_dir()
            else []
        )
    batch_roots = batch_roots or []
    root.mkdir(parents=True, exist_ok=True)
    batch_entries = []
    for index, raw in enumerate(batch_roots, 1):
        path = Path(raw).expanduser().resolve()
        batch_entries.append(
            {"batch_id": path.name, "root": str(path), "ordinal": index}
        )
    metadata = {
        "schema_version": "1.0.0",
        "campaign_id": root.name,
        "source": source,
        "source_revision": source_revision,
        "candidate_snapshot_hash": None,
        "batch_size": batch_size,
        "review_packet_max_cases": review_packet_max_cases,
        "review_packet_max_bytes": review_packet_max_bytes,
        "adjudication_packet_max_cases": adjudication_packet_max_cases,
        "adjudication_packet_max_bytes": adjudication_packet_max_bytes,
        "language_routing": language_routing,
        "languages": sorted(languages or []),
        "accounting": {},
        "batches": batch_entries,
    }
    write_json(root / "campaign.json", metadata)
    return metadata


def _read_candidate_rows(path: str | Path) -> list[dict]:
    target = Path(path)
    if target.suffix == ".jsonl":
        return read_jsonl(target)
    payload = read_json(target)
    if isinstance(payload, dict) and isinstance(payload.get("candidates"), list):
        return payload["candidates"]
    if isinstance(payload, list):
        return payload
    raise ValueError(
        "campaign candidate snapshot must be JSONL or a list/candidates object"
    )


def _case_id(row: dict, ordinal: int) -> str:
    value = row.get("case_id") or row.get("id") or row.get("source_id")
    return str(value) if value else f"case-{ordinal:06d}"


def _blind_case(row: dict) -> dict:
    return {
        key: row[key]
        for key in (
            "review_schema_version",
            "case_id",
            "reviewer_slot",
            "language",
            "locale",
            "input",
            "family_id",
            "annotation",
            "review",
            "review_guidance",
        )
        if key in row
    }


def campaign_fill(
    campaign: str | Path,
    *,
    candidates: str | Path,
    work_root: str | Path | None = None,
    source: str | None = None,
    source_revision: str | None = None,
    languages: list[str] | None = None,
) -> dict:
    """Fill a campaign once from an immutable candidate snapshot."""
    root = resolve_campaign_root(campaign, work_root)
    campaign_path = root / "campaign.json"
    metadata = read_json(campaign_path)
    rows = _read_candidate_rows(candidates)
    allowed_languages = set(languages or metadata.get("languages") or [])
    normalized = []
    for ordinal, raw in enumerate(rows, 1):
        if not isinstance(raw, dict):
            raise TypeError(f"candidate row {ordinal} must be an object")
        row = dict(raw)
        row["case_id"] = _case_id(row, ordinal)
        if allowed_languages and row.get("language") not in allowed_languages:
            continue
        normalized.append(row)
    normalized.sort(key=lambda row: str(row["case_id"]))
    digest = _rows_digest(normalized)
    if metadata.get("candidate_snapshot_hash") not in {None, digest}:
        raise ValueError(
            "campaign candidate snapshot hash does not match existing campaign"
        )
    if metadata.get("batches"):
        if metadata.get("candidate_snapshot_hash") == digest:
            return campaign_status(campaign, work_root=work_root)
        raise ValueError("campaign already contains batches")
    batch_size = int(metadata.get("batch_size", 1000))
    batch_entries = []
    batches_root = root / "batches"
    batches_root.mkdir(parents=True, exist_ok=True)
    for start in range(0, len(normalized), batch_size):
        batch_number = start // batch_size + 1
        batch_id = f"batch-{batch_number:04d}"
        batch_root = batches_root / batch_id
        if batch_root.exists():
            raise ValueError(f"campaign batch already exists: {batch_root}")
        batch_root.mkdir(parents=True)
        layout = BatchLayout(batch_root)
        cases = normalized[start : start + batch_size]
        contexts = [dict(row) for row in cases]
        blind_a = [_blind_case(row) for row in cases]
        blind_b = [_blind_case(row) for row in cases]
        write_jsonl(layout.cases, cases)
        write_jsonl(layout.context, contexts)
        write_jsonl(layout.review_blind("A"), blind_a)
        write_jsonl(layout.review_blind("B"), blind_b)
        write_json(
            layout.metadata,
            {
                "schema_version": "1.0.0",
                "batch_id": batch_id,
                "campaign_id": metadata.get("campaign_id", root.name),
                "state": "awaiting_review",
                "case_count": len(cases),
                "languages": sorted(
                    {row.get("language") for row in cases if row.get("language")}
                ),
            },
        )
        batch_entries.append(
            {"batch_id": batch_id, "root": str(batch_root), "ordinal": batch_number}
        )
    metadata["source"] = source or metadata.get("source")
    metadata["source_revision"] = source_revision or metadata.get("source_revision")
    metadata["candidate_snapshot_hash"] = digest
    metadata["languages"] = sorted(allowed_languages)
    metadata["accounting"] = {
        "observed": len(rows),
        "reviewable_unseen": len(normalized),
        "already_represented": len(rows) - len(normalized),
        "importer_excluded": 0,
        "unaccounted": 0,
    }
    metadata["batches"] = batch_entries
    write_json(campaign_path, metadata)
    return campaign_status(campaign, work_root=work_root)


def _batch_paths(entry: dict) -> BatchLayout:
    return BatchLayout(Path(entry["root"]))


def _count(path: Path) -> int:
    return len(read_jsonl(path)) if path.is_file() else 0


def _batch_status(entry: dict) -> dict:
    layout = _batch_paths(entry)
    metadata = read_json(layout.metadata) if layout.metadata.is_file() else {}
    cases = _count(layout.cases)
    review_a = _count(layout.review_complete("A"))
    review_b = _count(layout.review_complete("B"))
    review_check = (
        read_json(layout.review_check) if layout.review_check.is_file() else {}
    )
    decisions = _count(layout.adjudication_decisions)
    return {
        "batch_id": entry.get("batch_id", layout.root.name),
        "root": str(layout.root),
        "state": metadata.get("state"),
        "cases": cases,
        "languages": metadata.get("languages", []),
        "review_a": review_a,
        "review_b": review_b,
        "review_ready": bool(review_check.get("ready")),
        "adjudicated": decisions,
        "finalized": bool(
            metadata.get("state") == "finalized" or layout.integration_summary.is_file()
        ),
    }


def campaign_status(
    campaign: str | Path, *, work_root: str | Path | None = None
) -> dict:
    root = resolve_campaign_root(campaign, work_root)
    metadata = read_json(root / "campaign.json")
    batches = [_batch_status(entry) for entry in metadata.get("batches", [])]
    totals = {
        "batches": len(batches),
        "cases": 0,
        "review_a": 0,
        "review_b": 0,
        "adjudicated": 0,
        "review_ready": 0,
        "finalized": 0,
    }
    for batch in batches:
        for key in ("cases", "review_a", "review_b", "adjudicated"):
            totals[key] += batch[key]
        totals["review_ready"] += int(batch["review_ready"])
        totals["finalized"] += int(batch["finalized"])
    complete = bool(batches) and totals["finalized"] == totals["batches"]
    return {
        "campaign_id": metadata.get("campaign_id", root.name),
        "root": str(root),
        "source": metadata.get("source"),
        "source_revision": metadata.get("source_revision"),
        "candidate_snapshot_hash": metadata.get("candidate_snapshot_hash"),
        "accounting": metadata.get("accounting", {}),
        "batches": batches,
        "totals": totals,
        "complete": complete,
    }


def _available_languages(rows: list[dict]) -> list[str]:
    return sorted({row.get("language") for row in rows if row.get("language")})


def _select_language(rows: list[dict], *, enabled: bool) -> str | None:
    if not enabled:
        return None
    languages = _available_languages(rows)
    return languages[0] if languages else None


def campaign_next(
    campaign: str | Path,
    role: str,
    *,
    work_root: str | Path | None = None,
    out: str | Path | None = None,
) -> dict | None:
    if role not in ROLES:
        raise ValueError(f"role must be one of {sorted(ROLES)}")
    root = resolve_campaign_root(campaign, work_root)
    metadata = read_json(root / "campaign.json")
    for entry in sorted(
        metadata.get("batches", []), key=lambda item: item.get("ordinal", 0)
    ):
        layout = _batch_paths(entry)
        if not layout.cases.is_file():
            continue
        cases = read_jsonl(layout.cases)
        if not cases:
            continue
        enabled = bool(metadata.get("language_routing", False))
        if role in {"review-a", "review-b"}:
            slot = "A" if role == "review-a" else "B"
            blind = layout.review_blind(slot)
            completed = layout.review_complete(slot)
            if not blind.is_file():
                continue
            blind_rows = read_jsonl(blind)
            completed_rows = read_jsonl(completed) if completed.is_file() else []
            language = _select_language(
                [
                    row
                    for row in blind_rows
                    if row.get("case_id")
                    not in {item.get("case_id") for item in completed_rows}
                ],
                enabled=enabled,
            )
            if language:
                blind_rows = [
                    row for row in blind_rows if row.get("language") == language
                ]
                completed_rows = [
                    row for row in completed_rows if row.get("language") == language
                ]
            rows = review_packet_rows(
                blind_rows,
                completed_rows,
                max_cases=metadata.get("review_packet_max_cases", 200),
                max_bytes=metadata.get("review_packet_max_bytes", 98304),
            )
            template = "templates/reviewer-ab-task.md"
        else:
            review_check = (
                read_json(layout.review_check) if layout.review_check.is_file() else {}
            )
            review_a = (
                read_jsonl(layout.review_complete("A"))
                if layout.review_complete("A").is_file()
                else []
            )
            review_b = (
                read_jsonl(layout.review_complete("B"))
                if layout.review_complete("B").is_file()
                else []
            )
            if not review_check.get("ready"):
                review_check = check_reviews(cases, review_a, review_b)
            if not review_check.get("ready"):
                continue
            decisions = (
                read_jsonl(layout.adjudication_decisions)
                if layout.adjudication_decisions.is_file()
                else []
            )
            contexts = read_jsonl(layout.context) if layout.context.is_file() else cases
            remaining = [
                row
                for row in cases
                if row.get("case_id") not in {item.get("case_id") for item in decisions}
            ]
            language = _select_language(remaining, enabled=enabled)
            if language:
                cases_for_packet = [
                    row for row in cases if row.get("language") == language
                ]
                contexts = [row for row in contexts if row.get("language") == language]
                review_a = [row for row in review_a if row.get("language") == language]
                review_b = [row for row in review_b if row.get("language") == language]
                decisions = [
                    row for row in decisions if row.get("language") == language
                ]
            else:
                cases_for_packet = cases
            rows = adjudication_packet_rows(
                cases_for_packet,
                contexts,
                review_a,
                review_b,
                decisions,
                max_cases=metadata.get("adjudication_packet_max_cases", 100),
                max_bytes=metadata.get("adjudication_packet_max_bytes", 98304),
            )
            template = "templates/adjudicator-task.md"
        if not rows:
            continue
        packet_path = (
            Path(out) if out else root / "packets" / role / f"{entry['batch_id']}.jsonl"
        )
        write_jsonl(packet_path, rows)
        return {
            "campaign_id": metadata.get("campaign_id", root.name),
            "role": role,
            "batch_id": entry["batch_id"],
            "packet": str(packet_path),
            "template": template,
            "cases": len(rows),
            "language": language,
            "rows": rows,
        }
    return None


def _campaign_entry(metadata: dict, batch_id: str | None) -> dict:
    entries = metadata.get("batches", [])
    if batch_id:
        for entry in entries:
            if entry.get("batch_id") == batch_id:
                return entry
        raise ValueError(f"unknown campaign batch: {batch_id}")
    for entry in sorted(entries, key=lambda item: item.get("ordinal", 0)):
        return entry
    raise ValueError("campaign has no batches")


def campaign_merge(
    campaign: str | Path,
    role: str,
    result: str | Path,
    *,
    batch_id: str | None = None,
    work_root: str | Path | None = None,
) -> dict:
    if role not in ROLES:
        raise ValueError(f"role must be one of {sorted(ROLES)}")
    root = resolve_campaign_root(campaign, work_root)
    metadata = read_json(root / "campaign.json")
    entry = _campaign_entry(metadata, batch_id)
    layout = _batch_paths(entry)
    result_rows = read_jsonl(result)
    if role in {"review-a", "review-b"}:
        slot = "A" if role == "review-a" else "B"
        blind_rows = read_jsonl(layout.review_blind(slot))
        complete_path = layout.review_complete(slot)
        existing = read_jsonl(complete_path) if complete_path.is_file() else []
        merged = merge_review_rows(
            blind_rows,
            existing,
            result_rows,
            slot=slot,
            output=complete_path,
        )
    else:
        cases = read_jsonl(layout.cases)
        review_a = read_jsonl(layout.review_complete("A"))
        review_b = read_jsonl(layout.review_complete("B"))
        review = check_reviews(cases, review_a, review_b)
        if not review["ready"]:
            raise ValueError("adjudication requires complete independent A/B reviews")
        output_path = layout.adjudication_decisions
        existing = read_jsonl(output_path) if output_path.is_file() else []
        merged = merge_adjudication_rows(existing, result_rows, output=output_path)
    return {
        "campaign_id": metadata.get("campaign_id", root.name),
        "role": role,
        "batch_id": entry["batch_id"],
        "rows": len(merged),
    }


def campaign_finalize(
    campaign: str | Path,
    *,
    corpus: str | Path,
    retry_pool: str | Path | None = None,
    work_root: str | Path | None = None,
    write: bool = False,
) -> dict:
    root = resolve_campaign_root(campaign, work_root)
    metadata = read_json(root / "campaign.json")
    results = []
    for entry in metadata.get("batches", []):
        layout = _batch_paths(entry)
        if not layout.cases.is_file():
            continue
        from .workflow import batch_preflight, finalize_batch

        preflight = batch_preflight(layout.root, Path(corpus))
        if not preflight.get("ready_to_finalize"):
            continue
        results.append(
            finalize_batch(
                layout.root,
                Path(corpus),
                Path(retry_pool) if retry_pool else None,
                write=write,
            )
        )
    status = campaign_status(campaign, work_root=work_root)
    return {
        "campaign_id": status["campaign_id"],
        "finalized": len(results),
        "results": results,
        "status": status,
    }
