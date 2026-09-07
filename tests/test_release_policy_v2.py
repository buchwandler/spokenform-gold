import json
import tempfile
import unittest
from pathlib import Path

from spokenform_gold.release import (
    _build_review_evidence_summary,
    plan_publication_records,
)
from spokenform_gold.source_resolver import build_v2_external_overlay


class ReleasePolicyV2Tests(unittest.TestCase):
    def test_excluded_records_do_not_block_and_multi_source_basis_wins(self):
        manifest = {
            "sources": [
                {
                    "name": "embedded",
                    "revision": "a",
                    "release_ready": True,
                    "materialization_policy": "embedded_public",
                },
                {
                    "name": "excluded",
                    "revision": "b",
                    "release_ready": True,
                    "materialization_policy": "review_required",
                },
            ]
        }
        records = [
            {
                "id": "excluded-record",
                "source_observations": [
                    {"benchmark": "excluded", "materialization": "embedded"}
                ],
            },
            {
                "id": "multi-record",
                "source_observations": [
                    {"benchmark": "embedded", "materialization": "embedded"},
                    {"benchmark": "excluded", "materialization": "embedded"},
                ],
            },
        ]
        decisions = [
            {"source": "embedded", "decision": "embedded_public"},
            {"source": "excluded", "decision": "exclude_public"},
        ]
        plan = plan_publication_records(records, manifest, decisions=decisions)
        rows = {row["record_id"]: row for row in plan["records_plan"]}
        self.assertEqual(rows["excluded-record"]["mode"], "excluded")
        self.assertEqual(rows["multi-record"]["mode"], "embedded")
        self.assertEqual(rows["multi-record"]["publication_basis"], ["embedded"])
        self.assertEqual(plan["excluded"], 1)
        self.assertEqual(plan["blocked"], 0)

    def test_external_overlay_uses_public_source_whitelist(self):
        record = {
            "id": "record-1",
            "input": "Value 42",
            "oracle": {
                "canonical_output": "Value forty-two",
                "accepted_outputs": ["Value forty-two"],
                "rejected_outputs": [],
            },
            "units": [],
            "negative_for": [],
            "source_observations": [],
        }
        source = {
            "benchmark": "polynorm",
            "source_id": "en-US:1",
            "source_version": "rev-1",
            "source_url": "https://example.test/source",
            "license": "CC BY-NC-ND 4.0",
            "source_hash": "sha256:abc",
            "source_category": "Version Numbers",
            "upstream_expected": "restricted text",
            "projection_notes": "restricted notes",
            "original_text": "restricted input",
        }
        overlay = build_v2_external_overlay(record, source=source)
        serialized = str(overlay)
        for forbidden in ("upstream_expected", "projection_notes", "original_text"):
            self.assertNotIn(forbidden, serialized)
        self.assertIsNone(overlay["input"])
        self.assertEqual(overlay["external_ref"]["source_id"], "en-US:1")
        self.assertEqual(overlay["source"]["source_category"], "Version Numbers")

    def test_review_evidence_summary_distinguishes_review_lineage(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            lineage = root / "data" / "lineage"
            lineage.mkdir(parents=True)
            rows = [
                {
                    "record_id": "modern",
                    "review_a": {"status": "complete"},
                    "review_b": {"status": "complete"},
                },
                {"record_id": "legacy", "review_status": "complete"},
            ]
            (lineage / "review-evidence.jsonl").write_text(
                "".join(json.dumps(row) + "\n" for row in rows),
                encoding="utf-8",
            )
            summary = _build_review_evidence_summary(
                [{"id": "modern"}, {"id": "legacy"}, {"id": "missing"}],
                root,
            )
        self.assertEqual(summary["records_checked"], 3)
        self.assertEqual(summary["modern_ab"], 1)
        self.assertEqual(summary["legacy_metadata"], 1)
        self.assertEqual(summary["missing_lineage"], 1)


if __name__ == "__main__":
    unittest.main()
