import copy
import unittest
from pathlib import Path

from spokenform_gold.io import read_records
from spokenform_gold.oracle import oracle_hash
from spokenform_gold.oracle_diff import correction_record, diff_records

ROOT = Path(__file__).resolve().parents[1]


class OracleDiffTests(unittest.TestCase):
    def test_diff_is_empty_for_identical_data(self):
        records = read_records([ROOT / "data/test"])
        self.assertEqual(diff_records(records, records)["counts"], {"added": 0, "removed": 0, "changed": 0})

    def test_diff_classifies_canonical_change_and_correction(self):
        old = read_records([ROOT / "data/test"])[0]
        new = copy.deepcopy(old)
        new["oracle"]["canonical_output"] = "changed"
        new["expected_output"] = "changed"
        new["oracle"]["accepted_outputs"] = ["changed"]
        new["oracle_hash"] = oracle_hash(new)
        report = diff_records([old], [new])
        self.assertEqual(report["changed"][0]["classification"], "canonical_change")
        correction = correction_record(old, new, reason="error_correction", reviewed_by=["r2", "r1"], adjudicator="a1")
        self.assertEqual(correction["reviewed_by"], ["r1", "r2"])


if __name__ == "__main__":
    unittest.main()
