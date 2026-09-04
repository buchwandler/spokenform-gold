"""Deterministic orchestration across bounded semantic-review batches."""

from __future__ import annotations

from pathlib import Path

from .io import read_json, read_jsonl, write_json, write_jsonl
from .packets import adjudication_packet_rows, review_packet_rows
from .work_layout import BatchLayout
from .workflow import check_reviews

ROLES = {"review-a", "review-b", "adjudicator"}


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
) -> dict:
    if batch_size < 1 or batch_size > 1000:
        raise ValueError("batch_size must be between 1 and 1000")
    root = resolve_campaign_root(campaign, work_root)
    if root.exists() and any(root.iterdir()):
        raise ValueError(f"campaign root must be new or empty: {root}")
    if batch_roots is None and work_root is not None:
        batch_roots = (
            sorted(
                path
                for path in (Path(work_root) / "batches").iterdir()
                if path.is_dir()
            )
            if (Path(work_root) / "batches").is_dir()
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
        "batch_size": batch_size,
        "review_packet_max_cases": review_packet_max_cases,
        "review_packet_max_bytes": review_packet_max_bytes,
        "adjudication_packet_max_cases": adjudication_packet_max_cases,
        "adjudication_packet_max_bytes": adjudication_packet_max_bytes,
        "batches": batch_entries,
    }
    write_json(root / "campaign.json", metadata)
    return metadata


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
        "batches": batches,
        "totals": totals,
        "complete": complete,
    }


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
        if role in {"review-a", "review-b"}:
            slot = "A" if role == "review-a" else "B"
            blind = layout.review_blind(slot)
            completed = layout.review_complete(slot)
            if not blind.is_file():
                continue
            rows = review_packet_rows(
                read_jsonl(blind),
                read_jsonl(completed) if completed.is_file() else [],
                max_cases=metadata.get("review_packet_max_cases", 200),
                max_bytes=metadata.get("review_packet_max_bytes", 98304),
            )
            template = "templates/reviewer-ab-task.md"
        else:
            review_check = (
                read_json(layout.review_check) if layout.review_check.is_file() else {}
            )
            if not review_check.get("ready"):
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
                review_check = check_reviews(cases, review_a, review_b)
            if not review_check.get("ready"):
                continue
            decisions = (
                read_jsonl(layout.adjudication_decisions)
                if layout.adjudication_decisions.is_file()
                else []
            )
            contexts = read_jsonl(layout.context) if layout.context.is_file() else cases
            rows = adjudication_packet_rows(
                cases,
                contexts,
                read_jsonl(layout.review_complete("A")),
                read_jsonl(layout.review_complete("B")),
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
            "rows": rows,
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

    return None
