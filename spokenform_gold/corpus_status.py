"""Compact status views for canonical Gold and derived release artifacts."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .gold_audit import audit_records
from .io import read_records
from .source_manifest import (
    build_source_materialization_census,
    normalize_materialization_policy,
)


def canonical_corpus_hash(records: Iterable[dict]) -> str:
    """Return a stable hash of canonical records, independent of shard order."""
    payload = "\n".join(
        json.dumps(
            {key: value for key, value in record.items() if not key.startswith("_")},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        for record in sorted(records, key=lambda row: row.get("id", ""))
    )
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _fallback_release_partition(records: list[dict], source_manifest: dict) -> dict:
    """Conservatively estimate release modes for status-only reporting.

    The authoritative planner lives in :mod:`spokenform_gold.release`; this
    fallback keeps status useful when no preflight artifact has been generated.
    """
    source_map = {
        source.get("name"): source
        for source in source_manifest.get("sources", [])
        if isinstance(source, dict) and isinstance(source.get("name"), str)
    }
    counts = Counter()
    blockers = Counter()
    for record in records:
        observations = record.get("source_observations") or [record.get("source", {})]
        if not observations:
            mode, reason = "blocked", "missing_source_observation"
        else:
            policies = []
            mode = "embedded"
            reason = None
            for observation in observations:
                if not isinstance(observation, dict):
                    mode, reason = "blocked", "invalid_source_observation"
                    break
                name = observation.get("benchmark")
                source = source_map.get(name)
                if source is None:
                    mode, reason = "blocked", "unknown_source"
                    break
                if not source.get("release_ready", False):
                    mode, reason = "blocked", "source_policy_unresolved"
                    break
                policy = normalize_materialization_policy(source)
                policies.append(policy)
                materialization = observation.get(
                    "materialization", record.get("materialization", "embedded")
                )
                if materialization == "external_ref" or policy == "external_ref_only":
                    mode = "external_ref"
                if materialization not in {"embedded", "external_ref"}:
                    mode, reason = "blocked", "invalid_materialization"
                    break
                if materialization == "embedded" and policy != "embedded_public":
                    mode, reason = "blocked", "embedding_not_authorized"
                    break
                if policy in {"importer_only", "review_required"}:
                    mode, reason = "blocked", "source_policy_unresolved"
                    break
            if mode != "blocked" and not any(
                policy in {"embedded_public", "external_ref_only"}
                for policy in policies
            ):
                mode, reason = "blocked", "source_policy_unresolved"
        counts[mode] += 1
        if reason:
            blockers[reason] += 1
    return {
        "embedded": counts["embedded"],
        "external_ref": counts["external_ref"],
        "blocked": counts["blocked"],
        "blockers": dict(sorted(blockers.items())),
    }


def build_corpus_status(
    records: Iterable[dict],
    *,
    source_manifest: dict | None = None,
    retry_backlog: int = 0,
    release_partition: dict | None = None,
) -> dict[str, Any]:
    """Build a compact, machine-readable canonical/release status report."""
    record_list = list(records)
    audit = audit_records(record_list, strict=True)
    source_manifest = source_manifest or {"sources": []}
    partition = release_partition or _fallback_release_partition(
        record_list, source_manifest
    )
    status_counts = dict(
        sorted(Counter(record.get("status") for record in record_list).items())
    )
    return {
        "canonical": len(record_list),
        "canonical_corpus_records": len(record_list),
        "canonical_corpus_hash": canonical_corpus_hash(record_list),
        "review_complete": audit["review_complete_records"],
        "review_complete_records": audit["review_complete_records"],
        "review_gaps": len(audit["review_gap_records"]),
        "review_gap_records": audit["review_gap_records"],
        "retry_backlog": int(retry_backlog),
        "release_embedded": int(partition.get("embedded", 0)),
        "release_external_ref": int(partition.get("external_ref", 0)),
        "release_blocked": int(partition.get("blocked", 0)),
        "release_blockers": partition.get("blockers", {}),
        "local_benchmark_records": len(record_list),
        "status_counts": status_counts,
        "source_census": build_source_materialization_census(
            record_list, source_manifest
        ),
        "audit": audit,
    }


def load_corpus_status(
    corpus_root: str | Path, *, source_manifest: dict | None = None
) -> dict[str, Any]:
    """Load canonical shards and return :func:`build_corpus_status`."""
    return build_corpus_status(
        read_records([corpus_root]), source_manifest=source_manifest
    )
