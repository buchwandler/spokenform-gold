import copy
import unittest
from pathlib import Path

from spokenform_gold.adjudication_quality import validate_adjudication_batch
from spokenform_gold.io import read_records
from spokenform_gold.review import blind_review_batch

ROOT = Path(__file__).resolve().parents[1]


class AdjudicationQualityTests(unittest.TestCase):
    def setUp(self):
        self.record = read_records([ROOT / "data/test/sample.jsonl"])[0]
        self.candidate = copy.deepcopy(self.record)
        self.candidate["id"] = "candidate-1"
        self.a = blind_review_batch([self.candidate], reviewer_slot="A")[0]
        self.b = blind_review_batch([self.candidate], reviewer_slot="B")[0]
        for row, reviewer, slot in ((self.a, "review-a", "a"), (self.b, "review-b", "b")):
            row["reviewer_id"] = reviewer
            row["annotation"] = {"status": self.record["status"], "expected_output": self.record["expected_output"], "units": copy.deepcopy(self.record["units"]), "negative_for": [], "notes": "independent", "oracle": copy.deepcopy(self.record["oracle"])}
            row["review"] = {"status": f"review_{slot}_complete"}
        self.comparison = [{"sentence_oracle_id": self.a["sentence_oracle_id"], "dimensions": {"semantic": True}, "disagreement": True}]

    def decision(self, **extra):
        result = {"candidate_id": "candidate-1", "record_id": self.record["id"], "decision": "needs_review", "reviewers": ["review-a", "review-b"], "adjudicator": "adj", "blocker_code": "semantic_ambiguity_irreducible", "blocker_reason": "The sentence is ambiguous without context.", "attempted_resolution": "Both interpretations were evaluated."}
        result.update(extra)
        return result

    def test_disagreement_alone_is_not_a_blocker(self):
        report = validate_adjudication_batch([self.candidate], [self.a], [self.b], self.comparison, [self.decision(blocker_reason="A/B disagreement")])
        self.assertFalse(report["ready"])
        self.assertIn("generic_disagreement_blocker", {issue["code"] for issue in report["issues"]})

    def test_mass_deferral_is_reported(self):
        report = validate_adjudication_batch([self.candidate], [self.a], [self.b], self.comparison, [self.decision()], max_unresolved_percent=25)
        self.assertFalse(report["ready"])
        self.assertEqual(report["unresolved"], 1)
        self.assertIn("mass_deferral", {issue["code"] for issue in report["issues"]})

    def test_hard_blocker_can_be_ready_without_threshold(self):
        report = validate_adjudication_batch([self.candidate], [self.a], [self.b], self.comparison, [self.decision()])
        self.assertTrue(report["ready"], report["issues"])


if __name__ == "__main__":
    unittest.main()
