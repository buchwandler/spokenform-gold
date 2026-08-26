import copy
import json
import tempfile
import unittest
from pathlib import Path

from spokenform_gold.corrections import apply_correction, prepare_correction_context
from spokenform_gold.io import read_records
from spokenform_gold.oracle import oracle_hash
from spokenform_gold.review import sentence_oracle_id
from spokenform_gold.review_lineage import backfill_legacy_evidence

ROOT = Path(__file__).resolve().parents[1]


class CorrectionTests(unittest.TestCase):
    def setUp(self):
        self.record = next(
            record
            for record in read_records([ROOT / "data/test/sample.jsonl"])
            if record["id"] == "en-us-time-001"
        )

    def correction(self, proposed):
        return {
            "record_id": self.record["id"],
            "old_oracle_hash": self.record["oracle_hash"],
            "new_oracle_hash": oracle_hash(proposed),
            "reason": "fixture correction",
            "reviewed_by": ["review-a", "review-b"],
            "adjudicator": "adjudicator-1",
            "review_revision": 1,
            "previous_review_evidence_hash": "legacy-none",
            "new_review_evidence_hash": "pending",
            "new_record": proposed,
        }

    def test_normal_correction_preserves_id_and_records_history(self):
        proposed = copy.deepcopy(self.record)
        proposed["notes"] = "corrected"
        updated, history = apply_correction(self.record, self.correction(proposed))
        self.assertEqual(updated["id"], self.record["id"])
        self.assertEqual(updated["family_id"], self.record["family_id"])
        self.assertTrue(updated["review"]["corrected"])
        self.assertEqual(updated["review"]["correction_history"][0], history)

    def test_input_correction_changes_derived_identity_not_record_id(self):
        proposed = copy.deepcopy(self.record)
        proposed["input"] = "Alarm at 09:05."
        proposed["units"] = copy.deepcopy(self.record["units"])
        proposed["units"][0]["surface"] = "09:05"
        proposed["units"][0]["semantic"] = {"hour": 9, "minute": 5}
        proposed["units"][0]["canonical"] = "nine oh five"
        proposed["units"][0]["accepted"] = ["nine oh five"]
        proposed["oracle"] = {
            "canonical_output": "Alarm at nine oh five.",
            "accepted_outputs": ["Alarm at nine oh five."],
            "rejected_outputs": [],
            "variant_mode": "explicit",
            "comparison_profile": "sentence-exact-v1",
        }
        proposed["expected_output"] = proposed["oracle"]["canonical_output"]
        updated, history = apply_correction(self.record, self.correction(proposed))
        self.assertEqual(updated["id"], self.record["id"])
        self.assertNotEqual(
            history["previous_sentence_oracle_id"], history["sentence_oracle_id"]
        )
        self.assertEqual(history["sentence_oracle_id"], sentence_oracle_id(updated))

    def test_record_id_change_is_rejected(self):
        proposed = copy.deepcopy(self.record)
        proposed["id"] = "renamed"
        with self.assertRaisesRegex(ValueError, "record.id is immutable"):
            apply_correction(self.record, self.correction(proposed))

    def test_prepare_context_has_human_artifacts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = prepare_correction_context(
                self.record, [], Path(tmpdir) / "correction", template="# <RECORD_ID>"
            )
            self.assertEqual(set(paths), {"context", "decision", "task", "report"})
            self.assertIn(self.record["id"], paths["task"].read_text())
            self.assertTrue(paths["report"].exists())

    def test_prepare_context_deduplicates_review_history(self):
        entry = backfill_legacy_evidence([self.record])[0]
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = prepare_correction_context(
                self.record,
                [entry, copy.deepcopy(entry)],
                Path(tmpdir) / "correction",
                template="# <RECORD_ID>",
            )
            context = json.loads(paths["context"].read_text())
            self.assertEqual(len(context["review_history"]), 1)


if __name__ == "__main__":
    unittest.main()
