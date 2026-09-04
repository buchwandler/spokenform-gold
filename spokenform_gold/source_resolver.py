from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy

from .corpus import exact_surface_hash
from .validation import validate_records

SourceTextLoader = Callable[[dict], str]


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
    overlay["source"] = dict(overlay.get("source", {}))
    overlay["source"]["source_artifact"] = source_artifact
    return overlay


def build_v2_external_overlay(
    record: dict, *, source: dict, source_artifact: str | None = None
) -> dict:
    """Create a v2 release overlay without changing the canonical record."""
    if not isinstance(record.get("input"), str) or not record["input"]:
        raise ValueError("v2 external overlay requires canonical input")
    overlay = deepcopy(record)
    overlay["materialization"] = "external_ref"
    overlay["input"] = None
    overlay["source_observations"] = [deepcopy(source)]
    public_source = deepcopy(source)
    artifact = (
        source_artifact
        or public_source.get("source_artifact")
        or (
            "source://"
            + str(public_source.get("benchmark", "unknown"))
            + "/"
            + str(public_source.get("source_id", ""))
        )
    )
    public_source["source_artifact"] = artifact
    overlay["source"] = public_source
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
    if not isinstance(input_text, str) or not input_text:
        raise ValueError("source_loader must return non-empty source text")
    hydrated = hydrate_external_overlay(record, input_text=input_text)
    validation_record = deepcopy(hydrated)
    validation_record["materialization"] = "embedded"
    errors = validate_records([validation_record])
    if errors:
        raise ValueError(
            "hydrated external_ref record is invalid: " + "; ".join(errors)
        )
    return hydrated
