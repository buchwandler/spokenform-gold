import unittest

from spokenform_gold.adjudication import build_adjudication_queue
from spokenform_gold.io import read_records
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class AdjudicationTests(unittest.TestCase):
    def test_queue_prioritizes_conflict_and_coverage_gap(self):
        records = read_records(
            [ROOT / "tests/fixtures/candidates/sample_candidates.jsonl"]
        )
        conflicts = [{"key": ["en-US", "currency", "$5"]}]
        coverage = {"gaps": [{"category": "currency", "kind": "low_volume"}]}
        queue = build_adjudication_queue(
            records, conflicts=conflicts, coverage=coverage
        )
        self.assertEqual(queue[0]["id"], "async-tn-en-1001")
        self.assertIn("source_disagreement", queue[0]["reasons"])


if __name__ == "__main__":
    unittest.main()
