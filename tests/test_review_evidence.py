import copy
import json
import tempfile
import unittest
from pathlib import Path

from spokenform_gold.io import read_records
from spokenform_gold.oracle import oracle_hash
from spokenform_gold.review import (
    _rejected_output_strings,
    apply_reviewed_oracles,
    blind_review_batch,
    compare_review_batches,
    review_preflight,
    sentence_oracle_id,
    validate_review_rows,
    write_review_application,
)
from spokenform_gold.validation import validate_records

ROOT = Path(__file__).resolve().parents[1]


class ReviewEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.record = read_records([ROOT / "data/test/sample.jsonl"])[0]
        self.review_a = self._completed("reviewer-a", "A")
        self.review_b = self._completed("reviewer-b", "B")

    def _completed(self, reviewer_id, slot):
        row = blind_review_batch([self.record], reviewer_slot=slot)[0]
        row["reviewer_id"] = reviewer_id
        row["annotation"] = {
            "status": self.record["status"],
            "expected_output": self.record["expected_output"],
            "units": copy.deepcopy(self.record["units"]),
            "negative_for": copy.deepcopy(self.record["negative_for"]),
            "notes": "Independent review fixture.",
            "oracle": copy.deepcopy(self.record["oracle"]),
        }
        row["review"] = {
            "status": "review_a_complete" if slot == "A" else "review_b_complete",
            "protocol_version": "1.0.0",
        }
        return row

    def _decision(self):
        return {
            "sentence_oracle_id": self.review_a["sentence_oracle_id"],
            "record_id": self.record["id"],
            "family_id": self.record["family_id"],
            "reviewers": ["reviewer-a", "reviewer-b"],
            "adjudicator": "maintainer-1",
            "decision": "adjudicated",
            "review_status": "adjudicated",
            "status": self.record["status"],
            "input": self.record["input"],
            "language": self.record["language"],
            "locale": self.record["locale"],
            "expected_output": self.record["expected_output"],
            "units": copy.deepcopy(self.record["units"]),
            "negative_for": copy.deepcopy(self.record["negative_for"]),
            "notes": "Adjudicated review fixture.",
            "oracle": copy.deepcopy(self.record["oracle"]),
            "disagreement": {"semantic": False},
            "source_error_codes": [],
        }

    def test_compare_requires_distinct_completed_reviewers(self):
        result = compare_review_batches([self.review_a], [self.review_b])
        self.assertEqual(result[0]["state"], "agreement")
        self.assertEqual(result[0]["reviewer_a"], "reviewer-a")
        self.assertEqual(result[0]["reviewer_b"], "reviewer-b")

        same = copy.deepcopy(self.review_b)
        same["reviewer_id"] = "reviewer-a"
        with self.assertRaisesRegex(ValueError, "distinct"):
            compare_review_batches([self.review_a], [same])

    def test_compare_rejects_context_mismatch(self):
        other = copy.deepcopy(self.review_b)
        other["locale"] = "de-DE"
        with self.assertRaisesRegex(ValueError, "locale"):
            compare_review_batches([self.review_a], [other])

    def test_apply_preserves_identity_and_recomputes_oracle_hash(self):
        updated, comparisons, report = apply_reviewed_oracles(
            [self.record], [self.review_a], [self.review_b], [self._decision()]
        )
        result = updated[0]
        self.assertEqual(result["id"], self.record["id"])
        self.assertEqual(result["family_id"], self.record["family_id"])
        self.assertEqual(result["source"], self.record["source"])
        self.assertEqual(result["review"]["status"], "adjudicated")
        self.assertEqual(result["review"]["reviewers"], ["reviewer-a", "reviewer-b"])
        self.assertEqual(result["oracle_hash"], oracle_hash(result))
        self.assertEqual(validate_records(updated), [])
        self.assertEqual(report["agreement"], 1)
        self.assertEqual(len(comparisons), 1)

    def test_apply_rejects_malformed_canonical_decision_shapes(self):
        cases = []
        missing_oracle = self._decision()
        missing_oracle.pop("oracle")
        cases.append((missing_oracle, "missing oracle"))
        one_reviewer = self._decision()
        one_reviewer["reviewers"] = ["reviewer-a"]
        cases.append((one_reviewer, "two distinct"))
        empty_adjudicator = self._decision()
        empty_adjudicator["adjudicator"] = ""
        cases.append((empty_adjudicator, "adjudicator"))
        invalid_review_status = self._decision()
        invalid_review_status["review_status"] = "unreviewed"
        cases.append((invalid_review_status, "review_status"))
        invalid_record_status = self._decision()
        invalid_record_status["status"] = "quarantine"
        cases.append((invalid_record_status, "invalid record status"))
        malformed_unit = self._decision()
        if malformed_unit["units"]:
            malformed_unit["units"][0]["accepted"] = []
        else:
            malformed_unit["units"] = [{"surface": "x"}]
        cases.append((malformed_unit, "canonical must be in accepted"))
        for decision, message in cases:
            with (
                self.subTest(message=message),
                self.assertRaisesRegex(ValueError, "invalid canonical review decision"),
            ):
                apply_reviewed_oracles(
                    [self.record], [self.review_a], [self.review_b], [decision]
                )

    def test_apply_requires_all_decisions_and_rejects_family_migration(self):
        with self.assertRaisesRegex(ValueError, "missing adjudication"):
            apply_reviewed_oracles([self.record], [self.review_a], [self.review_b], [])
        decision = self._decision()
        decision["family_id"] = "new-family"
        with self.assertRaisesRegex(ValueError, "family_id"):
            apply_reviewed_oracles(
                [self.record], [self.review_a], [self.review_b], [decision]
            )

    def test_output_tree_is_new_and_contains_reported_artifacts(self):
        updated, comparisons, report = apply_reviewed_oracles(
            [self.record], [self.review_a], [self.review_b], [self._decision()]
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "reviewed"
            write_review_application(
                output,
                updated,
                comparisons,
                report,
                input_paths=[ROOT / "data/test/sample.jsonl"],
            )
            self.assertEqual(
                read_records([output / "records.jsonl"])[0]["id"], self.record["id"]
            )
            self.assertEqual(
                json.loads((output / "report.json").read_text())["records"], 1
            )

    def test_output_under_canonical_input_is_rejected(self):
        updated, comparisons, report = apply_reviewed_oracles(
            [self.record], [self.review_a], [self.review_b], [self._decision()]
        )
        with self.assertRaisesRegex(ValueError, "overlaps"):
            write_review_application(
                ROOT / "data/test/reviewed-output",
                updated,
                comparisons,
                report,
                input_paths=[ROOT / "data/test/sample.jsonl"],
            )

    def test_preflight_reports_blank_reviews_and_canonical_identity_parity(self):
        blank_a = blind_review_batch([self.record], reviewer_slot="A")
        blank_b = blind_review_batch([self.record], reviewer_slot="B")
        report = review_preflight([self.record], blank_a, blank_b)
        self.assertFalse(report["ready"])
        self.assertEqual(report["review_a"]["completed"], 0)
        self.assertEqual(report["review_b"]["completed"], 0)
        self.assertTrue(report["canonical_identity_match"])
        codes = {issue["code"] for issue in report["issues"]}
        self.assertIn("missing_reviewer_id", codes)
        self.assertIn("incomplete_annotations", codes)
        self.assertIn("unreviewed_rows", codes)

    def test_preflight_ready_state_uses_derived_canonical_identity(self):
        report = review_preflight([self.record], [self.review_a], [self.review_b])
        self.assertTrue(report["ready"])
        self.assertTrue(report["canonical_identity_match"])
        self.assertTrue(report["id_sets_match"])
        self.assertTrue(report["context_match"])
        self.assertNotIn("sentence_oracle_id", self.record)
        self.assertEqual(
            self.review_a["sentence_oracle_id"], sentence_oracle_id(self.record)
        )

    def test_preflight_reports_shared_reviewer(self):
        same = copy.deepcopy(self.review_b)
        same["reviewer_id"] = "reviewer-a"
        report = review_preflight([self.record], [self.review_a], [same])
        self.assertFalse(report["ready"])
        self.assertIn(
            "shared_reviewer_id", {issue["code"] for issue in report["issues"]}
        )

    def test_preflight_reports_slot_duplicate_id_and_context_mismatches(self):
        wrong_slot = copy.deepcopy(self.review_b)
        wrong_slot["reviewer_slot"] = "A"
        report = review_preflight([self.record], [self.review_a], [wrong_slot])
        self.assertIn("slot_mismatch", {issue["code"] for issue in report["issues"]})

        duplicate = [copy.deepcopy(self.review_b), copy.deepcopy(self.review_b)]
        report = review_preflight([self.record], [self.review_a], duplicate)
        self.assertIn(
            "duplicate_oracle_id", {issue["code"] for issue in report["issues"]}
        )

        context = copy.deepcopy(self.review_b)
        context["locale"] = "de-DE"
        report = review_preflight([self.record], [self.review_a], [context])
        self.assertIn("context_mismatch", {issue["code"] for issue in report["issues"]})

    def test_preflight_reports_id_set_and_canonical_identity_mismatch(self):
        unknown = copy.deepcopy(self.review_b)
        unknown["sentence_oracle_id"] = "oracle-unknown"
        report = review_preflight([self.record], [self.review_a], [unknown])
        codes = {issue["code"] for issue in report["issues"]}
        self.assertIn("missing_in_a", codes)
        self.assertIn("unknown_review_identity", codes)

    def test_validate_review_accepts_dict_form_rejected_outputs(self):
        row = copy.deepcopy(self.review_b)
        row["annotation"]["oracle"]["rejected_outputs"] = [
            {"output": "Wrong sentence.", "reason": "changes the meaning"}
        ]
        report = validate_review_rows([row], slot="B")
        self.assertTrue(report["ready"], report["issues"])

    def test_validate_review_accepts_ambiguous_oracle_without_canonical(self):
        row = copy.deepcopy(self.review_a)
        row["annotation"]["status"] = "ambiguous"
        row["annotation"]["oracle"] = {
            "canonical_output": None,
            "accepted_outputs": [],
            "rejected_outputs": [],
            "variant_mode": "explicit",
            "comparison_profile": "sentence-exact-v1",
            "interpretations": [
                {
                    "label": "first",
                    "semantic": {"value": "one"},
                    "accepted_outputs": ["one"],
                },
                {
                    "label": "second",
                    "semantic": {"value": "two"},
                    "accepted_outputs": ["two"],
                },
            ],
        }
        report = validate_review_rows([row], slot="A")
        self.assertTrue(report["ready"], report["issues"])

    def test_validate_review_flags_oracle_overlap_with_dict_form_outputs(self):
        row = copy.deepcopy(self.review_b)
        canonical = row["annotation"]["oracle"]["canonical_output"]
        row["annotation"]["oracle"]["rejected_outputs"] = [
            {"output": canonical, "reason": "duplicate of the canonical output"}
        ]
        report = validate_review_rows([row], slot="B")
        codes = {issue["code"] for issue in report["issues"]}
        self.assertIn("oracle_variant_overlap", codes)

    def test_rejected_output_strings_handles_mixed_forms(self):
        self.assertEqual(
            _rejected_output_strings(
                ["plain", {"output": "dict", "reason": "why"}, {"no": "output"}]
            ),
            {"plain", "dict"},
        )


if __name__ == "__main__":
    unittest.main()
