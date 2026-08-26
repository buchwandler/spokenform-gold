from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable
from pathlib import Path

from .corpus import find_identity_collisions
from .deduplication import normalize_for_fingerprint
from .io import sha256_text, write_json, write_jsonl


def _source_ref(record: dict) -> dict:
    source = record.get("source", {})
    return {
        "benchmark": source.get("benchmark"),
        "source_id": source.get("source_id"),
        "source_version": source.get("source_version"),
        "source_hash": source.get("source_hash"),
    }


def _census_row(record: dict, state: str = "candidate") -> dict:
    source = record.get("source", {})
    materialization = record.get("materialization", "embedded")
    input_value = record.get("input")
    fingerprint = (
        sha256_text(normalize_for_fingerprint(input_value))
        if isinstance(input_value, str)
        else None
    )
    return {
        "census_id": "sha256:"
        + sha256_text(
            "|".join(
                str(value or "")
                for value in (
                    source.get("benchmark"),
                    source.get("source_id"),
                    source.get("source_version"),
                    fingerprint,
                )
            )
        ),
        "source": source.get("benchmark"),
        "source_id": source.get("source_id"),
        "source_revision": source.get("source_version"),
        "language": record.get("language"),
        "locale": record.get("locale"),
        "source_hash": source.get("source_hash"),
        "materialization": materialization,
        "candidate_id": record.get("id"),
        "input_fingerprint": fingerprint,
        "state": state,
    }


def _exclusion_row(exclusion: dict) -> dict:
    source = exclusion.get("source") or exclusion.get("benchmark")
    source_id = exclusion.get("source_id") or exclusion.get("id")
    row = {
        "census_id": "sha256:"
        + sha256_text(
            "|".join(
                str(value or "")
                for value in (source, source_id, exclusion.get("reason"))
            )
        ),
        "source": source,
        "source_id": source_id,
        "source_revision": exclusion.get("source_version"),
        "language": exclusion.get("language"),
        "locale": exclusion.get("locale"),
        "source_hash": exclusion.get("source_hash"),
        "materialization": exclusion.get("materialization", "external_ref"),
        "state": "explicit_exclusion",
        "exclusion_reason": exclusion.get("reason", "unspecified"),
    }
    return row


def build_upstream_census(
    candidates: Iterable[dict],
    exclusions: Iterable[dict] = (),
    import_reports: Iterable[dict] = (),
) -> dict:
    candidate_rows = [
        _census_row(
            record,
            "metadata_only"
            if record.get("mapping_status") == "unsupported"
            else "candidate",
        )
        for record in candidates
    ]
    identity_collisions = find_identity_collisions(candidates)
    exclusion_rows = [_exclusion_row(item) for item in exclusions]
    rows = sorted(
        candidate_rows + exclusion_rows,
        key=lambda row: (
            row.get("source") or "",
            row.get("source_id") or "",
            row.get("census_id") or "",
        ),
    )
    reports = list(import_reports)
    observed = sum(int(report.get("source_rows", 0)) for report in reports)
    parsed = len(candidate_rows)
    explicit_exclusions = len(exclusion_rows)
    if observed == 0:
        observed = parsed + explicit_exclusions
    accounting_ok = observed == parsed + explicit_exclusions
    clusters = build_sentence_clusters(candidates)
    state_counts = Counter(row.get("state") for row in rows)
    summary = {
        "rows_observed": observed,
        "rows_parsed": parsed,
        "rows_candidate": state_counts.get("candidate", 0),
        "rows_metadata_only": state_counts.get("metadata_only", 0),
        "rows_excluded": explicit_exclusions,
        "rows_failed": sum(
            1 for item in exclusions if item.get("reason") in {"parse_error", "failed"}
        ),
        "rows_reviewed": sum(
            1
            for row in rows
            if row.get("state") in {"reviewed", "adjudicated", "release_ready"}
        ),
        "rows_adjudicated": sum(
            1 for row in rows if row.get("state") in {"adjudicated", "release_ready"}
        ),
        "rows_gold_eligible": sum(
            1 for row in rows if row.get("state") == "release_ready"
        ),
        "sentence_clusters": len(clusters),
        "identity_collision_count": len(identity_collisions),
        "row_accounting_ok": accounting_ok,
    }
    return {
        "rows": rows,
        "sentence_clusters": clusters,
        "identity_collisions": identity_collisions,
        "summary": summary,
    }


def build_sentence_clusters(records: Iterable[dict]) -> list[dict]:
    groups: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for record in records:
        key = (
            record.get("language", ""),
            record.get("locale", ""),
            normalize_for_fingerprint(record.get("input")),
        )
        groups[key].append(record)
    clusters = []
    for key, members in sorted(groups.items()):
        refs = sorted(
            {
                _ref_key(_source_ref(record)): _source_ref(record) for record in members
            }.values(),
            key=lambda item: (item.get("benchmark") or "", item.get("source_id") or ""),
        )
        expected = sorted(
            {
                record.get("source", {}).get("upstream_expected")
                for record in members
                if record.get("source", {}).get("upstream_expected") is not None
            }
        )
        clusters.append(
            {
                "sentence_oracle_id": "oracle-" + sha256_text("|".join(key)),
                "input_fingerprint": sha256_text(key[2]),
                "language": key[0],
                "locale": key[1],
                "normalized_input": key[2],
                "source_refs": refs,
                "upstream_expected_values": expected,
                "candidate_ids": sorted(record.get("id") for record in members),
            }
        )
    return clusters


def _ref_key(value: dict) -> tuple:
    return (
        value.get("benchmark"),
        value.get("source_id"),
        value.get("source_version"),
        value.get("source_hash"),
    )


def write_census_artifacts(work_root: str | Path, census: dict) -> dict:
    root = Path(work_root) / "census"
    root.mkdir(parents=True, exist_ok=True)
    rows_path = root / "upstream_rows.jsonl"
    clusters_path = root / "sentence_clusters.jsonl"
    summary_path = root / "summary.json"
    collisions_path = root / "identity_collisions.jsonl"
    write_jsonl(rows_path, census["rows"])
    write_jsonl(clusters_path, census["sentence_clusters"])
    write_jsonl(collisions_path, census.get("identity_collisions", []))
    write_json(summary_path, census["summary"])
    return {
        "rows": str(rows_path),
        "sentence_clusters": str(clusters_path),
        "identity_collisions": str(collisions_path),
        "summary": str(summary_path),
    }
