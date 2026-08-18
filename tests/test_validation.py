import unittest
from pathlib import Path
from spokenform_gold.io import read_jsonl
from spokenform_gold.validation import validate_records

ROOT = Path(__file__).resolve().parents[1]

class ValidationTests(unittest.TestCase):
    def test_sample_is_valid(self):
        records = read_jsonl(ROOT / "data/dev/sample.jsonl")
        self.assertEqual(validate_records(records), [])

    def test_duplicate_id_is_rejected(self):
        records = read_jsonl(ROOT / "data/dev/sample.jsonl")
        records.append(dict(records[0]))
        self.assertTrue(any("duplicate id" in e for e in validate_records(records)))

if __name__ == "__main__":
    unittest.main()
