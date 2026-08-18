import unittest
from pathlib import Path

from spokenform_gold.io import read_records
from spokenform_gold.judge_calibration import (
    build_judge_calibration,
    load_judge_predictions,
)

ROOT = Path(__file__).resolve().parents[1]


class JudgeCalibrationTests(unittest.TestCase):
    def test_calibration_reports_requested_metrics(self):
        records = read_records([ROOT / "data/judge_gold/sample.jsonl"])
        predictions = load_judge_predictions(
            ROOT / "tests/fixtures/predictions/judge_predictions.jsonl"
        )
        result = build_judge_calibration(records, predictions)
        self.assertEqual(result["records"], len(records))
        self.assertIn("precision", result)
        self.assertIn("recall", result)
        self.assertIn("false_acceptance_rate", result)
        self.assertIn("false_rejection_rate", result)
        self.assertIn("date", result["per_category_accuracy"])
        self.assertIn("en", result["per_language_accuracy"])
        self.assertIn("mdy-vs-dmy", result["per_ambiguity_family_accuracy"])

    def test_missing_prediction_is_rejected(self):
        records = read_records([ROOT / "data/judge_gold/sample.jsonl"])
        with self.assertRaises(ValueError):
            build_judge_calibration(records, {})


if __name__ == "__main__":
    unittest.main()
