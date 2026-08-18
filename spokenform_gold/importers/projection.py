from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..io import sha256_text


@dataclass(frozen=True)
class ProjectionUnit:
    surface: str
    start: int
    end: int
    category: str
    source_category: str
    mapping_status: str
    surface_pattern: str = "imported"
    span_origin: str = "explicit"
    features: dict[str, Any] = field(default_factory=dict)

    def to_candidate(self, *, import_format: str) -> dict[str, Any]:
        merged_features = {
            "surface_pattern": self.surface_pattern,
            "span_origin": self.span_origin,
            "import_format": import_format,
        }
        merged_features.update(self.features)
        return {
            "surface": self.surface,
            "start": self.start,
            "end": self.end,
            "category": self.category,
            "source_category": self.source_category,
            "mapping_status": self.mapping_status,
            "semantic": {},
            "policy": "unadjudicated-upstream",
            "canonical": None,
            "accepted": [],
            "rejected": [],
            "features": merged_features,
        }


@dataclass(frozen=True)
class ProjectionRecord:
    benchmark: str
    source_id: str
    source_version: str
    source_url: str
    license: str
    language: str
    locale: str
    input_text: str
    source_file: str
    import_format: str
    units: tuple[ProjectionUnit, ...] = ()
    family_id: str | None = None
    upstream_expected: str | None = None
    source_category: str | None = None
    source_split: str | None = None
    projection_notes: str = ""
    notes: str = ""
    status: str = "quarantine"
    split: str = "candidate"
    negative_for: tuple[str, ...] = ()
    extra_source: dict[str, Any] = field(default_factory=dict)
    extra_record: dict[str, Any] = field(default_factory=dict)

    def _source_hash(self) -> str:
        parts = [
            self.source_id,
            self.input_text,
            self.upstream_expected or "",
            self.source_category or "",
            self.import_format,
        ]
        return "sha256:" + sha256_text("\n".join(parts))

    def to_candidate(self) -> dict[str, Any]:
        record = {
            "id": f"{self.benchmark.replace('_', '-')}-{self.source_id.replace(':', '-')}",
            "schema_version": "1.0.0",
            "taxonomy_version": "1.0.0",
            "policy_version": "1.0.0",
            "language": self.language,
            "locale": self.locale,
            "split": self.split,
            "family_id": self.family_id
            or f"{self.benchmark.replace('_', '-')}-{self.source_id.replace(':', '-')}",
            "status": self.status,
            "input": self.input_text,
            "expected_output": None,
            "source": {
                "benchmark": self.benchmark,
                "source_id": self.source_id,
                "source_version": self.source_version,
                "source_url": self.source_url,
                "license": self.license,
                "source_hash": self._source_hash(),
                "source_file": self.source_file,
                "source_split": self.source_split,
                "upstream_expected": self.upstream_expected,
                "projection_notes": self.projection_notes,
                "import_format": self.import_format,
                "importer_version": "1.0.0",
            },
            "units": [unit.to_candidate(import_format=self.import_format) for unit in self.units],
            "negative_for": list(self.negative_for),
            "notes": self.notes or f"Imported from {self.benchmark}; adjudicate before promotion.",
        }
        record["source"].update(self.extra_source)
        record.update(self.extra_record)
        return record
