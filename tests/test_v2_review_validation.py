from __future__ import annotations

import contextlib
import copy
import io
import tempfile
import unittest
from pathlib import Path

from spokenform_gold.cli import main
from spokenform_gold.collection import blind_case, collect_batch
from spokenform_gold.io import read_records, write_jsonl
from spokenform_gold.review import (
    blind_review_batch,
    detect_review_contract,
    validate_v2_review_rows,
)
from spokenform_gold.workflow import check_reviews

ROOT = Path(__file__).resolve().parents[1]


def v2_case() -> dict:
    return {
        "case_id": "case-1",
        "language": "en",
        "locale": "en-US",
        "input": "Value 3/4.",
        "family_id": None,
    }


def completed_v2(slot: str = "A", reviewer_id: str = "reviewer-a") -> dict:
    row = blind_case(v2_case(), slot)
    row["reviewer_id"] = reviewer_id
    row["annotation"] = {
        "status": "no_change",
        "expected_output": row["input"],
        "units": [],
        "negative_for": ["fraction-normalization"],
        "oracle": {
            "canonical_output": row["input"],
            "accepted_outputs": [row["input"]],
            "rejected_outputs": [],
        },
    }
    row["review"] = {
        "status": f"review_{slot.lower()}_complete",
        "protocol_version": "2.0.0",
    }
    return row


def completed_canonical(slot: str = "A", reviewer_id: str = "reviewer-a") -> dict:
    record = read_records([ROOT / "data/test/sample.jsonl"])[0]
    row = blind_review_batch([record], reviewer_slot=slot)[0]
    row["reviewer_id"] = reviewer_id
    row["annotation"] = {
        "status": record["status"],
        "expected_output": record["expected_output"],
        "units": copy.deepcopy(record["units"]),
        "negative_for": copy.deepcopy(record.get("negative_for", [])),
        "oracle": copy.deepcopy(record["oracle"]),
    }
    row["review"] = {
        "status": "unreviewed",
        "protocol_version": "1.0.0",
    }
    row["review"]["status"] = f"review_{slot.lower()}_complete"
    return row


class V2ReviewValidationTests(unittest.TestCase):
    def test_valid_v2_cli_and_auto_detection(self):
        row = completed_v2()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.complete.jsonl"
            write_jsonl(path, [row])
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = main(
                    ["validate-review", str(path), "--slot", "A", "--contract", "v2"]
                )
            self.assertEqual(code, 0)
            self.assertIn("review_contract=sentence-centric-v2", output.getvalue())
            self.assertIn("ready=yes", output.getvalue())
            self.assertNotIn("sentence_oracle_id error", output.getvalue())
            self.assertEqual(detect_review_contract([row]), "v2")

    def test_canonical_cli_and_auto_detection_remain_compatible(self):
        row = completed_canonical()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "canonical-a.complete.jsonl"
            write_jsonl(path, [row])
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = main(["validate-review", str(path), "--slot", "A"])
            self.assertEqual(code, 0)
            self.assertIn("canonical_review_state=ready", output.getvalue())
            self.assertEqual(detect_review_contract([row]), "canonical")

    def test_mixed_contracts_fail_closed(self):
        rows = [completed_v2(), completed_canonical()]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "mixed.jsonl"
            write_jsonl(path, rows)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = main(["validate-review", str(path), "--slot", "A"])
            self.assertEqual(code, 2)
            self.assertIn("mixes sentence-centric v2 and canonical", output.getvalue())
            self.assertEqual(detect_review_contract(rows), "indeterminate")

    def test_v2_identity_lifecycle_and_annotation_failures(self):
        cases = [
            ("duplicate_case_id", lambda row: None),
            ("invalid_lifecycle", lambda row: row["review"].update({"status": "review_b_complete"})),
            ("incomplete_annotation", lambda row: row.update({"annotation": None})),
            ("invalid_oracle", lambda row: row["annotation"]["oracle"].update({"accepted_outputs": []})),
            ("oracle_variant_overlap", lambda row: row["annotation"]["oracle"].update({"rejected_outputs": [row["input"]]})),
            ("invalid_no_change", lambda row: row["annotation"].update({"negative_for": []})),
        ]
        for code, mutate in cases:
            with self.subTest(code=code):
                row = completed_v2()
                if code == "duplicate_case_id":
                    report = validate_v2_review_rows([row, copy.deepcopy(row)], slot="A")
                else:
                    mutate(row)
                    report = validate_v2_review_rows([row], slot="A")
                self.assertFalse(report["ready"])
                self.assertIn(code, {issue["code"] for issue in report["issues"]})

    def test_v2_oracle_and_unit_invariants(self):
        row = completed_v2()
        row["annotation"]["expected_output"] = "different"
        report = validate_v2_review_rows([row], slot="A")
        self.assertIn("oracle_output_mismatch", {issue["code"] for issue in report["issues"]})

        row = completed_v2()
        row["annotation"]["units"] = [
            {"canonical": "three quarters", "accepted": [], "rejected": []}
        ]
        report = validate_v2_review_rows([row], slot="A")
        self.assertIn("invalid_unit", {issue["code"] for issue in report["issues"]})

    def test_unstable_reviewer_identity_fails(self):
        first = completed_v2(reviewer_id="reviewer-a")
        second = copy.deepcopy(first)
        second["case_id"] = "case-2"
        second["reviewer_id"] = "reviewer-b"
        report = validate_v2_review_rows([first, second], slot="A")
        self.assertFalse(report["ready"])
        self.assertIn("unstable_reviewer_id", {issue["code"] for issue in report["issues"]})

    def test_review_check_preserves_context_and_reuses_v2_validation(self):
        case = v2_case()
        review_a = completed_v2("A", "reviewer-a")
        review_b = completed_v2("B", "reviewer-b")
        self.assertTrue(check_reviews([case], [review_a], [review_b])["ready"])

        for field, value in ((
            "input",
            "Changed 3/4.",
        ), (
            "language",
            "de",
        ), (
            "locale",
            "de-DE",
        ), (
            "family_id",
            "family-2",
        )):
            with self.subTest(field=field):
                changed = copy.deepcopy(review_b)
                changed[field] = value
                result = check_reviews([case], [review_a], [changed])
                self.assertFalse(result["ready"])
                self.assertTrue(any("context mismatch" in issue for issue in result["issues"]))

        malformed = copy.deepcopy(review_a)
        malformed["annotation"] = None
        result = check_reviews([case], [malformed], [review_b])
        self.assertFalse(result["ready"])
        self.assertTrue(any("annotation must be an object" in issue for issue in result["issues"]))

    def test_collect_to_review_check_smoke(self):
        observations = [
            {
                "language": "en",
                "locale": "en-US",
                "input": "Value 3/4.",
                "source": {
                    "benchmark": "fixture",
                    "source_id": "source-1",
                    "source_version": "v1",
                },
            }
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            observation_path = root / "observations.jsonl"
            batch_root = root / "batch-0001"
            write_jsonl(observation_path, observations)
            collect_batch(
                [observation_path],
                output_root=batch_root,
                batch_id="batch-0001",
                limit=1000,
            )
            a_rows = read_records([batch_root / "a.blind.jsonl"])
            b_rows = read_records([batch_root / "b.blind.jsonl"])
            for rows, slot, reviewer in (
                (a_rows, "A", "reviewer-a"),
                (b_rows, "B", "reviewer-b"),
            ):
                for row in rows:
                    completed = completed_v2(slot, reviewer)
                    for field in ("case_id", "language", "locale", "input", "family_id"):
                        completed[field] = row[field]
                    row.clear()
                    row.update(completed)
            self.assertEqual(validate_v2_review_rows(a_rows, slot="A")["ready"], True)
            self.assertEqual(validate_v2_review_rows(b_rows, slot="B")["ready"], True)
            cases = read_records([batch_root / "cases.jsonl"])
            self.assertTrue(check_reviews(cases, a_rows, b_rows)["ready"])


if __name__ == "__main__":
    unittest.main()
