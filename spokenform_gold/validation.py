from __future__ import annotations

from collections import Counter, defaultdict

from .semantics import validate_semantic
from .taxonomy import ambiguity_map, categories_set, policies_map, source_manifest_map


STATUSES = {
    "gold",
    "multi_valid",
    "policy_choice",
    "ambiguous",
    "quarantine",
    "no_change",
}
SPLITS = {"train", "dev", "test", "challenge", "judge_gold", "candidate"}
REVIEWED_STATUSES = {"gold", "multi_valid", "policy_choice"}


def _norm_text(value: str) -> str:
    return " ".join(value.split()).casefold()


def load_categories(path=None) -> set[str]:
    return categories_set(path)


def _validate_versions(record: dict, prefix: str, errors: list[str]) -> None:
    for key in ("schema_version", "taxonomy_version", "policy_version"):
        value = record.get(key)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{prefix}: missing version field {key}")


def _validate_source(
    record: dict, prefix: str, source_manifests: dict[str, dict], errors: list[str]
) -> None:
    source = record.get("source")
    if not isinstance(source, dict):
        errors.append(f"{prefix}: source must be an object")
        return
    benchmark = source.get("benchmark")
    source_id = source.get("source_id")
    source_version = source.get("source_version")
    source_url = source.get("source_url")
    if not isinstance(benchmark, str) or not benchmark:
        errors.append(f"{prefix}: source.benchmark is required")
        return
    if not isinstance(source_id, str) or not source_id:
        errors.append(f"{prefix}: source.source_id is required")
    if not isinstance(source_version, str) or not source_version:
        errors.append(f"{prefix}: source.source_version is required")
    if not isinstance(source_url, str) or not source_url:
        errors.append(f"{prefix}: source.source_url is required")
    manifest = source_manifests.get(benchmark)
    if manifest is None:
        errors.append(f"{prefix}: unknown source benchmark {benchmark!r}")
        return
    if source_version and source_version != manifest.get("revision"):
        errors.append(
            f"{prefix}: source_version {source_version!r} does not match manifest revision {manifest.get('revision')!r}"
        )
    license_name = source.get("license")
    if not isinstance(license_name, str) or not license_name:
        errors.append(f"{prefix}: source.license is required")
    elif manifest.get("license") and license_name != manifest.get("license"):
        errors.append(
            f"{prefix}: source.license {license_name!r} does not match manifest license {manifest.get('license')!r}"
        )
    if (
        source_url
        and manifest.get("source_url")
        and source_url != manifest.get("source_url")
    ):
        errors.append(
            f"{prefix}: source.source_url {source_url!r} does not match manifest source_url {manifest.get('source_url')!r}"
        )
    if source.get("upstream_expected") is not None and not isinstance(
        source.get("upstream_expected"), str
    ):
        errors.append(f"{prefix}: source.upstream_expected must be string when present")
    if benchmark != "spokenform_curated":
        source_hash = source.get("source_hash")
        if not isinstance(source_hash, str) or not source_hash.startswith("sha256:"):
            errors.append(f"{prefix}: imported records require source.source_hash")


def _validate_unit(
    record: dict,
    unit: dict,
    *,
    index: int,
    categories: set[str],
    policies: dict,
    ambiguities: dict,
    errors: list[str],
) -> None:
    prefix = f"line {record.get('_source_line', '?')} ({record.get('id', '?')}): unit[{index}]"
    required = (
        "surface",
        "start",
        "end",
        "category",
        "semantic",
        "policy",
        "canonical",
        "accepted",
        "rejected",
        "features",
    )
    for key in required:
        if key not in unit:
            errors.append(f"{prefix}: missing field {key}")

    category = unit.get("category")
    if category not in categories:
        errors.append(f"{prefix}: unknown category {category!r}")

    policy = unit.get("policy")
    if not isinstance(policy, str) or policy not in policies:
        errors.append(f"{prefix}: unknown policy {policy!r}")

    surface = unit.get("surface")
    start = unit.get("start")
    end = unit.get("end")
    text = record.get("input", "")
    if not isinstance(surface, str) or not surface:
        errors.append(f"{prefix}: surface must be non-empty string")
    if not isinstance(start, int) or not isinstance(end, int):
        errors.append(f"{prefix}: start/end must be integers")
    elif text[start:end] != surface:
        errors.append(f"{prefix}: start/end do not select surface")

    semantic = unit.get("semantic")
    if not isinstance(semantic, dict):
        errors.append(f"{prefix}: semantic must be an object")
    elif semantic or record.get("status") in REVIEWED_STATUSES | {"ambiguous"}:
        for message in validate_semantic(category, semantic):
            errors.append(f"{prefix}: {message}")

    accepted = unit.get("accepted")
    rejected = unit.get("rejected")
    canonical = unit.get("canonical")
    if not isinstance(accepted, list) or not all(
        isinstance(item, str) for item in accepted
    ):
        errors.append(f"{prefix}: accepted must be list[str]")
        accepted = []
    if not isinstance(rejected, list) or not all(
        isinstance(item, str) for item in rejected
    ):
        errors.append(f"{prefix}: rejected must be list[str]")
        rejected = []

    if record.get("status") in REVIEWED_STATUSES:
        if not isinstance(canonical, str) or not canonical.strip():
            errors.append(f"{prefix}: canonical required for reviewed record")
        elif _norm_text(canonical) not in {_norm_text(item) for item in accepted}:
            errors.append(f"{prefix}: canonical must appear in accepted")
    if record.get("status") == "ambiguous" and canonical is not None:
        errors.append(f"{prefix}: ambiguous units must not set canonical")

    overlap = {_norm_text(item) for item in accepted} & {
        _norm_text(item) for item in rejected
    }
    if overlap:
        errors.append(f"{prefix}: accepted/rejected overlap: {sorted(overlap)}")

    features = unit.get("features")
    if not isinstance(features, dict):
        errors.append(f"{prefix}: features must be object")
    else:
        ambiguity_family = features.get("ambiguity_family")
        if ambiguity_family is not None:
            family = ambiguities.get(ambiguity_family)
            if family is None:
                errors.append(
                    f"{prefix}: unknown ambiguity family {ambiguity_family!r}"
                )
            elif category not in family.get("categories", []):
                errors.append(
                    f"{prefix}: ambiguity family {ambiguity_family!r} does not allow category {category!r}"
                )

    if record.get("source", {}).get("benchmark") != "spokenform_curated":
        source_category = unit.get("source_category")
        mapping_status = unit.get("mapping_status")
        if not isinstance(source_category, str) or not source_category:
            errors.append(f"{prefix}: imported units require source_category")
        if mapping_status not in {
            "exact",
            "broader",
            "narrower",
            "ambiguous",
            "unsupported",
        }:
            errors.append(f"{prefix}: imported units require valid mapping_status")


def validate_records(
    records,
    *,
    judge: bool = False,
    categories=None,
    policies=None,
    ambiguities=None,
    source_manifests=None,
):
    errors = []
    ids = Counter(record.get("id") for record in records)
    for record_id, count in ids.items():
        if record_id and count > 1:
            errors.append(f"duplicate id: {record_id} ({count} records)")

    categories = categories if categories is not None else categories_set()
    policies = policies if policies is not None else policies_map()
    ambiguities = ambiguities if ambiguities is not None else ambiguity_map()
    source_manifests = (
        source_manifests if source_manifests is not None else source_manifest_map()
    )

    if judge:
        for record in records:
            prefix = f"line {record.get('_source_line', '?')} ({record.get('id', '?')})"
            for key in (
                "id",
                "input",
                "candidate",
                "human_label",
                "reason",
                "category",
                "language",
                "locale",
                "schema_version",
                "taxonomy_version",
            ):
                if key not in record:
                    errors.append(f"{prefix}: missing judge field {key}")
            if record.get("human_label") not in {"accept", "reject"}:
                errors.append(f"{prefix}: human_label must be accept/reject")
            if record.get("category") not in categories:
                errors.append(f"{prefix}: unknown category {record.get('category')!r}")
            if not isinstance(record.get("expected_semantic"), dict):
                errors.append(f"{prefix}: expected_semantic must be object")
            else:
                for message in validate_semantic(
                    record.get("category"), record.get("expected_semantic")
                ):
                    errors.append(f"{prefix}: {message}")
        return errors

    for record in records:
        prefix = f"line {record.get('_source_line', '?')} ({record.get('id', '?')})"
        required = (
            "id",
            "language",
            "locale",
            "split",
            "family_id",
            "status",
            "input",
            "expected_output",
            "source",
            "units",
            "negative_for",
            "notes",
        )
        for key in required:
            if key not in record:
                errors.append(f"{prefix}: missing field {key}")

        _validate_versions(record, prefix, errors)

        status = record.get("status")
        split = record.get("split")
        if status not in STATUSES:
            errors.append(f"{prefix}: invalid status {status!r}")
        if split not in SPLITS:
            errors.append(f"{prefix}: invalid split {split!r}")
        if not isinstance(record.get("input"), str):
            errors.append(f"{prefix}: input must be a string")
        if not isinstance(record.get("units"), list):
            errors.append(f"{prefix}: units must be a list")
            continue
        if not isinstance(record.get("negative_for"), list) or not all(
            isinstance(item, str) for item in record.get("negative_for", [])
        ):
            errors.append(f"{prefix}: negative_for must be list[str]")
        if not isinstance(record.get("notes"), str):
            errors.append(f"{prefix}: notes must be a string")

        _validate_source(record, prefix, source_manifests, errors)

        if status == "no_change":
            if record.get("units"):
                errors.append(f"{prefix}: no_change records must not contain units")
            if record.get("expected_output") != record.get("input"):
                errors.append(f"{prefix}: no_change expected_output must equal input")
            if not record.get("negative_for"):
                errors.append(f"{prefix}: no_change requires negative_for")
        elif status in REVIEWED_STATUSES:
            if not isinstance(record.get("expected_output"), str):
                errors.append(f"{prefix}: reviewed records require expected_output")
        elif (
            status in {"ambiguous", "quarantine"}
            and record.get("expected_output") is not None
        ):
            errors.append(
                f"{prefix}: ambiguous/quarantine records must use null expected_output"
            )

        for index, unit in enumerate(record.get("units", [])):
            if not isinstance(unit, dict):
                errors.append(f"{prefix}: unit[{index}] must be an object")
                continue
            _validate_unit(
                record,
                unit,
                index=index,
                categories=categories,
                policies=policies,
                ambiguities=ambiguities,
                errors=errors,
            )

    family_splits = defaultdict(set)
    for record in records:
        family_id = record.get("family_id")
        split = record.get("split")
        if family_id and split not in {"candidate", "judge_gold"}:
            family_splits[family_id].add(split)
    for family_id, splits in family_splits.items():
        if len(splits) > 1:
            errors.append(
                f"family leakage: {family_id} appears in splits {sorted(splits)}"
            )
    return errors
