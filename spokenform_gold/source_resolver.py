from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy

from .corpus import exact_surface_hash
from .validation import validate_records

SourceTextLoader = Callable[[dict], str]


PUBLIC_SOURCE_FIELDS = frozenset(
    {
        "benchmark",
        "source_id",
        "source_version",
        "source_url",
        "license",
        "license_id",
        "source_hash",
        "source_file",
        "source_split",
        "source_category",
        "materialization",
        "source_artifact",
    }
)


def public_source_reference(
    source: dict, *, source_artifact: str | None = None
) -> dict:
    """Build the restricted-field-free source reference used in public releases."""
    reference = {key: source[key] for key in PUBLIC_SOURCE_FIELDS if key in source}
    artifact = source_artifact or source.get("source_artifact")
    if artifact is not None:
        reference["source_artifact"] = artifact
    return reference


def build_external_overlay(record: dict, *, source_artifact: str) -> dict:
    overlay = deepcopy(record)
    annotation = {
        "expected_output": overlay.pop("expected_output", None),
        "units": overlay.pop("units", []),
        "negative_for": overlay.pop("negative_for", []),
        "notes": overlay.pop("notes", ""),
    }
    overlay["materialization"] = "external_ref"
    overlay["annotation"] = annotation
    overlay["input"] = None
    source = public_source_reference(
        overlay.get("source", {}), source_artifact=source_artifact
    )
    overlay["source"] = source
    if "source_observations" in overlay:
        overlay["source_observations"] = [source]
    return overlay


def build_v2_external_overlay(
    record: dict, *, source: dict, source_artifact: str | None = None
) -> dict:
    """Create a v2 release overlay without changing the canonical record."""
    if not isinstance(record.get("input"), str):
        raise TypeError("v2 external overlay requires canonical input")
    overlay = deepcopy(record)
    overlay["materialization"] = "external_ref"
    overlay["input"] = None
    artifact = (
        source_artifact
        or source.get("source_artifact")
        or (
            "source://"
            + str(source.get("benchmark", "unknown"))
            + "/"
            + str(source.get("source_id", ""))
        )
    )
    public_source = public_source_reference(source, source_artifact=artifact)
    overlay["source_observations"] = [public_source]
    overlay["source"] = public_source
    public_source["materialization"] = "external_ref"
    overlay["external_ref"] = {
        "source": public_source.get("benchmark"),
        "source_revision": public_source.get("source_version"),
        "source_id": public_source.get("source_id"),
        "source_artifact": artifact,
        "source_input_hash": exact_surface_hash(record["input"]),
        "hydration": {
            "kind": "source_record",
            "source_id": public_source.get("source_id"),
        },
    }
    overlay["annotation"] = {
        "oracle": deepcopy(record.get("oracle")),
        "units": deepcopy(record.get("units", [])),
        "negative_for": deepcopy(record.get("negative_for", [])),
        "notes": record.get("notes", ""),
    }
    return overlay


def hydrate_external_overlay(overlay: dict, *, input_text: str) -> dict:
    if overlay.get("materialization") != "external_ref":
        return deepcopy(overlay)
    expected_hash = (overlay.get("external_ref") or {}).get("source_input_hash")
    if expected_hash and exact_surface_hash(input_text) != expected_hash:
        raise ValueError("hydrated external_ref source hash mismatch")
    annotation = overlay.get("annotation")
    if not isinstance(annotation, dict):
        raise TypeError("external_ref record is missing annotation payload")
    hydrated = deepcopy(overlay)
    hydrated["input"] = input_text
    hydrated["expected_output"] = annotation.get("expected_output")
    hydrated["units"] = annotation.get("units", [])
    hydrated["negative_for"] = annotation.get("negative_for", [])
    hydrated["notes"] = annotation.get("notes", "")
    return hydrated


def resolve_release_record(
    record: dict, *, source_loader: SourceTextLoader | None
) -> dict:
    if record.get("materialization") != "external_ref":
        return deepcopy(record)
    if source_loader is None:
        raise ValueError("external_ref record requires a source_loader")
    input_text = source_loader(record)
    if not isinstance(input_text, str):
        raise TypeError("source_loader must return source text")
    hydrated = hydrate_external_overlay(record, input_text=input_text)
    validation_record = deepcopy(hydrated)
    validation_record["materialization"] = "embedded"
    errors = validate_records([validation_record])
    if errors:
        raise ValueError(
            "hydrated external_ref record is invalid: " + "; ".join(errors)
        )
    return hydrated
