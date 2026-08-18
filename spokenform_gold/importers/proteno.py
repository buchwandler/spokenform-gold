from __future__ import annotations

import io
import pickle
from pathlib import Path

from ..io import read_json
from ..taxonomy import load_mapping, source_manifest_map


class RestrictedUnpickler(pickle.Unpickler):
    SAFE_BUILTINS = {
        "builtins": {
            "dict",
            "list",
            "tuple",
            "set",
            "str",
            "int",
            "float",
            "bool",
            "NoneType",
        }
    }

    def find_class(self, module, name):
        if module in self.SAFE_BUILTINS and name in self.SAFE_BUILTINS[module]:
            return getattr(__import__(module), name)
        raise pickle.UnpicklingError(f"unsafe pickle global: {module}.{name}")


def _load_payload(path: str | Path):
    target = Path(path)
    if target.suffix == ".json":
        return read_json(target)
    if target.suffix == ".pkl":
        return RestrictedUnpickler(io.BytesIO(target.read_bytes())).load()
    raise ValueError("proteno source must be .json or .pkl")


def import_proteno(path: str | Path) -> list[dict]:
    payload = _load_payload(path)
    if not isinstance(payload, dict) or not isinstance(payload.get("cases"), list):
        raise ValueError("proteno payload must be an object with a cases list")

    manifest = source_manifest_map()["proteno"]
    mapping = load_mapping("proteno").get("mappings", {})
    records: list[dict] = []
    for index, case in enumerate(payload["cases"], 1):
        if not isinstance(case, dict):
            raise ValueError(f"proteno case {index} must be an object")
        category = case.get("category")
        rule = mapping.get(category)
        if rule is None:
            raise ValueError(f"proteno case {index}: unsupported category {category!r}")
        source_id = str(case.get("case_id", index))
        records.append(
            {
                "id": f"proteno-{source_id}",
                "schema_version": "1.0.0",
                "taxonomy_version": "1.0.0",
                "policy_version": "1.0.0",
                "language": case.get("language", "en"),
                "locale": case.get("locale", "en-US"),
                "split": "candidate",
                "family_id": f"proteno-{source_id}",
                "status": "quarantine",
                "input": case["input"],
                "expected_output": None,
                "source": {
                    "benchmark": "proteno",
                    "source_id": source_id,
                    "source_version": manifest["revision"],
                    "source_url": manifest["source_url"],
                    "license": manifest["license"],
                    "source_split": case.get("source_split", "unknown"),
                    "upstream_expected": case.get("expected"),
                    "projection_notes": case.get("projection_notes", ""),
                    "importer_version": "1.0.0",
                },
                "units": [
                    {
                        "surface": case["surface"],
                        "start": case["start"],
                        "end": case["end"],
                        "category": rule["category"],
                        "source_category": category,
                        "mapping_status": rule["status"],
                        "semantic": {},
                        "policy": "unadjudicated-upstream",
                        "canonical": None,
                        "accepted": [],
                        "rejected": [],
                        "features": {
                            "surface_pattern": rule.get("surface_pattern", "imported"),
                            "identity_example": bool(
                                case.get("identity_example", False)
                            ),
                        },
                    }
                ],
                "negative_for": [],
                "notes": case.get("projection_notes", ""),
            }
        )
    return records
