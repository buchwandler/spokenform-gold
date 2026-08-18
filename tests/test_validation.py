import copy
import unittest
from pathlib import Path

from spokenform_gold.io import read_records
from spokenform_gold.validation import validate_records


ROOT = Path(__file__).resolve().parents[1]


class ValidationTests(unittest.TestCase):
    def test_samples_are_valid(self):
        records = read_records([ROOT / "data/dev", ROOT / "data/test"])
        self.assertEqual(validate_records(records), [])

    def test_duplicate_id_is_rejected(self):
        records = read_records([ROOT / "data/dev/sample.jsonl"])
        records.append(dict(records[0]))
        self.assertTrue(
            any("duplicate id" in error for error in validate_records(records))
        )

    def test_missing_source_version_is_rejected(self):
        records = read_records([ROOT / "data/dev/sample.jsonl"])
        broken = copy.deepcopy(records[0])
        del broken["source"]["source_version"]
        errors = validate_records([broken])
        self.assertTrue(
            any("source.source_version is required" in error for error in errors)
        )

    def test_invalid_policy_is_rejected(self):
        records = read_records([ROOT / "data/dev/sample.jsonl"])
        broken = copy.deepcopy(records[0])
        broken["units"][0]["policy"] = "missing-policy"
        errors = validate_records([broken])
        self.assertTrue(any("unknown policy" in error for error in errors))

    def test_invalid_semantic_is_rejected(self):
        records = read_records([ROOT / "data/test/sample.jsonl"])
        broken = copy.deepcopy(records[0])
        broken["units"][0]["semantic"] = {"hour": 28, "minute": 0}
        errors = validate_records([broken])
        self.assertTrue(any("time hour out of range" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
