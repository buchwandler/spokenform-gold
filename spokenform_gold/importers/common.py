from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ImportResult:
    records: list[dict]
    exclusions: list[dict]
    source_rows: int
