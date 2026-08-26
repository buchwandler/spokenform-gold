import copy
import unittest
from pathlib import Path

from spokenform_gold.io import read_records
from spokenform_gold.review import blind_review_batch, compare_review_batches
from spokenform_gold.review_lineage import (
    artifact_sha256,
    backfill_legacy_evidence,
    build_review_evidence,
    sanitize_review_artifact,
    validate_review_evidence,
)

ROOT = Path(__file__).resolve().parents[1]


class ReviewLineageTests(unittest.TestCase):
    def setUp(self):
        self.record = read_records([ROOT / "data/test/sample.jsonl"])[0]

    def _reviews(self):
        rows = []
        for slot, reviewer in (("A", "review-a"), ("B", "review-b")):
            row = blind_review_batch([self.record], reviewer_slot=slot)[0]
            row["reviewer_id"] = reviewer
            row["annotation"] = {
                "status": self.record["status"],
                "expected_output": self.record["expected_output"],
                "units": copy.deepcopy(self.record["units"]),
                "negative_for": [],
                "notes": "independent fixture",
                "oracle": copy.deepcopy(self.record["oracle"]),
            }
            row["review"] = {"status": f"review_{slot.lower()}_complete"}
            rows.append(row)
        return rows[:1], rows[1:]

    def test_forbidden_fields_are_removed_and_hash_is_deterministic(self):
        value = {
            "upstream_expected": "hidden",
            "nested": {"current_output": "hidden", "ok": 1},
        }
        self.assertEqual(sanitize_review_artifact(value), {"nested": {"ok": 1}})
        self.assertEqual(artifact_sha256(value), artifact_sha256(value))

    def test_multiple_candidates_resolve_to_one_record(self):
        review_a, review_b = self._reviews()
        comparison = compare_review_batches(review_a, review_b)
        candidate = copy.deepcopy(self.record)
        candidate["id"] = "candidate-alias"
        decisions = [
            {
                "candidate_id": candidate["id"],
                "record_id": self.record["id"],
                "decision": "promote_curated",
                "adjudicator": "adj",
            }
        ]
        entries = build_review_evidence(
            [candidate],
            review_a,
            review_b,
            comparison,
            decisions,
            records=[self.record],
        )
        self.assertEqual(entries[0]["record_id"], self.record["id"])
        self.assertEqual(entries[0]["candidate_ids"], [candidate["id"]])
        self.assertEqual(validate_review_evidence(entries), [])
        self.assertNotIn("upstream_expected", repr(entries))

    def test_legacy_backfill_is_explicit(self):
        entry = backfill_legacy_evidence([self.record])[0]
        self.assertEqual(entry["review_revision"], 0)
        self.assertTrue(entry["legacy"])
        self.assertEqual(entry["evidence_status"], "legacy_review_metadata_only")
        self.assertEqual(validate_review_evidence([entry]), [])


if __name__ == "__main__":
    unittest.main()
