import unittest
from pathlib import Path

from spokenform_gold.control_validation import validate_control_records
from spokenform_gold.io import read_records

ROOT = Path(__file__).resolve().parents[1]


class ControlDataTests(unittest.TestCase):
    def test_checked_in_control_suites_validate_and_cover_languages(self):
        paths = sorted((ROOT / "data" / "controls").glob("*.jsonl"))
        self.assertEqual(
            {path.stem for path in paths},
            {
                "domain_policy",
                "interpretation_mode",
                "literal_promotion",
                "sequence_fallback",
            },
        )
        all_records = []
        for path in paths:
            records = read_records([path])
            self.assertEqual(validate_control_records(records), [], path.name)
            all_records.extend(records)
        languages = {record["language"] for record in all_records}
        self.assertTrue({"cs", "de", "en", "es", "fr", "it", "pt"} <= languages)
        self.assertEqual(
            {record["control"] for record in all_records},
            {
                "allowed_domains",
                "disabled_domains",
                "interpretation_mode",
                "normalize_literals",
                "sequence_fallback_mode",
            },
        )


if __name__ == "__main__":
    unittest.main()
