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


if __name__ == "__main__":
    unittest.main()
