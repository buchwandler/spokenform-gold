from __future__ import annotations

from collections import Counter, defaultdict

from .oracle import (
    COMPARISON_PROFILE,
    canonical_unit_reconstruction,
    interpretation_semantic_key,
    normalize_text,
    oracle_hash,
)
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
    return normalize_text(value)


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
    check_surface: bool = True,
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
    elif check_surface and text[start:end] != surface:
        errors.append(f"{prefix}: start/end do not select surface")

    semantic = unit.get("semantic")
    if not isinstance(semantic, dict):
        errors.append(f"{prefix}: semantic must be an object")
    elif semantic or record.get("status") in REVIEWED_STATUSES | {"ambiguous"}:
        for message in validate_semantic(category, semantic):
            errors.append(f"{prefix}: {message}")
        if (
            record.get("status") == "ambiguous"
            and category == "date"
            and unit.get("mapping_status") == "ambiguous"
        ):
            candidates = semantic.get("candidates")
            if not isinstance(candidates, list) or len(candidates) < 2:
                errors.append(
                    f"{prefix}: ambiguous date unit requires at least two semantic candidates"
                )

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

    source = record.get("source") or {}
    if not source and record.get("source_observations"):
        source = record.get("source_observations")[0] or {}
    if source.get("benchmark") != "spokenform_curated":
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
    if not judge and any("split" not in record for record in records):
        return validate_v2_records(
            records,
            categories=categories,
            policies=policies,
            ambiguities=ambiguities,
            source_manifests=source_manifests,
        )
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
            ambiguity_family = record.get("ambiguity_family")
            if ambiguity_family is not None:
                family = ambiguities.get(ambiguity_family)
                if family is None:
                    errors.append(
                        f"{prefix}: unknown ambiguity_family {ambiguity_family!r}"
                    )
                elif record.get("category") not in family.get("categories", []):
                    errors.append(
                        f"{prefix}: ambiguity_family {ambiguity_family!r} does not "
                        f"allow category {record.get('category')!r}"
                    )
        return errors

    for record in records:
        prefix = f"line {record.get('_source_line', '?')} ({record.get('id', '?')})"
        materialization = record.get("materialization", "embedded")
        if materialization not in {"embedded", "external_ref"}:
            errors.append(f"{prefix}: invalid materialization {materialization!r}")
            continue
        required = (
            "id",
            "language",
            "locale",
            "split",
            "family_id",
            "status",
            "source",
        )
        if materialization == "embedded":
            required += ("input", "expected_output", "units", "negative_for", "notes")
            effective = record
            check_surface = True
        else:
            required += ("annotation",)
            annotation = record.get("annotation")
            if not isinstance(annotation, dict):
                errors.append(f"{prefix}: external_ref annotation must be an object")
                effective = record
            else:
                for key in ("expected_output", "units", "negative_for", "notes"):
                    if key not in annotation:
                        errors.append(f"{prefix}: annotation missing field {key}")
                effective = dict(record)
                effective.update(annotation)
                effective["input"] = ""
            if "input" not in record or record.get("input") is not None:
                errors.append(f"{prefix}: external_ref input must be null")
            source = record.get("source")
            if (
                not isinstance(source, dict)
                or not isinstance(source.get("source_artifact"), str)
                or not source.get("source_artifact")
            ):
                errors.append(
                    f"{prefix}: external_ref source.source_artifact is required"
                )
            check_surface = False
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
        if materialization == "embedded" and not isinstance(record.get("input"), str):
            errors.append(f"{prefix}: input must be a string")
        if not isinstance(effective.get("units"), list):
            errors.append(f"{prefix}: units must be a list")
            continue
        if not isinstance(effective.get("negative_for"), list) or not all(
            isinstance(item, str) for item in effective.get("negative_for", [])
        ):
            errors.append(f"{prefix}: negative_for must be list[str]")
        if not isinstance(effective.get("notes"), str):
            errors.append(f"{prefix}: notes must be a string")
        _validate_source(record, prefix, source_manifests, errors)
        expected_output = effective.get("expected_output")
        if status == "no_change":
            if effective.get("units"):
                errors.append(f"{prefix}: no_change records must not contain units")
            if materialization == "embedded" and expected_output != record.get("input"):
                errors.append(f"{prefix}: no_change expected_output must equal input")
            if not effective.get("negative_for"):
                errors.append(f"{prefix}: no_change requires negative_for")
        elif status in REVIEWED_STATUSES:
            if not isinstance(expected_output, str):
                errors.append(f"{prefix}: reviewed records require expected_output")
        elif status in {"ambiguous", "quarantine"} and expected_output is not None:
            errors.append(
                f"{prefix}: ambiguous/quarantine records must use null expected_output"
            )

        oracle = effective.get("oracle")
        oracle_required = status in REVIEWED_STATUSES | {"no_change", "ambiguous"}
        if oracle_required and split != "candidate":
            if not isinstance(oracle, dict):
                errors.append(f"{prefix}: reviewed records require an oracle object")
            else:
                canonical_output = oracle.get("canonical_output")
                accepted_outputs = oracle.get("accepted_outputs")
                rejected_outputs = oracle.get("rejected_outputs")
                variant_mode = oracle.get("variant_mode")
                if not isinstance(accepted_outputs, list) or not all(
                    isinstance(item, str) for item in accepted_outputs
                ):
                    errors.append(
                        f"{prefix}: oracle.accepted_outputs must be list[str]"
                    )
                    accepted_outputs = []
                if not isinstance(rejected_outputs, list) or not all(
                    isinstance(item, dict)
                    and isinstance(item.get("output"), str)
                    and isinstance(item.get("reason"), str)
                    for item in rejected_outputs
                ):
                    errors.append(
                        f"{prefix}: oracle.rejected_outputs must contain output/reason objects"
                    )
                    rejected_outputs = []
                if variant_mode != "explicit":
                    errors.append(
                        f"{prefix}: oracle.variant_mode must be explicit for release-eligible records"
                    )
                normalized_accepted = [_norm_text(item) for item in accepted_outputs]
                if len(normalized_accepted) != len(set(normalized_accepted)):
                    errors.append(
                        f"{prefix}: oracle.accepted_outputs contains duplicates"
                    )
                overlap = set(normalized_accepted) & {
                    _norm_text(item["output"]) for item in rejected_outputs
                }
                if overlap:
                    errors.append(
                        f"{prefix}: oracle accepted/rejected overlap: {sorted(overlap)}"
                    )
                if status in REVIEWED_STATUSES:
                    if not isinstance(canonical_output, str):
                        errors.append(
                            f"{prefix}: reviewed oracle canonical_output must be a string"
                        )
                    elif expected_output != canonical_output:
                        errors.append(
                            f"{prefix}: expected_output must equal oracle.canonical_output"
                        )
                    if isinstance(canonical_output, str) and _norm_text(
                        canonical_output
                    ) not in set(normalized_accepted):
                        errors.append(
                            f"{prefix}: oracle canonical_output must appear in accepted_outputs"
                        )
                    reconstructed = canonical_unit_reconstruction(effective)
                    if (
                        check_surface
                        and isinstance(canonical_output, str)
                        and reconstructed != canonical_output
                    ):
                        errors.append(
                            f"{prefix}: canonical unit reconstruction does not equal oracle.canonical_output"
                        )
                elif status == "no_change":
                    if canonical_output != effective.get("input"):
                        errors.append(
                            f"{prefix}: no_change oracle.canonical_output must equal input"
                        )
                    if accepted_outputs != [effective.get("input")]:
                        errors.append(
                            f"{prefix}: no_change oracle.accepted_outputs must equal [input]"
                        )
                elif status == "ambiguous":
                    interpretations = oracle.get("interpretations")
                    if canonical_output is not None:
                        errors.append(
                            f"{prefix}: ambiguous oracle canonical_output must be null"
                        )
                    if accepted_outputs:
                        errors.append(
                            f"{prefix}: ambiguous oracle accepted_outputs must be empty"
                        )
                    if (
                        not isinstance(interpretations, list)
                        or len(interpretations) < 2
                    ):
                        errors.append(
                            f"{prefix}: ambiguous oracle requires at least two interpretations"
                        )
                    else:
                        semantic_keys = set()
                        for interpretation in interpretations:
                            if not isinstance(interpretation, dict):
                                errors.append(
                                    f"{prefix}: oracle interpretation must be an object"
                                )
                                continue
                            semantic = interpretation.get("semantic")
                            outputs = interpretation.get("accepted_outputs")
                            if not isinstance(semantic, dict):
                                errors.append(
                                    f"{prefix}: interpretation semantic must be an object"
                                )
                            else:
                                semantic_keys.add(interpretation_semantic_key(semantic))
                            if (
                                not isinstance(outputs, list)
                                or not outputs
                                or not all(isinstance(item, str) for item in outputs)
                            ):
                                errors.append(
                                    f"{prefix}: interpretation requires accepted_outputs"
                                )
                        if len(semantic_keys) < 2:
                            errors.append(
                                f"{prefix}: ambiguous interpretation semantics must differ"
                            )
                stored_hash = effective.get("oracle_hash")
                if (
                    check_surface
                    and stored_hash is not None
                    and stored_hash != oracle_hash(effective)
                ):
                    errors.append(
                        f"{prefix}: oracle_hash does not match semantic oracle assertion"
                    )
                comparison_profile = oracle.get(
                    "comparison_profile", COMPARISON_PROFILE
                )
                if comparison_profile != COMPARISON_PROFILE:
                    errors.append(
                        f"{prefix}: unsupported oracle comparison_profile {comparison_profile!r}"
                    )
        for index, unit in enumerate(effective.get("units", [])):
            if not isinstance(unit, dict):
                errors.append(f"{prefix}: unit[{index}] must be an object")
                continue
            _validate_unit(
                effective,
                unit,
                index=index,
                categories=categories,
                policies=policies,
                ambiguities=ambiguities,
                errors=errors,
                check_surface=check_surface,
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


def validate_v2_records(
    records,
    *,
    categories=None,
    policies=None,
    ambiguities=None,
    source_manifests=None,
) -> list[str]:
    """Validate sentence-centric v2 corpus records without split state."""
    errors: list[str] = []
    categories = categories if categories is not None else categories_set()
    policies = policies if policies is not None else policies_map()
    ambiguities = ambiguities if ambiguities is not None else ambiguity_map()
    source_manifests = (
        source_manifests if source_manifests is not None else source_manifest_map()
    )
    ids = Counter(record.get("id") for record in records)
    for record_id, count in ids.items():
        if record_id and count > 1:
            errors.append(f"duplicate id: {record_id} ({count} records)")
    identities: dict[tuple[str, str, str], str] = {}
    for record in records:
        prefix = f"line {record.get('_source_line', '?')} ({record.get('id', '?')})"
        for key in (
            "schema_version",
            "taxonomy_version",
            "policy_version",
            "id",
            "language",
            "locale",
            "family_id",
            "status",
            "input",
            "oracle",
            "units",
            "negative_for",
            "source_observations",
        ):
            if key not in record:
                errors.append(f"{prefix}: missing field {key}")
        if record.get("schema_version") != "2.0.0":
            errors.append(f"{prefix}: v2 records require schema_version 2.0.0")
        if not isinstance(record.get("input"), str):
            errors.append(f"{prefix}: input must be a string")
        if record.get("status") not in STATUSES - {"quarantine"}:
            errors.append(f"{prefix}: invalid v2 status {record.get('status')!r}")
        if not isinstance(record.get("family_id"), str) or not record.get("family_id"):
            errors.append(f"{prefix}: family_id is required")
        source_observations = record.get("source_observations")
        if not isinstance(source_observations, list) or not source_observations:
            errors.append(f"{prefix}: source_observations must be a non-empty list")
            source_observations = []
        seen_sources: set[str] = set()
        for index, source in enumerate(source_observations):
            source_prefix = f"{prefix}: source_observations[{index}]"
            if not isinstance(source, dict):
                errors.append(f"{source_prefix}: source observation must be an object")
                continue
            benchmark = source.get("benchmark")
            if not isinstance(benchmark, str) or not benchmark:
                errors.append(f"{source_prefix}: benchmark is required")
                continue
            source_id = source.get("source_id")
            source_version = source.get("source_version")
            if not isinstance(source_id, str) or not source_id:
                errors.append(f"{source_prefix}: source_id is required")
            if not isinstance(source_version, str) or not source_version:
                errors.append(f"{source_prefix}: source_version is required")
            key = f"{benchmark}+{source_version}+{source_id}"
            if key in seen_sources:
                errors.append(f"{source_prefix}: duplicate source observation {key}")
            seen_sources.add(key)
            manifest = source_manifests.get(benchmark)
            if manifest is None:
                errors.append(
                    f"{source_prefix}: unknown source benchmark {benchmark!r}"
                )
            elif source_version != manifest.get("revision") and source_version:
                errors.append(
                    f"{source_prefix}: source_version does not match manifest revision"
                )
        if not isinstance(record.get("input"), str):
            continue
        identity = (
            record.get("language", ""),
            record.get("locale", ""),
            " ".join(record["input"].split()),
        )
        if identity in identities and identities[identity] != record.get("id"):
            errors.append(
                f"{prefix}: duplicate sentence identity also used by {identities[identity]}"
            )
        identities[identity] = record.get("id", "")
        oracle = record.get("oracle")
        if not isinstance(oracle, dict):
            continue
        status = record.get("status")
        accepted = oracle.get("accepted_outputs")
        rejected = oracle.get("rejected_outputs")
        canonical = oracle.get("canonical_output")
        if not isinstance(accepted, list) or not all(
            isinstance(item, str) for item in accepted
        ):
            errors.append(f"{prefix}: oracle.accepted_outputs must be list[str]")
            accepted = []
        if not isinstance(rejected, list) or not all(
            isinstance(item, dict)
            and isinstance(item.get("output"), str)
            and isinstance(item.get("reason"), str)
            for item in rejected
        ):
            errors.append(
                f"{prefix}: oracle.rejected_outputs must contain output/reason objects"
            )
            rejected = []
        accepted_norm = {_norm_text(item) for item in accepted}
        rejected_norm = {_norm_text(item["output"]) for item in rejected}
        if accepted_norm & rejected_norm:
            errors.append(f"{prefix}: oracle accepted/rejected overlap")
        if status == "ambiguous":
            if canonical is not None or accepted:
                errors.append(
                    f"{prefix}: ambiguous oracle must have null canonical and empty accepted_outputs"
                )
        elif status == "no_change":
            if canonical != record.get("input") or accepted != [record.get("input")]:
                errors.append(f"{prefix}: no_change oracle must preserve input")
            if record.get("units") != [] or not record.get("negative_for"):
                errors.append(f"{prefix}: no_change requires no units and negative_for")
        else:
            if (
                not isinstance(canonical, str)
                or _norm_text(canonical) not in accepted_norm
            ):
                errors.append(
                    f"{prefix}: canonical_output must occur in accepted_outputs"
                )
            reconstructed = canonical_unit_reconstruction(record)
            if reconstructed != canonical:
                errors.append(
                    f"{prefix}: canonical unit reconstruction does not equal oracle.canonical_output"
                )
        if oracle.get("variant_mode") != "explicit":
            errors.append(f"{prefix}: oracle.variant_mode must be explicit")
        stored_hash = record.get("oracle_hash")
        if stored_hash is not None and stored_hash != oracle_hash(record):
            errors.append(
                f"{prefix}: oracle_hash does not match semantic oracle assertion"
            )
        units = record.get("units")
        if not isinstance(units, list):
            errors.append(f"{prefix}: units must be a list")
            continue
        for index, unit in enumerate(units):
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
                check_surface=True,
            )
    return errors
