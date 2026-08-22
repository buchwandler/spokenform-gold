import copy
import unittest
from pathlib import Path

from spokenform_gold.io import read_records
from spokenform_gold.oracle import canonical_unit_reconstruction, oracle_hash
from spokenform_gold.scoring import score_records
from spokenform_gold.validation import validate_records

ROOT = Path(__file__).resolve().parents[1]


class SentenceOracleTests(unittest.TestCase):
    def test_migrated_canonical_records_have_explicit_oracles(self):
        records = read_records([ROOT / "data/dev", ROOT / "data/test"])
        self.assertEqual(validate_records(records), [])
        for record in records:
            if record["status"] in {"gold", "multi_valid", "policy_choice"}:
                self.assertEqual(record["expected_output"], record["oracle"]["canonical_output"])
                self.assertEqual(canonical_unit_reconstruction(record), record["expected_output"])
                self.assertEqual(record["oracle_hash"], oracle_hash(record))

    def test_duplicate_accepted_outputs_fail(self):
        record = copy.deepcopy(read_records([ROOT / "data/test"])[0])
        record["oracle"]["accepted_outputs"] = [record["expected_output"], record["expected_output"]]
        record["oracle_hash"] = oracle_hash(record)
        self.assertTrue(any("accepted_outputs contains duplicates" in error for error in validate_records([record])))

    def test_accepted_rejected_overlap_fails(self):
        record = copy.deepcopy(read_records([ROOT / "data/test"])[0])
        record["oracle"]["rejected_outputs"] = [{"output": record["expected_output"], "reason": "test"}]
        record["oracle_hash"] = oracle_hash(record)
        self.assertTrue(any("accepted/rejected overlap" in error for error in validate_records([record])))

    def test_reconstruction_mismatch_fails(self):
        record = copy.deepcopy(read_records([ROOT / "data/test"])[0])
        record["oracle"]["canonical_output"] = "not the reconstructed sentence"
        record["expected_output"] = record["oracle"]["canonical_output"]
        record["oracle"]["accepted_outputs"] = [record["expected_output"]]
        record["oracle_hash"] = oracle_hash(record)
        self.assertTrue(any("canonical unit reconstruction" in error for error in validate_records([record])))

    def test_no_change_and_ambiguous_contracts_are_explicit(self):
        records = read_records([ROOT / "data/dev"])
        no_change = next(record for record in records if record["status"] == "no_change")
        ambiguous = next(record for record in records if record["status"] == "ambiguous")
        self.assertEqual(no_change["oracle"]["accepted_outputs"], [no_change["input"]])
        self.assertGreaterEqual(len(ambiguous["oracle"]["interpretations"]), 2)

    def test_multi_unit_scoring_does_not_accept_unreviewed_cartesian_combination(self):
        record = {
            "id": "multi", "status": "multi_valid", "split": "test", "language": "en", "locale": "en-US",
            "input": "Use 1/2 and 3/4.", "expected_output": "Use one half and three quarters.",
            "units": [
                {"start": 4, "end": 7, "canonical": "one half", "accepted": ["one half", "a half"]},
                {"start": 12, "end": 15, "canonical": "three quarters", "accepted": ["three quarters", "three fourths"]},
            ],
            "oracle": {"canonical_output": "Use one half and three quarters.", "accepted_outputs": ["Use one half and three quarters.", "Use a half and three fourths."], "rejected_outputs": [], "variant_mode": "explicit"},
        }
        predictions = {"multi": "Use one half and three fourths."}
        result = score_records([record], predictions, mode="accepted")
        self.assertEqual(result["accepted_variant_accuracy"], 0.0)

    def test_explicit_variant_set_has_no_legacy_256_cap(self):
        record = {"id": "many", "status": "gold", "split": "test", "language": "en", "locale": "en-US", "input": "x", "expected_output": "canonical", "units": []}
        record["oracle"] = {"canonical_output": "canonical", "accepted_outputs": ["canonical"] + [f"variant-{i}" for i in range(300)], "rejected_outputs": [], "variant_mode": "explicit"}
        result = score_records([record], {"many": "variant-299"}, mode="accepted")
        self.assertEqual(result["accepted_variant_accuracy"], 1.0)

    def test_hash_excludes_notes_but_changes_with_semantics(self):
        record = copy.deepcopy(read_records([ROOT / "data/test"])[0])
        original = oracle_hash(record)
        record["notes"] = "volatile note"
        self.assertEqual(original, oracle_hash(record))
        record["units"][0]["semantic"] = {"changed": True}
        self.assertNotEqual(original, oracle_hash(record))

    def test_reviewed_record_without_oracle_fails(self):
        record = copy.deepcopy(read_records([ROOT / "data/test"])[0])
        del record["oracle"]
        self.assertTrue(any("require an oracle object" in error for error in validate_records([record])))


if __name__ == "__main__":
    unittest.main()
