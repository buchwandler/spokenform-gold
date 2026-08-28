"""Canonical paths for workflow-owned Spokenform Gold artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WorkLayout:
    root: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "root", Path(self.root).expanduser().resolve())

    @property
    def batches_root(self) -> Path:
        return self.root / "batches"

    @property
    def corrections_root(self) -> Path:
        return self.root / "corrections"

    @property
    def archive_root(self) -> Path:
        return self.root / "archive"

    @property
    def state_root(self) -> Path:
        return self.root / "state"

    def batch(self, batch_id: str) -> BatchLayout:
        return BatchLayout(self.batches_root / batch_id)

    def correction(
        self, record_id: str, revision: int | None = None
    ) -> CorrectionLayout:
        root = self.corrections_root / record_id
        if revision is not None:
            root /= f"rev-{revision:04d}"
        return CorrectionLayout(root)


@dataclass(frozen=True)
class BatchLayout:
    root: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "root", Path(self.root).expanduser().resolve())

    @property
    def metadata(self) -> Path:
        return self.root / "batch.json"

    @property
    def source_dir(self) -> Path:
        return self.root / "source"

    @property
    def cases_dir(self) -> Path:
        return self.root / "cases"

    @property
    def cases(self) -> Path:
        return self.cases_dir / "cases.jsonl"

    @property
    def context(self) -> Path:
        return self.cases_dir / "context.jsonl"

    def review_dir(self, slot: str) -> Path:
        return self.root / "reviews" / slot.lower()

    def review_blind(self, slot: str) -> Path:
        return self.review_dir(slot) / "blind.jsonl"

    def review_complete(self, slot: str) -> Path:
        return self.review_dir(slot) / "complete.jsonl"

    def review_validation(self, slot: str) -> Path:
        return self.review_dir(slot) / "validation.json"

    def review_packet_dir(self, slot: str) -> Path:
        return self.review_dir(slot) / "packets"

    def review_packet(
        self, slot: str, packet_number: int, result: bool = False
    ) -> Path:
        suffix = "result" if result else "input"
        return self.review_packet_dir(slot) / f"{packet_number:04d}.{suffix}.jsonl"

    @property
    def review_check(self) -> Path:
        return self.root / "reviews" / "check.json"

    @property
    def adjudication_dir(self) -> Path:
        return self.root / "adjudication"

    @property
    def adjudication_decisions(self) -> Path:
        return self.adjudication_dir / "decisions.jsonl"

    @property
    def adjudication_partial(self) -> Path:
        return self.adjudication_dir / "decisions.partial.jsonl"

    def adjudication_packet(self, packet_number: int, result: bool = False) -> Path:
        suffix = "result" if result else "input"
        return self.adjudication_dir / "packets" / f"{packet_number:04d}.{suffix}.jsonl"

    @property
    def integration_dir(self) -> Path:
        return self.root / "integration"

    @property
    def integration_summary(self) -> Path:
        return self.integration_dir / "summary.json"

    @property
    def reports_dir(self) -> Path:
        return self.root / "reports"

    @property
    def handoff(self) -> Path:
        return self.root / "handoff.md"

    def legacy(self, name: str) -> Path:
        """Return a legacy root-level artifact path for compatibility reads."""
        return self.root / name


@dataclass(frozen=True)
class CorrectionLayout:
    root: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "root", Path(self.root).expanduser().resolve())

    @property
    def context(self) -> Path:
        return self.root / "context.json"

    @property
    def decision(self) -> Path:
        return self.root / "decision.json"

    @property
    def result(self) -> Path:
        return self.root / "result.json"

    @property
    def receipt(self) -> Path:
        return self.root / "receipt.json"

    @property
    def evidence(self) -> Path:
        return self.root / "review-evidence.jsonl"

    @property
    def report(self) -> Path:
        return self.root / "report.html"


__all__ = ["BatchLayout", "CorrectionLayout", "WorkLayout"]
