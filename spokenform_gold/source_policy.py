"""Source-level public redistribution policy workflow.

This module intentionally operates on source revisions and bounded evidence, not
on individual corpus rows.  Recommendations remain distinct from maintainer
authorization until an approved decision is applied.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Iterable
from copy import deepcopy
from pathlib import Path
from typing import Any

from .io import read_json, sha256_file, write_json
from .source_manifest import (
    build_source_materialization_census,
    normalize_materialization_policy,
)

DECISION_SCHEMA_VERSION = "1.0.0"
DECISIONS = {
    "embedded_public",
    "external_ref_only",
    "exclude_public",
    "needs_human_legal_review",
}


def _digest_payload(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def source_manifest_hash(manifest: dict) -> str:
    return _digest_payload(manifest)


def decision_hash(decision: dict) -> str:
    payload = {key: value for key, value in decision.items() if key != "decision_hash"}
    return _digest_payload(payload)


def _decision_rows(decisions: dict | list | None) -> list[dict]:
    if decisions is None:
        return []
    if isinstance(decisions, dict) and isinstance(decisions.get("decisions"), list):
        decisions = decisions["decisions"]
    if isinstance(decisions, dict):
        decisions = list(decisions.values())
    if not isinstance(decisions, list) or not all(
        isinstance(row, dict) for row in decisions
    ):
        raise TypeError(
            "source decisions must be a list or an object containing decisions"
        )
    return list(decisions)


def _evidence_hashes(evidence: Iterable[str | Path], *, root: Path) -> list[dict]:
    result = []
    for raw_path in evidence:
        path = Path(raw_path)
        if not path.is_absolute():
            path = root / path
        if not path.is_file():
            raise ValueError(f"license evidence file does not exist: {path}")
        result.append(
            {
                "kind": "file",
                "locator": str(path),
                "sha256": "sha256:" + sha256_file(path),
            }
        )
    return result


def make_source_decision(
    source: dict,
    *,
    decision: str,
    manifest_hash: str,
    evidence: Iterable[str | Path] = (),
    reviewer_a: dict | None = None,
    reviewer_b: dict | None = None,
    adjudication: dict | None = None,
    maintainer_approval: dict | None = None,
    root: str | Path = ".",
) -> dict:
    if decision not in DECISIONS:
        raise ValueError(f"decision must be one of {sorted(DECISIONS)}")
    payload = {
        "schema_version": DECISION_SCHEMA_VERSION,
        "source": source.get("name"),
        "source_revision": source.get("revision"),
        "manifest_hash": manifest_hash,
        "decision": decision,
        "allowed_materializations": (
            ["embedded", "external_ref"]
            if decision == "embedded_public"
            else ["external_ref"]
            if decision == "external_ref_only"
            else []
        ),
        "license_evidence": _evidence_hashes(evidence, root=Path(root)),
        "attribution_requirements": [],
        "review_a": reviewer_a,
        "review_b": reviewer_b,
        "adjudication": adjudication,
        "maintainer_approval": maintainer_approval,
    }
    payload["decision_hash"] = decision_hash(payload)
    return payload


def validate_source_decision(
    decision: dict,
    source: dict,
    *,
    manifest_hash: str,
    repo_root: str | Path = ".",
    require_approval: bool = True,
) -> list[str]:
    errors = []
    if decision.get("schema_version") != DECISION_SCHEMA_VERSION:
        errors.append("unsupported source decision schema_version")
    if decision.get("source") != source.get("name"):
        errors.append("decision source does not match manifest source")
    if decision.get("source_revision") != source.get("revision"):
        errors.append("stale source revision")
    if decision.get("manifest_hash") != manifest_hash:
        errors.append("stale source manifest hash")
    if decision.get("decision") not in DECISIONS:
        errors.append("invalid source policy decision")
    allowed = decision.get("allowed_materializations")
    if not isinstance(allowed, list) or any(
        value not in {"embedded", "external_ref"} for value in allowed
    ):
        errors.append("invalid allowed_materializations")
    if decision.get("decision") == "embedded_public" and set(allowed or ()) != {
        "embedded",
        "external_ref",
    }:
        errors.append("embedded_public must allow embedded and external_ref")
    if decision.get("decision") == "external_ref_only" and set(allowed or ()) != {
        "external_ref"
    }:
        errors.append("external_ref_only must allow external_ref")
    if decision.get("decision_hash") != decision_hash(decision):
        errors.append("decision hash mismatch")
    evidence = decision.get("license_evidence", [])
    if not isinstance(evidence, list) or not evidence:
        errors.append("license evidence is required")
    else:
        root = Path(repo_root)
        for item in evidence:
            if not isinstance(item, dict) or not isinstance(item.get("sha256"), str):
                errors.append("license evidence entries must contain sha256")
                continue
            locator = item.get("locator")
            if isinstance(locator, str):
                path = Path(locator)
                if not path.is_absolute():
                    path = root / path
                if path.is_file() and "sha256:" + sha256_file(path) != item["sha256"]:
                    errors.append(f"license evidence hash mismatch: {locator}")
    for key in ("review_a", "review_b"):
        value = decision.get(key)
        if value is not None and (
            not isinstance(value, dict) or not value.get("reviewer_id")
        ):
            errors.append(f"{key} must contain reviewer_id")
    a = decision.get("review_a") or {}
    b = decision.get("review_b") or {}
    if (
        a.get("result")
        and b.get("result")
        and a.get("result") != b.get("result")
        and not isinstance(decision.get("adjudication"), dict)
    ):
        errors.append("conflicting A/B results require adjudication")
    approval = decision.get("maintainer_approval")
    if require_approval and (
        not isinstance(approval, dict)
        or approval.get("approved") is not True
        or not approval.get("actor")
    ):
        errors.append("maintainer approval is required")
    return errors


def build_source_policy_status(
    records: list[dict], manifest: dict, decisions: dict | list | None = None
) -> dict:
    source_map = {
        row.get("name"): row
        for row in manifest.get("sources", [])
        if isinstance(row, dict)
    }
    decision_map = {row.get("source"): row for row in _decision_rows(decisions)}
    census = build_source_materialization_census(records, manifest)
    rows = []
    counts = Counter()
    manifest_hash = source_manifest_hash(manifest)
    for source in sorted(source_map.values(), key=lambda row: row.get("name", "")):
        name = source.get("name")
        decision = decision_map.get(name)
        if decision:
            errors = validate_source_decision(
                decision, source, manifest_hash=manifest_hash, require_approval=False
            )
            state = (
                "approved"
                if not errors
                and (decision.get("maintainer_approval") or {}).get("approved") is True
                else "decision_pending"
            )
            if errors:
                state = "stale_or_invalid"
            proposed = decision.get("decision")
        else:
            state = "release_ready" if source.get("release_ready") else "unresolved"
            proposed = (
                normalize_materialization_policy(source)
                if source.get("release_ready")
                else None
            )
        affected = sum(
            row.get("records", 0)
            for row in census.get("groups", [])
            if row.get("benchmark") == name
        )
        counts[state] += 1
        rows.append(
            {
                "source": name,
                "revision": source.get("revision"),
                "records": affected,
                "state": state,
                "current_policy": normalize_materialization_policy(source),
                "proposed_decision": proposed,
            }
        )
    return {
        "schema_version": DECISION_SCHEMA_VERSION,
        "manifest_hash": manifest_hash,
        "sources": rows,
        "counts": dict(sorted(counts.items())),
        "source_count": len(rows),
    }


def build_source_policy_packet(
    source_name: str, slot: str, records: list[dict], manifest: dict
) -> dict:
    if slot not in {"A", "B"}:
        raise ValueError("source policy reviewer slot must be A or B")
    source = next(
        (row for row in manifest.get("sources", []) if row.get("name") == source_name),
        None,
    )
    if source is None:
        raise ValueError(f"unknown source: {source_name}")
    census = build_source_materialization_census(records, manifest)
    groups = [row for row in census["groups"] if row.get("benchmark") == source_name]
    return {
        "schema_version": DECISION_SCHEMA_VERSION,
        "packet_kind": "source_policy_review",
        "slot": slot,
        "source": deepcopy(source),
        "manifest_hash": source_manifest_hash(manifest),
        "source_census": groups,
        "instructions": "Extract facts from bounded evidence; do not grant redistribution authorization.",
    }


def apply_source_decision(
    manifest_path: str | Path, decision: dict, *, write: bool = False
) -> dict:
    manifest = read_json(manifest_path)
    source = next(
        (
            row
            for row in manifest.get("sources", [])
            if row.get("name") == decision.get("source")
        ),
        None,
    )
    if source is None:
        raise ValueError(
            f"decision source is not in manifest: {decision.get('source')}"
        )
    if source.get("source_policy_decision_hash") == decision.get("decision_hash"):
        return manifest
    errors = validate_source_decision(
        decision,
        source,
        manifest_hash=source_manifest_hash(manifest),
        repo_root=Path(manifest_path).resolve().parent.parent,
    )
    if errors:
        raise ValueError("source decision is not applicable: " + "; ".join(errors))
    updated = deepcopy(manifest)
    target = next(
        row for row in updated["sources"] if row.get("name") == decision["source"]
    )
    outcome = decision["decision"]
    target["release_ready"] = outcome in {"embedded_public", "external_ref_only"}
    if outcome == "embedded_public":
        target["materialization_policy"] = "embedded_public"
        target["redistribution_status"] = "allowed"
    elif outcome == "external_ref_only":
        target["materialization_policy"] = "external_ref_only"
        target["redistribution_status"] = "metadata_only"
    else:
        target["materialization_policy"] = "review_required"
        target["redistribution_status"] = "not_redistributable"
    target["source_policy_decision_hash"] = decision["decision_hash"]
    if write:
        write_json(manifest_path, updated)
    return updated
