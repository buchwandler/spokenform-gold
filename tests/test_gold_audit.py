import copy
import unittest
from pathlib import Path

from spokenform_gold.gold_audit import audit_records, find_reviewed_oracle_conflicts
from spokenform_gold.io import read_records

ROOT = Path(__file__).resolve().parents[1]


class GoldAuditTests(unittest.TestCase):
    def test_non_strict_audit_passes_migrated_seed(self):
        report = audit_records(read_records([ROOT / "data/dev", ROOT / "data/test"]))
        self.assertTrue(report["oracle_complete"])
        self.assertEqual(report["reviewed_oracle_conflicts"], [])

    def test_strict_audit_exposes_legacy_review_gap(self):
        report = audit_records(read_records([ROOT / "data/test"]), strict=True)
        self.assertFalse(report["oracle_complete"])
        self.assertTrue(report["review_gap_records"])

    def test_same_input_conflicting_reviewed_oracles_are_detected(self):
        records = read_records([ROOT / "data/test"])[0:1]
        other = copy.deepcopy(records[0])
        other["id"] = "conflict"
        other["oracle"]["canonical_output"] = "different"
        records.append(other)
        self.assertTrue(find_reviewed_oracle_conflicts(records))


if __name__ == "__main__":
    unittest.main()
