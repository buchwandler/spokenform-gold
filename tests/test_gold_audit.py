import copy
import unittest
from pathlib import Path

from spokenform_gold.corpus import sentence_key
from spokenform_gold.gold_audit import audit_records, find_reviewed_oracle_conflicts
from spokenform_gold.io import read_records

ROOT = Path(__file__).resolve().parents[1]


class GoldAuditTests(unittest.TestCase):
    def test_non_strict_audit_passes_migrated_seed(self):
        report = audit_records(read_records([ROOT / "data/dev", ROOT / "data/test"]))
        self.assertTrue(report["oracle_complete"])
        self.assertEqual(report["reviewed_oracle_conflicts"], [])

    def test_strict_audit_passes_canonical_rereviewed_test(self):
        report = audit_records(read_records([ROOT / "data/test"]), strict=True)
        self.assertTrue(report["oracle_complete"])
        self.assertEqual(report["review_gap_records"], [])
        self.assertEqual(report["review_complete_records"], 11)

    def test_same_input_conflicting_reviewed_oracles_are_detected(self):
        records = read_records([ROOT / "data/test"])[0:1]
        other = copy.deepcopy(records[0])
        other["id"] = "conflict"
        other["oracle"]["canonical_output"] = "different"
        records.append(other)
        self.assertTrue(find_reviewed_oracle_conflicts(records))

    def test_case_distinct_inputs_are_not_merged_by_canonical_identity(self):
        base = copy.deepcopy(read_records([ROOT / "data/test"])[0])
        left = copy.deepcopy(base)
        right = copy.deepcopy(base)
        left["id"] = "case-left"
        right["id"] = "case-right"
        left["input"] = "ABC"
        right["input"] = "abc"
        self.assertNotEqual(
            sentence_key("en", "en-US", left["input"]),
            sentence_key("en", "en-US", right["input"]),
        )
        self.assertEqual(find_reviewed_oracle_conflicts([left, right]), [])

    def test_nfkc_equivalent_inputs_still_conflict(self):
        base = copy.deepcopy(read_records([ROOT / "data/test"])[0])
        left = copy.deepcopy(base)
        right = copy.deepcopy(base)
        left["id"] = "nfkc-left"
        right["id"] = "nfkc-right"
        left["input"] = "A"
        right["input"] = "Ａ"
        right["oracle"]["canonical_output"] = "different"
        self.assertEqual(
            sentence_key("en", "en-US", left["input"]),
            sentence_key("en", "en-US", right["input"]),
        )
        self.assertTrue(find_reviewed_oracle_conflicts([left, right]))


if __name__ == "__main__":
    unittest.main()
