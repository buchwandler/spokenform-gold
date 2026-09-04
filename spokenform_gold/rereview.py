"""Deterministic retry-pool and sentence-centric re-review helpers."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .corpus import corpus_identity_map, read_corpus, sentence_key, source_key
from .io import (
    read_json,
    read_jsonl,
    read_records,
    sha256_file,
    write_json,
    write_jsonl,
)
from .work_layout import BatchLayout

RETRY_POOL_SCHEMA_VERSION = "1.0.0"
RETRY_CONTEXT_SCHEMA_VERSION = "1.0.0"
REVIEW_BATCH_LIMIT = 1000
RETRY_STATES = {
    "needs_triage",
    "blocked",
    "ready",
    "in_retry_batch",
    "resolved",
    "terminal",
}
BLOCKER_CLASSES = {
    "semantic_schema",
    "taxonomy",
    "policy",
    "source_context",
    "source_quality",
    "licensing",
    "duplicate",
    "review_conflict",
    "other",
}
KNOWN_MIGRATION_BATCHES = {"batch-0014", "batch-0015"}
LEGACY_UNRESOLVED_BLOCKER_MIGRATION_BATCHES = {"batch-0016"}


@dataclass(frozen=True)
class RetryPoolSummary:
    total_unique: int
    needs_triage: int
    blocked: int
    ready: int
    in_retry_batch: int
    resolved: int
    terminal: int
    duplicate_failure_events: int
    blockers: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _public(row: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if not key.startswith("_")}


def _digest(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def retry_context_fingerprint(context: Mapping[str, Any] | None) -> str:
    """Hash the capability/policy context used to make a retry meaningful."""

    value = dict(context or {})
    return _digest(
        {
            "schema_version": value.get("schema_version"),
            "taxonomy_version": value.get("taxonomy_version"),
            "policy_version": value.get("policy_version"),
            "resolution_id": value.get("resolution_id"),
            "guidance": value.get("guidance", value.get("review_guidance")),
            "guidance_hash": value.get("guidance_hash"),
            "additional_context_hash": value.get("additional_context_hash"),
            "capabilities": value.get("capabilities"),
        }
    )


# Descriptive aliases for callers using the terminology from the brief.
retry_context_hash = retry_context_fingerprint
context_fingerprint = retry_context_fingerprint


def retryable_blocker(blocker: Any) -> bool:
    return isinstance(blocker, Mapping) and blocker.get("retryable") is True


def _normalise_blocker(blocker: Any) -> dict[str, Any] | None:
    if not isinstance(blocker, Mapping):
        return None
    result = dict(blocker)
    for key in ("code", "class", "reason", "attempted_resolution"):
        if not isinstance(result.get(key), str) or not result[key].strip():
            return None
    if not isinstance(result.get("retryable"), bool):
        return None
    requires = result.get("requires", [])
    if not isinstance(requires, list) or not all(
        isinstance(item, str) and item.strip() for item in requires
    ):
        return None
    return result


def _legacy_blocker(
    batch_id: str, rationale: Any, case: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """Classify only the known reconstructed batches; never infer generally."""
    text = str(rationale or "").casefold()
    if batch_id in KNOWN_MIGRATION_BATCHES:
        input_text = str((case or {}).get("input", ""))
        if "corrupt" in text or "source_span_error" in text:
            pass
        elif ("repeat" in text and "decimal" in text) or (
            re.search(r"\d+\.\d+", input_text) and "…" in input_text
        ):
            return {
                "code": "semantic.decimal.repeating_not_supported",
                "class": "semantic_schema",
                "retryable": True,
                "reason": "Repeating-decimal semantics were not representable under the old schema.",
                "attempted_resolution": str(
                    rationale or "Legacy rationale classified during migration."
                ),
                "requires": ["capability:repeating-decimal-semantic-v1"],
            }
        elif "cannot be represented" in text or any(
            word in text for word in ("partial", "year-only", "month-year", "decade")
        ):
            return {
                "code": "semantic.date.partial_not_supported",
                "class": "semantic_schema",
                "retryable": True,
                "reason": "Partial-date semantics were not representable under the old schema.",
                "attempted_resolution": str(
                    rationale or "Legacy rationale classified during migration."
                ),
                "requires": ["capability:partial-date-semantic-v1"],
            }
    return {
        "code": "legacy.unclassified",
        "class": "other",
        "retryable": False,
        "reason": "Legacy exclusion has no structured blocker classification.",
        "attempted_resolution": str(rationale or "No recorded rationale."),
        "requires": [],
    }


def normalize_decision_blocker(
    *,
    batch_id: str,
    batch_kind: str,
    case: Mapping[str, Any] | None,
    decision: Mapping[str, Any],
    allow_legacy: bool,
) -> dict[str, Any] | None:
    """Return a validated blocker, migrating only explicitly known legacy rows."""
    blocker = _normalise_blocker(decision.get("blocker"))
    if blocker is not None:
        return blocker
    if not allow_legacy or decision.get("decision") != "unresolved":
        return None
    if batch_id in LEGACY_UNRESOLVED_BLOCKER_MIGRATION_BATCHES:
        rationale = str(decision.get("rationale") or "")
        return {
            "code": "legacy.unresolved.missing_structured_blocker",
            "class": "other",
            "retryable": True,
            "reason": "This case was adjudicated as unresolved before structured blockers became mandatory.",
            "attempted_resolution": rationale
            or "Historical unresolved decision migrated to the structured blocker contract.",
            "requires": [
                "triage:classify-blocker",
                "context:additional-review-guidance",
            ],
        }
    if batch_id in KNOWN_MIGRATION_BATCHES:
        return _legacy_blocker(batch_id, decision.get("rationale"), case)
    return None


def migrate_legacy_adjudication(
    batch_root: str | Path, *, write: bool = False
) -> dict[str, Any]:
    """Migrate only allowlisted unresolved decisions to the blocker contract."""
    layout = BatchLayout(batch_root)
    metadata = read_json(layout.metadata) if layout.metadata.is_file() else {}
    batch_id = str(metadata.get("batch_id", layout.root.name))
    decisions_path = layout.adjudication_decisions
    if not decisions_path.is_file():
        decisions_path = layout.legacy("adjudicated.jsonl")
    rows = read_jsonl(decisions_path) if decisions_path.is_file() else []
    changed_ids: list[str] = []
    migrated: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        if (
            item.get("decision") == "unresolved"
            and _normalise_blocker(item.get("blocker")) is None
        ):
            if batch_id not in LEGACY_UNRESOLVED_BLOCKER_MIGRATION_BATCHES:
                raise ValueError(
                    f"{batch_id}: unresolved decision has no structured blocker; historical migration is not allowed"
                )
            blocker = normalize_decision_blocker(
                batch_id=batch_id,
                batch_kind=str(metadata.get("batch_kind", "new_data")),
                case=None,
                decision=item,
                allow_legacy=True,
            )
            if blocker is None:
                raise ValueError(f"{batch_id}: legacy blocker migration failed")
            item["blocker"] = blocker
            changed_ids.append(str(item.get("case_id")))
        migrated.append(item)
    old_hash = sha256_file(decisions_path) if decisions_path.is_file() else None
    new_payload = json.dumps(
        [
            {key: value for key, value in row.items() if not key.startswith("_")}
            for row in migrated
        ],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    new_hash = (
        "sha256:" + hashlib.sha256((new_payload + "\n").encode("utf-8")).hexdigest()
    )
    manifest = {
        "schema_version": "1",
        "rule": "legacy-unresolved-missing-blocker-v1",
        "batch_id": batch_id,
        "rows": len(rows),
        "rows_changed": len(changed_ids),
        "changed_case_ids": sorted(changed_ids),
        "old_sha256": old_hash,
        "new_sha256": new_hash,
    }
    if write and changed_ids:
        decisions_path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(
            prefix=f".{decisions_path.name}.", dir=decisions_path.parent
        )
        os.close(fd)
        temporary = Path(name)
        try:
            write_jsonl(temporary, migrated)
            os.replace(temporary, decisions_path)
        finally:
            temporary.unlink(missing_ok=True)
        write_json(layout.adjudication_dir / "migration-manifest.json", manifest)
    return manifest


def _case_identity(case: Mapping[str, Any]) -> tuple[str, str, str]:
    return sentence_key(
        str(case.get("language", "")),
        str(case.get("locale", "")),
        case.get("input", "") if isinstance(case.get("input"), str) else "",
    )


def _event_hash(event: Mapping[str, Any]) -> str:
    return _digest({key: value for key, value in event.items() if key != "event_hash"})


def _event_from_decision(
    case: Mapping[str, Any],
    decision: Mapping[str, Any],
    batch_id: str,
    batch_root: Path,
    batch_kind: str = "new_data",
    *,
    allow_legacy: bool = True,
) -> dict[str, Any] | None:
    disposition = decision.get("decision")
    rationale = decision.get("rationale", "")
    if disposition == "accept":
        blocker = None
    elif disposition in {"unresolved", "exclude"}:
        blocker = normalize_decision_blocker(
            batch_id=batch_id,
            batch_kind=batch_kind,
            case=case,
            decision=decision,
            allow_legacy=allow_legacy,
        )
        if disposition == "unresolved" and blocker is None:
            raise ValueError(
                f"{case.get('case_id')}: unresolved decision requires retryable structured blocker"
            )
    else:
        return None
    event = {
        "batch_id": batch_id,
        "batch_root": str(batch_root),
        "batch_kind": batch_kind,
        "case_id": case.get("case_id"),
        "decision": disposition,
        "adjudicator_id": decision.get("adjudicator_id"),
        "decision_hash": _digest(_public(decision)),
        "rationale": rationale,
        "blocker": blocker,
        "schema_version": decision.get(
            "schema_version", case.get("schema_version", "2.0.0")
        ),
        "taxonomy_version": decision.get(
            "taxonomy_version", case.get("taxonomy_version")
        ),
        "policy_version": decision.get("policy_version", case.get("policy_version")),
    }
    event["event_hash"] = _event_hash(event)
    return event


def _empty_row(case: Mapping[str, Any], event: Mapping[str, Any]) -> dict[str, Any]:
    blocker = event.get("blocker")
    return {
        "schema_version": RETRY_POOL_SCHEMA_VERSION,
        "case_id": case.get("case_id"),
        "language": case.get("language", ""),
        "locale": case.get("locale", ""),
        "input": case.get("input", ""),
        "family_id": case.get("family_id"),
        "state": "blocked" if retryable_blocker(blocker) else "terminal",
        "retry_attempts": 0,
        "blocker": blocker,
        "origin_batches": [],
        "events": [],
        "latest_retry_context_hash": None,
        "active_retry_batch": None,
        "resolved_record_id": None,
    }


def _apply_event(row: dict[str, Any], event: Mapping[str, Any]) -> None:
    event_hash = event.get("event_hash") or _event_hash(event)
    if any(item.get("event_hash") == event_hash for item in row["events"]):
        return
    row["events"].append(dict(event))
    row["events"].sort(
        key=lambda item: (
            str(item.get("batch_id", "")),
            str(item.get("event_hash", "")),
        )
    )
    batch_id = event.get("batch_id")
    if isinstance(batch_id, str) and batch_id and batch_id not in row["origin_batches"]:
        row["origin_batches"].append(batch_id)
        row["origin_batches"].sort()
    if event.get("decision") == "accept":
        row["state"] = "resolved"
        row["resolved_record_id"] = event.get("record_id") or row.get(
            "resolved_record_id"
        )
        row["active_retry_batch"] = None
        return
    blocker = _normalise_blocker(event.get("blocker"))
    if (
        isinstance(blocker, Mapping)
        and blocker.get("code") == "legacy.unclassified"
        and isinstance(row.get("blocker"), Mapping)
        and row["blocker"].get("code") != "legacy.unclassified"
    ):
        return
    if blocker is not None:
        row["blocker"] = blocker
        row["state"] = (
            "needs_triage"
            if blocker.get("code") == "legacy.unclassified"
            else "blocked"
            if blocker.get("retryable")
            else "terminal"
        )
        row["active_retry_batch"] = None
        if blocker.get("retryable"):
            rereview_events = {
                item.get("batch_id")
                for item in row["events"]
                if item.get("batch_kind") == "rereview"
                and retryable_blocker(item.get("blocker"))
            }
            if rereview_events:
                row["retry_attempts"] = max(
                    int(row.get("retry_attempts", 0)), len(rereview_events)
                )
            if event.get("retry_context_hash"):
                row["latest_retry_context_hash"] = event["retry_context_hash"]
    elif event.get("decision") == "exclude":
        row["state"] = "needs_triage"


def merge_retry_events(
    existing: Iterable[Mapping[str, Any]], events: Iterable[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """Merge case-level retry events once, retaining duplicate-batch history."""

    indexed: dict[str, dict[str, Any]] = {}
    for raw in existing:
        row = _public(raw)
        case_id = row.get("case_id")
        if not isinstance(case_id, str) or not case_id:
            raise ValueError("retry pool row is missing case_id")
        if case_id in indexed:
            raise ValueError(f"duplicate retry pool case_id: {case_id}")
        row.setdefault("events", [])
        row.setdefault("origin_batches", [])
        indexed[case_id] = row
    for raw_event in events:
        event = _public(raw_event)
        case_id = event.get("case_id")
        if not isinstance(case_id, str) or not case_id:
            raise ValueError("retry event is missing case_id")
        row = indexed.get(case_id)
        if row is None:
            case = (
                event.get("case") if isinstance(event.get("case"), Mapping) else event
            )
            row = _empty_row(case, event)
            indexed[case_id] = row
        _apply_event(row, event)
    for row in indexed.values():
        row["origin_batches"] = sorted(set(row.get("origin_batches", [])))
        row["events"] = sorted(
            row.get("events", []),
            key=lambda item: (
                str(item.get("batch_id", "")),
                str(item.get("event_hash", "")),
            ),
        )
        row["schema_version"] = row.get("schema_version", RETRY_POOL_SCHEMA_VERSION)
    return [indexed[key] for key in sorted(indexed)]


def load_retry_pool(path: str | Path) -> list[dict[str, Any]]:
    target = Path(path)
    if not target.is_file():
        return []
    return read_jsonl(target)


def write_retry_pool_atomic(
    path: str | Path, rows: Iterable[Mapping[str, Any]]
) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    os.close(fd)
    temporary = Path(name)
    try:
        write_jsonl(temporary, rows)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def _batch_paths(batch_root: Path) -> tuple[Path, Path]:
    layout = BatchLayout(batch_root)
    cases = layout.cases if layout.cases.is_file() else batch_root / "cases.jsonl"
    decisions = (
        layout.adjudication_decisions
        if layout.adjudication_decisions.is_file()
        else batch_root / "adjudicated.jsonl"
    )
    return cases, decisions


def _batch_events(batch_root: Path) -> list[dict[str, Any]]:
    metadata_path = batch_root / "batch.json"
    metadata = read_json(metadata_path) if metadata_path.is_file() else {}
    batch_id = str(metadata.get("batch_id", batch_root.name))
    cases_path, decisions_path = _batch_paths(batch_root)
    if not cases_path.is_file() or not decisions_path.is_file():
        return []
    cases = read_jsonl(cases_path)
    decisions = read_jsonl(decisions_path)
    case_map: dict[str, dict[str, Any]] = {}
    for case in cases:
        case_id = case.get("case_id")
        if not isinstance(case_id, str) or case_id in case_map:
            raise ValueError(f"invalid or duplicate case_id in {batch_root}")
        case_map[case_id] = case
    decision_map: dict[str, dict[str, Any]] = {}
    for decision in decisions:
        case_id = decision.get("case_id")
        if not isinstance(case_id, str) or case_id in decision_map:
            raise ValueError(
                f"invalid or duplicate adjudication case_id in {batch_root}"
            )
        decision_map[case_id] = decision
    if set(case_map) != set(decision_map):
        raise ValueError(f"incomplete adjudication set in {batch_root}")
    events = []
    for case_id in sorted(case_map):
        event = _event_from_decision(
            case_map[case_id],
            decision_map[case_id],
            batch_id,
            batch_root,
            str(metadata.get("batch_kind", "new_data")),
        )
        if event is not None and decision_map[case_id].get("decision") != "accept":
            event["case"] = _public(case_map[case_id])
            events.append(event)
    return events


def _all_batch_roots(work_root: Path) -> list[Path]:
    batches = work_root / "batches"
    if not batches.is_dir():
        return []
    return sorted(
        (path for path in batches.iterdir() if (path / "batch.json").is_file()),
        key=lambda path: path.name,
    )


def _mark_corpus_resolved(rows: list[dict[str, Any]], corpus_path: str | Path) -> None:
    target = Path(corpus_path)
    if target.is_dir():
        records = read_corpus(target)
    elif target.is_file():
        records = read_records([target])
    else:
        records = []
    identities = corpus_identity_map(records)
    for row in rows:
        identity = sentence_key(
            row.get("language", ""), row.get("locale", ""), row.get("input", "")
        )
        record = identities.get(identity)
        if record is not None:
            row["state"] = "resolved"
            row["resolved_record_id"] = record.get("id")
            row["active_retry_batch"] = None


def rebuild_retry_pool(
    work_root: str | Path, corpus_path: str | Path
) -> dict[str, Any]:
    """Rebuild the retry index from complete, deterministic batch artifacts."""

    root = Path(work_root).expanduser().resolve()
    events: list[dict[str, Any]] = []
    for batch_root in _all_batch_roots(root):
        events.extend(_batch_events(batch_root))
    rows = merge_retry_events([], events)
    _mark_corpus_resolved(rows, corpus_path)
    duplicate_events = max(0, len(events) - len(rows))
    summary = retry_pool_summary(rows, duplicate_failure_events=duplicate_events)
    pool_path = root / "state" / "review-exclusions.jsonl"
    write_retry_pool_atomic(pool_path, rows)
    write_json(root / "state" / "review-exclusions.summary.json", summary.to_dict())
    return {**summary.to_dict(), "pool": str(pool_path)}


def retry_pool_summary(
    rows: Iterable[Mapping[str, Any]], *, duplicate_failure_events: int = 0
) -> RetryPoolSummary:
    values = list(rows)
    states = Counter(str(row.get("state", "needs_triage")) for row in values)
    blockers = Counter(
        str((row.get("blocker") or {}).get("code"))
        for row in values
        if isinstance(row.get("blocker"), Mapping)
        and (row.get("blocker") or {}).get("code")
    )
    return RetryPoolSummary(
        total_unique=len(values),
        needs_triage=states["needs_triage"],
        blocked=states["blocked"],
        ready=states["ready"],
        in_retry_batch=states["in_retry_batch"],
        resolved=states["resolved"],
        terminal=states["terminal"],
        duplicate_failure_events=duplicate_failure_events,
        blockers=dict(sorted(blockers.items())),
    )


def mark_retry_ready(
    row: Mapping[str, Any], retry_context: Mapping[str, Any]
) -> dict[str, Any]:
    """Return a copy made ready only when a retryable blocker has new context."""

    result = _public(row)
    blocker = _normalise_blocker(result.get("blocker"))
    if not retryable_blocker(blocker):
        return result
    context = dict(retry_context)
    context.setdefault("schema_version", RETRY_CONTEXT_SCHEMA_VERSION)
    result["retry_context"] = context
    result["retry_context_hash"] = retry_context_fingerprint(context)
    if result.get("retry_context_hash") != result.get("latest_retry_context_hash"):
        result["state"] = "ready"
    return result


def update_retry_readiness(
    rows: Iterable[Mapping[str, Any]], retry_context: Mapping[str, Any]
) -> list[dict[str, Any]]:
    return [mark_retry_ready(row, retry_context) for row in rows]


def retry_context_changed(row: Mapping[str, Any]) -> bool:
    current = row.get("retry_context_hash") or row.get("current_retry_context_hash")
    latest = row.get("latest_retry_context_hash")
    return current is None or latest is None or current != latest


def select_retry_cases(
    pool: Iterable[Mapping[str, Any]],
    *,
    limit: int,
    blocker_codes: set[str] | None = None,
    languages: set[str] | None = None,
) -> list[dict[str, Any]]:
    if limit < 0:
        raise ValueError("limit must not be negative")
    limit = min(limit, REVIEW_BATCH_LIMIT)
    blockers = blocker_codes or set()
    selected = []
    for raw in pool:
        row = _public(raw)
        if row.get("state") != "ready" or row.get("active_retry_batch"):
            continue
        if not retry_context_changed(row):
            continue
        blocker = row.get("blocker") or {}
        if not retryable_blocker(blocker):
            continue
        if blockers and blocker.get("code") not in blockers:
            continue
        if languages and row.get("language") not in languages:
            continue
        selected.append(row)
    selected.sort(
        key=lambda row: (
            str((row.get("blocker") or {}).get("code", "")),
            str(row.get("case_id", "")),
        )
    )
    return selected[:limit]


def _read_origin_cases(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    embedded = row.get("case")
    if isinstance(embedded, Mapping):
        cases.append(_public(embedded))
    roots = set()
    for event in row.get("events", []):
        if isinstance(event, Mapping) and isinstance(event.get("case"), Mapping):
            cases.append(_public(event["case"]))
        if isinstance(event, Mapping) and event.get("batch_root"):
            roots.add(str(event["batch_root"]))
    for root in sorted(roots):
        cases_path, _ = _batch_paths(Path(root))
        if cases_path.is_file():
            for case in read_jsonl(cases_path):
                if case.get("case_id") == row.get("case_id"):
                    cases.append(case)
    return cases


def _merge_case_sources(row: Mapping[str, Any]) -> dict[str, Any]:
    cases = _read_origin_cases(row)
    if not cases:
        case = {
            key: row.get(key)
            for key in ("case_id", "language", "locale", "input", "family_id")
        }
        case["source_observations"] = list(row.get("source_observations", []))
        cases = [case]
    identity = None
    family = None
    observations: dict[str, dict[str, Any]] = {}
    first = cases[0]
    for case in cases:
        current_identity = _case_identity(case)
        if identity is None:
            identity = current_identity
        elif current_identity != identity:
            raise ValueError(
                f"case_id identity collision during retry: {row.get('case_id')}"
            )
        if case.get("case_id") != row.get("case_id"):
            raise ValueError(
                f"case_id mismatch during retry reconstruction: {row.get('case_id')}"
            )
        if case.get("family_id"):
            if family is None:
                family = case["family_id"]
            elif case["family_id"] != family:
                raise ValueError(
                    f"incompatible family_id during retry reconstruction: {row.get('case_id')}"
                )
        for observation in case.get("source_observations", []):
            if isinstance(observation, Mapping):
                observations[source_key(dict(observation))] = dict(observation)
    result = {
        key: first.get(key)
        for key in ("schema_version", "case_id", "language", "locale", "input")
    }
    result["schema_version"] = "2.0.0"
    result["case_id"] = row.get("case_id")
    result["family_id"] = family or row.get("family_id")
    result["source_observations"] = [observations[key] for key in sorted(observations)]
    return result


def build_rereview_batch(
    selected: Iterable[Mapping[str, Any]],
    *,
    work_root: str | Path,
    batch_id: str,
    corpus_path: str | Path,
) -> dict[str, Any]:
    """Materialize a deterministic re-review batch using the normal batch layout."""

    selected_rows = list(selected)
    if len(selected_rows) > REVIEW_BATCH_LIMIT:
        raise ValueError("re-review batch exceeds the 1,000-case logical limit")
    if not selected_rows:
        raise ValueError("re-review batch requires at least one selected case")
    layout = BatchLayout(Path(work_root).expanduser().resolve() / "batches" / batch_id)
    if layout.root.exists() and any(layout.root.iterdir()):
        raise ValueError(f"batch output root must be new or empty: {layout.root}")
    cases = [_merge_case_sources(row) for row in selected_rows]
    cases.sort(key=lambda row: row["case_id"])
    case_ids = [case["case_id"] for case in cases]
    if len(set(case_ids)) != len(case_ids):
        raise ValueError("duplicate case_id in re-review selection")
    contexts = []
    guidance_by_case: dict[str, dict[str, Any]] = {}
    resolution_ids = set()
    origin_batches = set()
    for row, case in zip(
        sorted(selected_rows, key=lambda item: str(item.get("case_id", ""))), cases
    ):
        retry_context = dict(row.get("retry_context") or {})
        resolution_id = retry_context.get("resolution_id")
        if resolution_id:
            resolution_ids.add(str(resolution_id))
        origin_batches.update(str(item) for item in row.get("origin_batches", []))
        guidance = (
            row.get("review_guidance")
            or retry_context.get("guidance")
            or retry_context.get("review_guidance")
        )
        if guidance:
            guidance_by_case[case["case_id"]] = dict(guidance)
        contexts.append(
            {
                "case_id": case["case_id"],
                "language": case["language"],
                "locale": case["locale"],
                "input": case["input"],
                "rereview": {
                    "attempt": int(row.get("retry_attempts", 0)) + 1,
                    "origin_batches": sorted(row.get("origin_batches", [])),
                    "prior_blockers": [
                        {
                            key: value
                            for key, value in (event.get("blocker") or {}).items()
                            if key in {"code", "class", "reason", "retryable"}
                        }
                        for event in row.get("events", [])
                        if isinstance(event, Mapping)
                        and isinstance(event.get("blocker"), Mapping)
                    ],
                    "resolution": retry_context,
                    "prior_review_hashes": row.get("prior_review_hashes", {}),
                },
            }
        )
    layout.root.mkdir(parents=True, exist_ok=True)
    write_jsonl(layout.cases, cases)
    write_jsonl(layout.context, contexts)
    from .collection import blind_case

    write_jsonl(
        layout.review_blind("A"),
        [
            blind_case(case, "A", guidance=guidance_by_case.get(case["case_id"]))
            for case in cases
        ],
    )
    write_jsonl(
        layout.review_blind("B"),
        [
            blind_case(case, "B", guidance=guidance_by_case.get(case["case_id"]))
            for case in cases
        ],
    )
    selection = {
        "schema_version": RETRY_POOL_SCHEMA_VERSION,
        "batch_id": batch_id,
        "case_ids": case_ids,
        "selection_hash": _digest(case_ids),
        "source_pool": str(
            Path(work_root).expanduser().resolve() / "state" / "review-exclusions.jsonl"
        ),
        "count": len(cases),
    }
    write_json(layout.source_dir / "retry-selection.json", selection)
    metadata = {
        "schema_version": "2.0.0",
        "batch_id": batch_id,
        "batch_kind": "rereview",
        "case_count": len(cases),
        "source_observation_count": sum(
            len(case.get("source_observations", [])) for case in cases
        ),
        "state": "awaiting_review",
        "rereview": {
            "source_pool": selection["source_pool"],
            "selection_hash": selection["selection_hash"],
            "resolution_ids": sorted(resolution_ids),
            "origin_batches": sorted(origin_batches),
            "attempt": max(
                int(row.get("retry_attempts", 0)) + 1 for row in selected_rows
            ),
        },
        "reviewer_a": None,
        "reviewer_b": None,
        "adjudicator": None,
    }
    write_json(layout.metadata, metadata)
    return metadata


__all__ = [
    "BLOCKER_CLASSES",
    "RETRY_POOL_SCHEMA_VERSION",
    "REVIEW_BATCH_LIMIT",
    "RetryPoolSummary",
    "build_rereview_batch",
    "context_fingerprint",
    "load_retry_pool",
    "mark_retry_ready",
    "merge_retry_events",
    "rebuild_retry_pool",
    "retry_context_changed",
    "retry_context_fingerprint",
    "retry_pool_summary",
    "select_retry_cases",
    "update_retry_readiness",
    "write_retry_pool_atomic",
]
