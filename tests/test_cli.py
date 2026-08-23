import contextlib
import hashlib
import io
import json
import shutil
import unittest
from copy import deepcopy
from pathlib import Path

from spokenform_gold.cli import build_parser, main
from spokenform_gold.io import read_records, write_jsonl
from spokenform_gold.review import blind_review_batch, sentence_oracle_id

ROOT = Path(__file__).resolve().parents[1]


class CliReviewWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.work = ROOT / "reports" / "test-cli-review-workflow"
        shutil.rmtree(self.work, ignore_errors=True)
        self.work.mkdir(parents=True)
        self.records_path = ROOT / "data" / "test" / "sample.jsonl"
        self.records = read_records([self.records_path])

    def tearDown(self):
        shutil.rmtree(self.work, ignore_errors=True)

    def _reviews(self):
        by_identity = {sentence_oracle_id(record): record for record in self.records}
        result = []
        for slot, reviewer_id in (("A", "reviewer-a"), ("B", "reviewer-b")):
            rows = blind_review_batch(self.records, reviewer_slot=slot)
            for row in rows:
                record = by_identity[row["sentence_oracle_id"]]
                row["reviewer_id"] = reviewer_id
                row["annotation"] = {
                    "status": record["status"],
                    "expected_output": record["expected_output"],
                    "units": deepcopy(record["units"]),
                    "negative_for": deepcopy(record["negative_for"]),
                    "notes": "CLI test review.",
                    "oracle": deepcopy(record["oracle"]),
                }
                row["review"]["status"] = f"review_{slot.lower()}_complete"
            result.append(rows)
        return result

    def test_review_commands_are_exposed(self):
        help_text = build_parser().format_help()
        self.assertIn("review-preflight", help_text)
        self.assertIn("validate-review", help_text)
        self.assertIn("doctor", help_text)
        self.assertIn("prepare-canonical-rereview", help_text)

    def test_blocked_preflight_returns_two_and_is_aggregate(self):
        review_a = self.work / "canonical-a.blind.jsonl"
        review_b = self.work / "canonical-b.blind.jsonl"
        write_jsonl(review_a, blind_review_batch(self.records, reviewer_slot="A"))
        write_jsonl(review_b, blind_review_batch(self.records, reviewer_slot="B"))
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main([
                "review-preflight",
                "--records", str(self.records_path),
                "--review-a", str(review_a),
                "--review-b", str(review_b),
                "--json", str(self.work / "preflight.json"),
            ])
        self.assertEqual(code, 2)
        text = output.getvalue()
        self.assertIn("canonical_review_state=blocked", text)
        self.assertIn("review A has no reviewer_id", text)
        self.assertIn("review B has no reviewer_id", text)
        self.assertEqual(json.loads((self.work / "preflight.json").read_text())["ready"], False)
        self.assertFalse((self.work / "comparison.jsonl").exists())

    def test_ready_preflight_returns_zero_and_json_is_deterministic(self):
        review_a, review_b = self._reviews()
        path_a = self.work / "canonical-a.complete.jsonl"
        path_b = self.work / "canonical-b.complete.jsonl"
        write_jsonl(path_a, review_a)
        write_jsonl(path_b, review_b)
        json_a = self.work / "preflight-a.json"
        json_b = self.work / "preflight-b.json"
        args = [
            "review-preflight", "--records", str(self.records_path),
            "--review-a", str(path_a), "--review-b", str(path_b),
        ]
        self.assertEqual(main([*args, "--json", str(json_a)]), 0)
        self.assertEqual(main([*args, "--json", str(json_b)]), 0)
        self.assertEqual(json_a.read_text(), json_b.read_text())
        report = json.loads(json_a.read_text())
        self.assertTrue(report["ready"])
        self.assertTrue(report["canonical_identity_match"])

    def test_compare_validation_error_has_no_traceback(self):
        output = io.StringIO()
        errors = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            code = main([
                "compare-reviews", str(self.records_path), str(self.records_path),
                "--out", str(self.work / "comparison.jsonl"),
            ])
        self.assertEqual(code, 2)
        self.assertIn("error:", errors.getvalue())
        self.assertNotIn("Traceback", errors.getvalue())

    def test_preflight_aggregates_missing_and_malformed_review_artifacts(self):
        missing = self.work / "missing.complete.jsonl"
        malformed = self.work / "malformed.complete.jsonl"
        malformed.write_text("not-json\n", encoding="utf-8")
        report_path = self.work / "preflight-errors.json"
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main([
                "review-preflight",
                "--records", str(self.records_path),
                "--review-a", str(missing),
                "--review-b", str(malformed),
                "--json", str(report_path),
            ])
        self.assertEqual(code, 2)
        self.assertIn("file_not_readable", report_path.read_text())
        self.assertIn("invalid_jsonl", report_path.read_text())
        self.assertIn("ready=no", output.getvalue())
        self.assertNotIn("Traceback", output.getvalue())
        self.assertFalse((self.work / "comparison.jsonl").exists())


    def test_validate_review_missing_artifact_is_cleanly_blocked(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main([
                "validate-review",
                str(self.work / "missing.complete.jsonl"),
                "--slot", "A",
            ])
        self.assertEqual(code, 2)
        self.assertIn("file is missing", output.getvalue())
        self.assertIn("ready=no", output.getvalue())

    def test_prepare_canonical_rereview_writes_blind_artifacts_and_manifest(self):
        output_root = self.work / "canonical"
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main([
                "prepare-canonical-rereview",
                "--records", str(self.records_path),
                "--out-root", str(output_root),
                "--review-id", "test-review",
            ])
        self.assertEqual(code, 0)
        self.assertTrue((output_root / "canonical-a.blind.jsonl").is_file())
        self.assertTrue((output_root / "canonical-b.blind.jsonl").is_file())
        manifest = json.loads((output_root / "manifest.json").read_text())
        self.assertEqual(manifest["review_id"], "test-review")
        self.assertEqual(manifest["review_a"]["sha256"], hashlib.sha256((output_root / "canonical-a.blind.jsonl").read_bytes()).hexdigest())
        self.assertIn("canonical-a.blind.jsonl", output.getvalue())


    def test_doctor_reports_configured_paths(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(["doctor", "--json", str(self.work / "doctor.json")])
        self.assertEqual(code, 0)
        self.assertIn("source_cache:", output.getvalue())
        report = json.loads((self.work / "doctor.json").read_text())
        self.assertIn("work_root", report)
        self.assertEqual(len(report["canonical_records"]), 3)

if __name__ == "__main__":
    unittest.main()
