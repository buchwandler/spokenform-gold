import unittest
from pathlib import Path
from spokenform_gold.io import read_jsonl
from spokenform_gold.coverage import build_coverage, load_targets

ROOT = Path(__file__).resolve().parents[1]

class CoverageTests(unittest.TestCase):
    def test_gaps_are_detected(self):
        records = read_jsonl(ROOT / "data/dev/sample.jsonl")
        result = build_coverage(records, load_targets(ROOT / "taxonomy/coverage_targets.json"))
        self.assertGreater(len(result["gaps"]), 0)
        self.assertTrue(any(g["kind"] == "low_volume" for g in result["gaps"]))

if __name__ == "__main__":
    unittest.main()
