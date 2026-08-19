from __future__ import annotations

from collections import Counter
from typing import Any

from .evaluation_profiles import load_registry

REQUIRED_FIELDS = {
    "schema_version",
    "id",
    "family_id",
    "control",
    "language",
    "locale",
    "input",
    "source",
    "expectations",
    "notes",
}
REQUIRED_SOURCE_FIELDS = {
    "benchmark",
    "source_id",
    "source_version",
    "source_url",
    "license",
}
REQUIRED_EXPECTATION_FIELDS = {
    "profile_id",
    "expected_output",
    "required_rules",
    "forbidden_rules",
}


def validate_control_records(
    records: list[dict[str, Any]], *, registry_path: str | None = None
) -> list[str]:
    errors: list[str] = []
    profiles = load_registry(registry_path).get("profiles", {})
    ids = Counter(record.get("id") for record in records)
    for record_id, count in ids.items():
        if record_id and count > 1:
            errors.append(f"duplicate control id: {record_id} ({count} records)")

    for record in records:
        prefix = f"control {record.get('id', '?')}"
        missing = sorted(REQUIRED_FIELDS - record.keys())
        errors.extend(f"{prefix}: missing field {field}" for field in missing)
        if any(key in record for key in ("prepare_kwargs", "profile_kwargs")):
            errors.append(f"{prefix}: control records must not contain runtime kwargs")
        if not isinstance(record.get("input"), str):
            errors.append(f"{prefix}: input must be a string")
        if not isinstance(record.get("notes"), str):
            errors.append(f"{prefix}: notes must be a string")
        source = record.get("source")
        if not isinstance(source, dict):
            errors.append(f"{prefix}: source must be an object")
        else:
            errors.extend(
                f"{prefix}: source missing field {field}"
                for field in sorted(REQUIRED_SOURCE_FIELDS - source.keys())
            )
        expectations = record.get("expectations")
        if not isinstance(expectations, list) or not expectations:
            errors.append(f"{prefix}: expectations must be a non-empty list")
            continue
        seen_profiles: set[str] = set()
        for index, expectation in enumerate(expectations):
            eprefix = f"{prefix}: expectation[{index}]"
            if not isinstance(expectation, dict):
                errors.append(f"{eprefix} must be an object")
                continue
            errors.extend(
                f"{eprefix}: missing field {field}"
                for field in sorted(REQUIRED_EXPECTATION_FIELDS - expectation.keys())
            )
            profile_id = expectation.get("profile_id")
            if profile_id in seen_profiles:
                errors.append(f"{eprefix}: duplicate profile_id {profile_id!r}")
            if isinstance(profile_id, str):
                seen_profiles.add(profile_id)
                if profile_id not in profiles:
                    errors.append(f"{eprefix}: unknown profile_id {profile_id!r}")
            if not isinstance(expectation.get("expected_output"), str):
                errors.append(f"{eprefix}: expected_output must be a string")
            required = expectation.get("required_rules")
            forbidden = expectation.get("forbidden_rules")
            if not isinstance(required, list) or not all(
                isinstance(item, str) for item in required
            ):
                errors.append(f"{eprefix}: required_rules must be list[str]")
                required = []
            if not isinstance(forbidden, list) or not all(
                isinstance(item, str) for item in forbidden
            ):
                errors.append(f"{eprefix}: forbidden_rules must be list[str]")
                forbidden = []
            overlap = set(required) & set(forbidden)
            if overlap:
                errors.append(
                    f"{eprefix}: required/forbidden rules overlap: {sorted(overlap)}"
                )
    return errors
