import json
import tempfile
import unittest
from pathlib import Path

from spokenform_gold.io import write_json, write_jsonl
from spokenform_gold.rereview import (
    build_rereview_batch,
    mark_retry_ready,
    merge_retry_events,
    rebuild_retry_pool,
    retry_context_fingerprint,
    select_retry_cases,
)


def blocker(code="semantic.date.partial_not_supported"):
    return {
        "code": code,
        "class": "semantic_schema",
        "retryable": True,
        "reason": "Capability was unavailable.",
        "attempted_resolution": "Preserved the missing representation.",
        "requires": ["capability:v2"],
    }


def case(case_id="case-1", input_text="Published 1996.", family_id="family-1"):
    return {
        "schema_version": "2.0.0",
        "case_id": case_id,
        "language": "en",
        "locale": "en-US",
        "input": input_text,
        "family_id": family_id,
        "source_observations": [
            {"benchmark": "fixture", "source_version": "v1", "source_id": case_id}
        ],
    }


class RereviewPipelineTests(unittest.TestCase):
    def test_duplicate_exclusions_rebuild_to_one_case_with_two_events(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            for batch_id in ("batch-0014", "batch-0015"):
                root = work / "batches" / batch_id
                write_json(
                    root / "batch.json",
                    {"batch_id": batch_id, "batch_kind": "new_data"},
                )
                item = case()
                write_jsonl(root / "cases" / "cases.jsonl", [item])
                write_jsonl(
                    root / "adjudication" / "decisions.jsonl",
                    [
                        {
                            "case_id": "case-1",
                            "adjudicator_id": "judge",
                            "decision": "exclude",
                            "blocker": blocker(),
                        }
                    ],
                )
            summary = rebuild_retry_pool(work, work / "corpus")
            rows = json.loads(
                (work / "state" / "review-exclusions.jsonl").read_text().splitlines()[0]
            )
            self.assertEqual(summary["total_unique"], 1)
            self.assertEqual(summary["duplicate_failure_events"], 1)
            self.assertEqual(len(rows["events"]), 2)
            self.assertEqual(rows["origin_batches"], ["batch-0014", "batch-0015"])

    def test_legacy_exclusion_requires_triage_and_terminal_is_not_selected(self):
        event = {
            "case": case(),
            "case_id": "case-1",
            "batch_id": "batch-1",
            "decision": "exclude",
            "blocker": {
                "code": "legacy.unclassified",
                "class": "other",
                "retryable": False,
                "reason": "triage needed",
                "attempted_resolution": "none",
                "requires": [],
            },
        }
        rows = merge_retry_events([], [event])
        self.assertEqual(rows[0]["state"], "needs_triage")
        self.assertEqual(select_retry_cases(rows, limit=100), [])

    def test_changed_context_makes_blocked_case_ready_and_same_context_is_skipped(self):
        row = merge_retry_events(
            [],
            [
                {
                    "case": case(),
                    "case_id": "case-1",
                    "batch_id": "batch-1",
                    "decision": "exclude",
                    "blocker": blocker(),
                }
            ],
        )[0]
        context = {"resolution_id": "partial-date-v1", "schema_version": "2.1.0"}
        ready = mark_retry_ready(row, context)
        self.assertEqual(len(select_retry_cases([ready], limit=100)), 1)
        same = dict(ready)
        same["latest_retry_context_hash"] = same["retry_context_hash"]
        self.assertEqual(select_retry_cases([same], limit=100), [])
        self.assertNotEqual(
            retry_context_fingerprint(context),
            retry_context_fingerprint({"resolution_id": "partial-date-v2"}),
        )

    def test_rereview_batch_preserves_identity_and_merges_sources(self):
        first = case()
        second = dict(first)
        second["source_observations"] = [
            {"benchmark": "other", "source_version": "v2", "source_id": "other-1"}
        ]
        row = {
            **first,
            "state": "ready",
            "retry_attempts": 0,
            "blocker": blocker(),
            "origin_batches": ["batch-1", "batch-2"],
            "events": [
                {"batch_id": "batch-1", "case": first, "blocker": blocker()},
                {"batch_id": "batch-2", "case": second, "blocker": blocker()},
            ],
            "retry_context": {"resolution_id": "partial-date-v1"},
            "retry_context_hash": "sha256:new",
            "latest_retry_context_hash": "sha256:old",
        }
        with tempfile.TemporaryDirectory() as directory:
            metadata = build_rereview_batch(
                [row],
                work_root=directory,
                batch_id="rereview-0001",
                corpus_path=Path(directory) / "corpus",
            )
            root = Path(directory) / "batches" / "rereview-0001"
            payload = [
                json.loads(line)
                for line in (root / "cases" / "cases.jsonl").read_text().splitlines()
            ]
            blind = [
                json.loads(line)
                for line in (root / "reviews" / "a" / "blind.jsonl")
                .read_text()
                .splitlines()
            ]
            self.assertEqual(metadata["batch_kind"], "rereview")
            self.assertEqual(payload[0]["case_id"], "case-1")
            self.assertEqual(len(payload[0]["source_observations"]), 2)
            self.assertNotIn("review_guidance", blind[0])
            self.assertNotIn("events", blind[0])
            self.assertNotIn("source_observations", blind[0])


if __name__ == "__main__":
    unittest.main()
