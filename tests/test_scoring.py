import unittest
from pathlib import Path

from spokenform_gold.io import read_records
from spokenform_gold.scoring import load_predictions, score_records


ROOT = Path(__file__).resolve().parents[1]


class ScoringTests(unittest.TestCase):
    def test_score_reports_canonical_and_accepted_metrics(self):
        records = read_records([ROOT / "data/test/sample.jsonl", ROOT / "data/dev/sample.jsonl", ROOT / "data/candidates/sample_candidates.jsonl"])
        predictions = load_predictions(ROOT / "tests/fixtures/predictions/sample_predictions.jsonl")
        canonical = score_records(records, predictions, mode="canonical")
        accepted = score_records(records, predictions, mode="accepted")
        self.assertLess(canonical["sentence_canonical_accuracy"], accepted["accepted_variant_accuracy"])
        self.assertEqual(accepted["quarantine_count"], 2)
        self.assertEqual(accepted["ambiguous_count"], 1)
        self.assertEqual(accepted["no_change_accuracy"], 1.0)

    def test_no_change_mutation_counts_as_false_positive(self):
        records = read_records([ROOT / "data/test/sample.jsonl"])
        predictions = {"en-us-nochange-version-001": "Version control now changes."}
        result = score_records(records, predictions, mode="canonical")
        self.assertGreater(result["false_positive_normalization_rate"], 0.0)


if __name__ == "__main__":
    unittest.main()
