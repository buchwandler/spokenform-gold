import copy
import json
import tempfile
import unittest
from pathlib import Path

from spokenform_gold.io import read_records
from spokenform_gold.oracle import oracle_hash
from spokenform_gold.review import (
    apply_reviewed_oracles,
    blind_review_batch,
    compare_review_batches,
    write_review_application,
)
from spokenform_gold.validation import validate_records

ROOT = Path(__file__).resolve().parents[1]


class ReviewEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.record = read_records([ROOT / "data/test/sample.jsonl"])[0]
        self.review_a = self._completed("reviewer-a", "A")
        self.review_b = self._completed("reviewer-b", "B")

    def _completed(self, reviewer_id, slot):
        row = blind_review_batch([self.record], reviewer_slot=slot)[0]
        row["reviewer_id"] = reviewer_id
        row["annotation"] = {
            "status": self.record["status"],
            "expected_output": self.record["expected_output"],
            "units": copy.deepcopy(self.record["units"]),
            "negative_for": copy.deepcopy(self.record["negative_for"]),
            "notes": "Independent review fixture.",
            "oracle": copy.deepcopy(self.record["oracle"]),
        }
        row["review"] = {
            "status": "review_a_complete" if slot == "A" else "review_b_complete",
            "protocol_version": "1.0.0",
        }
        return row

    def _decision(self):
        return {
            "sentence_oracle_id": self.review_a["sentence_oracle_id"],
            "record_id": self.record["id"],
            "family_id": self.record["family_id"],
            "reviewers": ["reviewer-a", "reviewer-b"],
            "adjudicator": "maintainer-1",
            "decision": "adjudicated",
            "status": self.record["status"],
            "input": self.record["input"],
            "language": self.record["language"],
            "locale": self.record["locale"],
            "expected_output": self.record["expected_output"],
            "units": copy.deepcopy(self.record["units"]),
            "negative_for": copy.deepcopy(self.record["negative_for"]),
            "notes": "Adjudicated review fixture.",
            "oracle": copy.deepcopy(self.record["oracle"]),
            "disagreement": {"semantic": False},
            "source_error_codes": [],
        }

    def test_compare_requires_distinct_completed_reviewers(self):
        result = compare_review_batches([self.review_a], [self.review_b])
        self.assertEqual(result[0]["state"], "agreement")
        self.assertEqual(result[0]["reviewer_a"], "reviewer-a")
        self.assertEqual(result[0]["reviewer_b"], "reviewer-b")

        same = copy.deepcopy(self.review_b)
        same["reviewer_id"] = "reviewer-a"
        with self.assertRaisesRegex(ValueError, "distinct"):
            compare_review_batches([self.review_a], [same])

    def test_compare_rejects_context_mismatch(self):
        other = copy.deepcopy(self.review_b)
        other["locale"] = "de-DE"
        with self.assertRaisesRegex(ValueError, "locale"):
            compare_review_batches([self.review_a], [other])

    def test_apply_preserves_identity_and_recomputes_oracle_hash(self):
        updated, comparisons, report = apply_reviewed_oracles(
            [self.record], [self.review_a], [self.review_b], [self._decision()]
        )
        result = updated[0]
        self.assertEqual(result["id"], self.record["id"])
        self.assertEqual(result["family_id"], self.record["family_id"])
        self.assertEqual(result["source"], self.record["source"])
        self.assertEqual(result["review"]["status"], "adjudicated")
        self.assertEqual(result["review"]["reviewers"], ["reviewer-a", "reviewer-b"])
        self.assertEqual(result["oracle_hash"], oracle_hash(result))
        self.assertEqual(validate_records(updated), [])
        self.assertEqual(report["agreement"], 1)
        self.assertEqual(len(comparisons), 1)

    def test_apply_requires_all_decisions_and_rejects_family_migration(self):
        with self.assertRaisesRegex(ValueError, "missing adjudication"):
            apply_reviewed_oracles([self.record], [self.review_a], [self.review_b], [])
        decision = self._decision()
        decision["family_id"] = "new-family"
        with self.assertRaisesRegex(ValueError, "family_id"):
            apply_reviewed_oracles(
                [self.record], [self.review_a], [self.review_b], [decision]
            )

    def test_output_tree_is_new_and_contains_reported_artifacts(self):
        updated, comparisons, report = apply_reviewed_oracles(
            [self.record], [self.review_a], [self.review_b], [self._decision()]
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "reviewed"
            write_review_application(
                output, updated, comparisons, report, input_paths=[ROOT / "data/test/sample.jsonl"]
            )
            self.assertEqual(read_records([output / "records.jsonl"])[0]["id"], self.record["id"])
            self.assertEqual(json.loads((output / "report.json").read_text())["records"], 1)

    def test_output_under_canonical_input_is_rejected(self):
        updated, comparisons, report = apply_reviewed_oracles(
            [self.record], [self.review_a], [self.review_b], [self._decision()]
        )
        with self.assertRaisesRegex(ValueError, "overlaps"):
            write_review_application(
                ROOT / "data/test/reviewed-output",
                updated,
                comparisons,
                report,
                input_paths=[ROOT / "data/test/sample.jsonl"],
            )


if __name__ == "__main__":
    unittest.main()
