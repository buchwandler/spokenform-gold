from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy

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


def hydrate_external_overlay(overlay: dict, *, input_text: str) -> dict:
    if overlay.get("materialization") != "external_ref":
        return deepcopy(overlay)
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
    return hydrate_external_overlay(record, input_text=input_text)
