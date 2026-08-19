import unittest
from pathlib import Path

from spokenform_gold.control_validation import validate_control_records
from spokenform_gold.coverage import build_control_coverage, load_targets
from spokenform_gold.io import read_records

ROOT = Path(__file__).resolve().parents[1]


class ControlCoverageTests(unittest.TestCase):
    def test_control_coverage_reports_suites_languages_and_gaps(self):
        records = read_records([ROOT / "data" / "controls"])
        self.assertEqual(validate_control_records(records), [])
        report = build_control_coverage(
            records, load_targets(ROOT / "taxonomy" / "coverage_targets.json")
        )
        self.assertEqual(report["controls_observed"], 5)
        self.assertEqual(report["gaps"], [])
        fallback = next(
            item
            for item in report["coverage"]
            if item["control"] == "sequence_fallback_mode"
        )
        self.assertEqual(
            fallback["languages"], ["cs", "de", "en", "es", "fr", "it", "pt"]
        )

    def test_czech_is_an_active_canonical_target(self):
        targets = load_targets(ROOT / "taxonomy" / "coverage_targets.json")
        self.assertIn("cs", targets["languages"])


if __name__ == "__main__":
    unittest.main()
