import unittest
from pathlib import Path

from spokenform_gold.coverage import build_coverage, load_targets
from spokenform_gold.io import read_records

ROOT = Path(__file__).resolve().parents[1]


class CoverageTests(unittest.TestCase):
    def test_gaps_are_detected(self):
        records = read_records([ROOT / "data/dev", ROOT / "data/test"])
        result = build_coverage(
            records, load_targets(ROOT / "taxonomy/coverage_targets.json")
        )
        self.assertGreater(len(result["gaps"]), 0)
        self.assertTrue(any(gap["kind"] == "low_volume" for gap in result["gaps"]))
        self.assertTrue(any(row["category"] == "decimal" for row in result["coverage"]))

    def test_language_profiles_and_translation_provenance_are_reported(self):
        targets_path = ROOT / "taxonomy/coverage_targets.json"
        cjk_targets = load_targets(targets_path, profile="cjk-experimental")
        self.assertEqual(cjk_targets["languages"], ["ja", "ko", "zh"])
        records = [
            {
                "language": "ja",
                "locale": "ja-JP",
                "status": "no_change",
                "negative_for": ["date"],
                "units": [],
                "source": {
                    "benchmark": "spokenform_translation",
                    "translation_parent_record_id": "parent-1",
                    "translation_relation": "adapted",
                },
            }
        ]
        result = build_coverage(records, cjk_targets)
        self.assertEqual(result["translation_derived_records"], 1)
        self.assertEqual(result["translation_derived_fraction"], 1.0)
        self.assertEqual(result["language_profile"], "cjk-experimental")


if __name__ == "__main__":
    unittest.main()
