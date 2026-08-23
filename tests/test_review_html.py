import copy
import tempfile
import unittest
from pathlib import Path

from spokenform_gold.io import read_records
from spokenform_gold.review import blind_review_batch
from spokenform_gold.review_html import render_review_html

ROOT = Path(__file__).resolve().parents[1]


class ReviewHtmlTests(unittest.TestCase):
    def test_report_is_deterministic_human_oriented_and_escaped(self):
        record = read_records([ROOT / "data/test/sample.jsonl"])[0]
        record = copy.deepcopy(record)
        record["input"] = '<script>alert("x")</script>'
        reviews = []
        for slot, reviewer in (("A", "review-a"), ("B", "review-b")):
            row = blind_review_batch([record], reviewer_slot=slot)[0]
            row["reviewer_id"] = reviewer
            row["annotation"] = {"status": "gold", "units": record["units"], "oracle": record["oracle"], "notes": "rationale"}
            row["review"] = {"status": f"review_{slot.lower()}_complete"}
            reviews.append(row)
        comparison = [{"sentence_oracle_id": reviews[0]["sentence_oracle_id"], "dimensions": {"semantic": True}, "disagreement": True, "state": "disagreement"}]
        decision = [{"candidate_id": record["id"], "record_id": record["id"], "decision": "needs_review", "status": "ambiguous", "blocker_code": "semantic_ambiguity_irreducible", "blocker_reason": "Context remains ambiguous.", "attempted_resolution": "Both interpretations were compared.", "adjudicator": "adj", "reviewers": ["review-a", "review-b"]}]
        with tempfile.TemporaryDirectory() as tmpdir:
            first = render_review_html(Path(tmpdir) / "one.html", candidates=[record], review_a=reviews[:1], review_b=reviews[1:], comparisons=comparison, decisions=decision, batch_id="batch-1").read_text()
            second = render_review_html(Path(tmpdir) / "two.html", candidates=[record], review_a=reviews[:1], review_b=reviews[1:], comparisons=comparison, decisions=decision, batch_id="batch-1").read_text()
        self.assertEqual(first, second)
        self.assertIn("Reviewer A", first)
        self.assertIn("semantic", first)
        self.assertIn("needs_review", first)
        self.assertIn("record-", first)
        self.assertIn("&lt;script&gt;", first)
        self.assertNotIn('<script>alert("x")</script>', first)
        self.assertNotIn('"upstream_expected"', first)


if __name__ == "__main__":
    unittest.main()
