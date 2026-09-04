import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from spokenform_gold.cli import build_parser, main
from spokenform_gold.io import read_jsonl, write_json, write_jsonl


class CliContextBudgetTests(unittest.TestCase):
    def test_v2_commands_are_registered(self):
        help_text = build_parser().format_help()
        for command in (
            "batch-status",
            "trace-case",
            "review-packet",
            "review-merge",
            "adjudication-packet",
            "adjudication-merge",
        ):
            self.assertIn(command, help_text)

    def test_batch_status_uses_configured_work_root_and_compact_output(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            root = work / "batches" / "batch-0001"
            root.mkdir(parents=True)
            case = {
                "case_id": "case-1",
                "language": "en",
                "locale": "en-US",
                "input": "Value 1.",
                "source_observations": [],
            }
            write_json(root / "batch.json", {"batch_id": "batch-0001", "case_count": 1})
            write_jsonl(root / "cases.jsonl", [case])
            write_jsonl(root / "a.complete.jsonl", [{"case_id": "case-1"}])
            write_jsonl(root / "b.complete.jsonl", [{"case_id": "case-1"}])
            write_json(root / "review-check.json", {"ready": True, "issues": []})
            write_jsonl(
                root / "adjudicated.jsonl",
                [{"case_id": "case-1", "decision": "accept"}],
            )
            write_json(root / "integration.json", {"state": "integrated"})

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = main(
                    [
                        "batch-status",
                        "--batch",
                        "batch-0001",
                        "--work-root",
                        str(work),
                    ]
                )

            self.assertEqual(code, 0)
            text = output.getvalue()
            self.assertLess(len(text), 4096)
            self.assertIn("batch_id=batch-0001", text)
            self.assertIn("review_ready=yes", text)
            self.assertIn("integrated=no", text)
            self.assertNotIn('"case_id"', text)

    def test_trace_case_is_exact_and_writes_detail_to_file(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            root = work / "batches" / "batch-0001"
            root.mkdir(parents=True)
            write_jsonl(
                root / "cases.jsonl",
                [
                    {
                        "case_id": "case-1",
                        "language": "en",
                        "locale": "en-US",
                        "input": "Value 1.",
                        "source_observations": [{"source_id": "source-1"}],
                    }
                ],
            )
            detail = work / "case.json"
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = main(
                    [
                        "trace-case",
                        "case-1",
                        "--batch",
                        "batch-0001",
                        "--work-root",
                        str(work),
                        "--json",
                        str(detail),
                    ]
                )

            self.assertEqual(code, 0)
            self.assertIn("case_id=case-1", output.getvalue())
            self.assertNotIn("source_observations", output.getvalue())
            self.assertEqual(json.loads(detail.read_text())["case_id"], "case-1")

    def test_review_packet_and_merge_commands(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "batch"
            root.mkdir()
            blind = {
                "review_schema_version": "2.0.0",
                "case_id": "case-1",
                "reviewer_slot": "A",
                "language": "en",
                "locale": "en-US",
                "input": "Value 1.",
                "family_id": "family-1",
                "annotation": None,
                "review": {"status": "unreviewed"},
            }
            write_jsonl(root / "a.blind.jsonl", [blind])
            packet = root / "packets" / "a-0001.jsonl"
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(
                    main(
                        [
                            "review-packet",
                            "--batch",
                            str(root),
                            "--slot",
                            "A",
                            "--out",
                            str(packet),
                        ]
                    ),
                    0,
                )
            self.assertEqual(read_jsonl(packet)[0]["case_id"], "case-1")
            result = dict(blind)
            result["reviewer_id"] = "reviewer-a"
            result["annotation"] = {
                "status": "gold",
                "expected_output": "Value 1.",
                "units": [],
                "negative_for": [],
                "oracle": {
                    "canonical_output": "Value 1.",
                    "accepted_outputs": ["Value 1."],
                    "rejected_outputs": [],
                },
            }
            result["review"] = {
                "status": "review_a_complete",
                "protocol_version": "2.0.0",
            }
            result_path = root / "result.jsonl"
            write_jsonl(result_path, [result])
            complete = root / "a.complete.jsonl"
            with contextlib.redirect_stdout(output):
                self.assertEqual(
                    main(
                        [
                            "review-merge",
                            "--batch",
                            str(root),
                            "--slot",
                            "A",
                            "--packet-result",
                            str(result_path),
                            "--out",
                            str(complete),
                        ]
                    ),
                    0,
                )
            self.assertEqual(read_jsonl(complete)[0]["reviewer_id"], "reviewer-a")

    def test_review_check_and_integrate_outputs_are_compact(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "cases.jsonl").write_text("\n", encoding="utf-8")
            (root / "a.jsonl").write_text("\n", encoding="utf-8")
            (root / "b.jsonl").write_text("\n", encoding="utf-8")
            review_result = {
                "ready": True,
                "cases": 1000,
                "issues": [],
                "review_a": {
                    "rows": 1000,
                    "reviewer_id": "a",
                    "case_ids": ["x"] * 1000,
                },
                "review_b": {
                    "rows": 1000,
                    "reviewer_id": "b",
                    "case_ids": ["x"] * 1000,
                },
            }
            output = io.StringIO()
            with (
                patch("spokenform_gold.cli.check_reviews", return_value=review_result),
                contextlib.redirect_stdout(output),
            ):
                code = main(
                    [
                        "review-check",
                        "--batch",
                        str(root),
                        "--review-a",
                        str(root / "a.jsonl"),
                        "--review-b",
                        str(root / "b.jsonl"),
                    ]
                )
            self.assertEqual(code, 0)
            self.assertLess(len(output.getvalue()), 4096)
            self.assertNotIn("case_ids", output.getvalue())
            output = io.StringIO()
            integration = {
                "records": 1000,
                "excluded": [{"case_id": "x"}],
                "synthetic_candidates": [{"case_id": "y"}],
            }
            with (
                patch("spokenform_gold.cli.integrate_batch", return_value=integration),
                contextlib.redirect_stdout(output),
            ):
                code = main(
                    [
                        "integrate",
                        "--batch",
                        str(root),
                        "--corpus",
                        str(root / "corpus.jsonl"),
                    ]
                )
            self.assertEqual(code, 0)
            self.assertLess(len(output.getvalue()), 4096)
            self.assertIn("records=1000", output.getvalue())
            self.assertNotIn("case_id", output.getvalue())


if __name__ == "__main__":
    unittest.main()
