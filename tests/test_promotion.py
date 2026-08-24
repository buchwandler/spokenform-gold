import copy
import json
import tempfile
import unittest
from pathlib import Path

from spokenform_gold.io import read_records, write_jsonl
from spokenform_gold.promotion import build_promoted_records

ROOT = Path(__file__).resolve().parents[1]


class PromotionTests(unittest.TestCase):
    def setUp(self):
        self.candidate = next(
            record
            for record in read_records([ROOT / "data/test/sample.jsonl"])
            if record["locale"] == "en-US" and record["units"]
        )
        self.existing = read_records([ROOT / "data/dev/sample.jsonl"])[0]

    def decision(self, **overrides):
        decision = {
            "candidate_id": self.candidate["id"],
            "record_id": "curated-promotion-001",
            "decision": "promote_curated",
            "reviewers": ["review-a", "review-b"],
            "adjudicator": "review-c",
            "family_id": "curated-promotion-family",
            "status": "gold",
            "input": self.candidate["input"],
            "expected_output": self.candidate["expected_output"],
            "units": copy.deepcopy(self.candidate["units"]),
            "negative_for": [],
            "notes": "Independently reviewed test record.",
            "oracle": copy.deepcopy(self.candidate["oracle"]),
            "license_disposition": "spokenform_original",
            "upstream_refs": [{"benchmark": "async_tn", "source_id": "1001"}],
        }
        decision.update(overrides)
        return decision

    def test_promotes_curated_record_with_lineage(self):
        promoted, report = build_promoted_records(
            [self.candidate], [self.decision()], [self.existing]
        )
        self.assertEqual(
            [record["id"] for record in promoted], ["curated-promotion-001"]
        )
        self.assertEqual(promoted[0]["source"]["benchmark"], "spokenform_curated")
        self.assertEqual(promoted[0]["source"]["informed_by"][0]["source_id"], "1001")
        self.assertEqual(report["new_families"], ["curated-promotion-family"])

    def test_output_and_report_are_deterministic(self):
        first = build_promoted_records([self.candidate], [self.decision()], [])[0:2]
        second = build_promoted_records([self.candidate], [self.decision()], [])[0:2]
        self.assertEqual(first, second)
        self.assertEqual(first[1]["record_ids"], ["curated-promotion-001"])

    def test_missing_decision_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "missing decisions"):
            build_promoted_records([self.candidate], [], [])

    def test_duplicate_decision_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate decision"):
            build_promoted_records(
                [self.candidate], [self.decision(), self.decision()], []
            )

    def test_invalid_reviewed_status_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "invalid promoted status"):
            build_promoted_records(
                [self.candidate], [self.decision(status="quarantine")], []
            )

    def test_semantic_validation_failure_is_rejected(self):
        broken_units = copy.deepcopy(self.candidate["units"])
        broken_units[0]["semantic"] = {"hour": 28, "minute": 0}
        with self.assertRaisesRegex(ValueError, "promoted records are invalid"):
            build_promoted_records(
                [self.candidate], [self.decision(units=broken_units)], []
            )

    def test_no_change_invariant_failure_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "promoted records are invalid"):
            build_promoted_records(
                [self.candidate],
                [
                    self.decision(
                        status="no_change",
                        expected_output="not the input",
                        units=[],
                        negative_for=["time"],
                    )
                ],
                [],
            )

    def test_restricted_upstream_promotion_is_rejected(self):
        upstream = copy.deepcopy(self.candidate)
        upstream["source"] = copy.deepcopy(
            read_records([ROOT / "data/candidates/async_tn.jsonl"])[0]["source"]
        )
        decision = self.decision(decision="promote_upstream")
        with self.assertRaisesRegex(ValueError, "not permitted for embedded upstream"):
            build_promoted_records([upstream], [decision], [])

    def test_existing_record_id_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "already exists"):
            build_promoted_records(
                [self.candidate],
                [self.decision(record_id=self.existing["id"])],
                [self.existing],
            )

    def test_family_language_conflict_is_rejected(self):
        existing = copy.deepcopy(self.existing)
        existing["family_id"] = "curated-promotion-family"
        existing["language"] = "de"
        existing["locale"] = "de-DE"
        with self.assertRaisesRegex(ValueError, "family conflict"):
            build_promoted_records([self.candidate], [self.decision()], [existing])

    def test_cli_shape_can_be_written_as_jsonl_staging(self):
        promoted, report = build_promoted_records(
            [self.candidate], [self.decision()], []
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "reviewed.jsonl"
            write_jsonl(output, promoted)
            self.assertEqual(len(read_records([output])), 1)
            self.assertEqual(json.loads(json.dumps(report))["promoted"], 1)


if __name__ == "__main__":
    unittest.main()
