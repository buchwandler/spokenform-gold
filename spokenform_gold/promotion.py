from __future__ import annotations

from collections import Counter
from copy import deepcopy
from typing import Any

from .oracle import oracle_hash
from .source_manifest import normalize_materialization_policy
from .taxonomy import source_manifest_map
from .validation import REVIEWED_STATUSES, validate_records

PROMOTION_DECISIONS = {
    "promote_curated",
    "promote_upstream",
    "keep_external",
    "reject",
    "quarantine",
    "needs_review",
}
PROMOTABLE_DECISIONS = {"promote_curated", "promote_upstream"}
PROMOTABLE_STATUSES = REVIEWED_STATUSES | {"no_change"}


def _decision_error(message: str) -> ValueError:
    return ValueError(f"promotion rejected: {message}")


def _review_metadata(decision: dict) -> dict[str, Any]:
    return {
        "reviewers": list(decision.get("reviewers", [])),
        "adjudicator": decision.get("adjudicator"),
        "license_disposition": decision.get("license_disposition"),
    }


def _source_for_decision(
    candidate: dict,
    decision: dict,
    *,
    source_manifests: dict[str, dict],
) -> dict:
    disposition = decision["decision"]
    if disposition == "promote_upstream":
        source = deepcopy(candidate.get("source", {}))
        benchmark = source.get("benchmark")
        if benchmark not in source_manifests:
            raise _decision_error(
                f"candidate {candidate['id']} references unknown source {benchmark!r}"
            )
        manifest = source_manifests[benchmark]
        policy = normalize_materialization_policy(manifest)
        if policy != "embedded_public" or manifest.get("redistribution_status") != "allowed":
            raise _decision_error(
                f"source {benchmark!r} is not permitted for embedded upstream promotion"
            )
        return source

    manifest = source_manifests.get("spokenform_curated")
    if manifest is None:
        raise _decision_error("spokenform_curated source manifest is missing")
    source = {
        "benchmark": "spokenform_curated",
        "source_id": decision.get("record_id", candidate["id"]),
        "source_version": manifest["revision"],
        "source_url": manifest["source_url"],
        "license": manifest["license"],
        "review": _review_metadata(decision),
    }
    upstream_refs = decision.get("upstream_refs", [])
    if upstream_refs:
        source["informed_by"] = deepcopy(upstream_refs)
    return source


def _record_from_decision(
    candidate: dict,
    decision: dict,
    *,
    source_manifests: dict[str, dict],
) -> dict:
    record = deepcopy(candidate)
    record.pop("_source_file", None)
    record.pop("_source_line", None)
    for key in (
        "input",
        "expected_output",
        "units",
        "negative_for",
        "notes",
        "language",
        "locale",
        "schema_version",
        "taxonomy_version",
        "policy_version",
    ):
        if key in decision:
            record[key] = deepcopy(decision[key])
    record["id"] = decision.get("record_id", candidate["id"])
    record["family_id"] = decision["family_id"]
    record["status"] = decision["status"]
    record["split"] = "candidate"
    record["source"] = _source_for_decision(
        candidate, decision, source_manifests=source_manifests
    )
    record["oracle"] = deepcopy(decision["oracle"])
    record["review"] = {
        "protocol_version": decision.get("review_protocol_version", "1.0.0"),
        "status": "adjudicated",
        "reviewers": list(decision["reviewers"]),
        "adjudicator": decision["adjudicator"],
        "decision": decision["decision"],
        "disagreement": deepcopy(decision.get("disagreement", {})),
        "source_error_codes": list(decision.get("source_error_codes", [])),
    }
    record["oracle_hash"] = oracle_hash(record)
    if "notes" not in decision:
        record["notes"] = (
            f"Promoted after independent review of candidate {candidate['id']}."
        )
    return record


def _validate_decision_shape(decision: dict) -> None:
    required = {"candidate_id", "decision", "reviewers", "adjudicator", "family_id"}
    missing = sorted(key for key in required if key not in decision)
    if missing:
        raise _decision_error(
            f"decision for {decision.get('candidate_id', '?')} is missing {missing}"
        )
    if decision["decision"] not in PROMOTION_DECISIONS:
        raise _decision_error(
            f"decision for {decision['candidate_id']} has invalid disposition "
            f"{decision['decision']!r}"
        )
    if not isinstance(decision["reviewers"], list) or len(decision["reviewers"]) < 2:
        raise _decision_error(
            f"decision for {decision['candidate_id']} requires two independent reviewers"
        )
    if not all(isinstance(item, str) and item for item in decision["reviewers"]):
        raise _decision_error(
            f"decision for {decision['candidate_id']} has invalid reviewers"
        )
    if not isinstance(decision["adjudicator"], str) or not decision["adjudicator"]:
        raise _decision_error(
            f"decision for {decision['candidate_id']} requires an adjudicator"
        )
    if decision["decision"] in PROMOTABLE_DECISIONS:
        if not isinstance(decision["family_id"], str) or not decision["family_id"]:
            raise _decision_error(
                f"decision for {decision['candidate_id']} requires a family_id"
            )
        if decision.get("status") not in PROMOTABLE_STATUSES:
            raise _decision_error(
                f"decision for {decision['candidate_id']} has invalid promoted status "
                f"{decision.get('status')!r}"
            )
        for key in ("input", "expected_output", "units", "negative_for", "notes", "oracle"):
            if key not in decision:
                raise _decision_error(
                    f"promoted decision for {decision['candidate_id']} is missing {key}"
                )
        if not isinstance(decision.get("license_disposition"), str) or not decision[
            "license_disposition"
        ]:
            raise _decision_error(
                f"promoted decision for {decision['candidate_id']} requires license_disposition"
            )


def build_promoted_records(
    candidates: list[dict],
    decisions: list[dict],
    existing_records: list[dict],
    *,
    source_manifests: dict[str, dict] | None = None,
) -> tuple[list[dict], dict]:
    manifests = source_manifests or source_manifest_map()
    candidate_map: dict[str, dict] = {}
    for candidate in candidates:
        candidate_id = candidate.get("id")
        if not isinstance(candidate_id, str) or not candidate_id:
            raise _decision_error("candidate is missing a valid id")
        if candidate_id in candidate_map:
            raise _decision_error(f"duplicate candidate id {candidate_id}")
        candidate_map[candidate_id] = candidate

    decision_map: dict[str, dict] = {}
    for decision in decisions:
        _validate_decision_shape(decision)
        candidate_id = decision["candidate_id"]
        if candidate_id not in candidate_map:
            raise _decision_error(f"decision references unknown candidate {candidate_id}")
        if candidate_id in decision_map:
            raise _decision_error(f"duplicate decision for candidate {candidate_id}")
        decision_map[candidate_id] = decision

    missing = sorted(set(candidate_map) - set(decision_map))
    if missing:
        raise _decision_error(f"missing decisions for candidates {missing}")

    existing_ids = {record.get("id") for record in existing_records}
    existing_families = {record.get("family_id") for record in existing_records}
    promoted: list[dict] = []
    dispositions = Counter()
    for candidate_id in sorted(candidate_map):
        candidate = candidate_map[candidate_id]
        decision = decision_map[candidate_id]
        disposition = decision["decision"]
        dispositions[disposition] += 1
        if disposition not in PROMOTABLE_DECISIONS:
            continue
        record = _record_from_decision(
            candidate, decision, source_manifests=manifests
        )
        family_records = [
            item
            for item in existing_records
            if item.get("family_id") == record["family_id"]
        ]
        if any(
            item.get("language") != record.get("language")
            or item.get("locale") != record.get("locale")
            for item in family_records
        ):
            raise _decision_error(
                f"family conflict for {record['family_id']}: language or locale differs"
            )
        if record["id"] in existing_ids:
            raise _decision_error(f"resulting record id already exists: {record['id']}")
        if any(item.get("id") == record["id"] for item in promoted):
            raise _decision_error(f"duplicate resulting record id: {record['id']}")
        promoted.append(record)

    validation_errors = validate_records(promoted, source_manifests=manifests)
    if validation_errors:
        raise _decision_error("promoted records are invalid: " + "; ".join(validation_errors))

    promoted.sort(key=lambda record: record["id"])
    report = {
        "candidates": len(candidates),
        "decisions": len(decisions),
        "promoted": len(promoted),
        "promoted_curated": dispositions.get("promote_curated", 0),
        "promoted_upstream": dispositions.get("promote_upstream", 0),
        "kept_external": dispositions.get("keep_external", 0),
        "rejected": dispositions.get("reject", 0),
        "quarantine": dispositions.get("quarantine", 0),
        "needs_review": dispositions.get("needs_review", 0),
        "new_families": sorted(
            {record["family_id"] for record in promoted} - existing_families
        ),
        "existing_families": sorted(
            {record["family_id"] for record in promoted} & existing_families
        ),
        "languages": dict(sorted(Counter(record["language"] for record in promoted).items())),
        "sources": dict(
            sorted(
                Counter(record["source"]["benchmark"] for record in promoted).items()
            )
        ),
        "license_dispositions": dict(
            sorted(
                Counter(
                    decision.get("license_disposition", "not_applicable")
                    for decision in decisions
                ).items()
            )
        ),
        "record_ids": [record["id"] for record in promoted],
    }
    return promoted, report
