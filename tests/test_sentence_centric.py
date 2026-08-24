from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from spokenform_gold.collection import build_batch, cluster_observations
from spokenform_gold.corpus import migrate_record, sentence_key
from spokenform_gold.io import read_records, write_jsonl
from spokenform_gold.workflow import check_reviews, integrate_batch

ROOT = Path(__file__).resolve().parents[1]


class SentenceCentricTests(unittest.TestCase):
    def test_migration_removes_split_and_pluralizes_source(self):
        old = read_records([ROOT / "data/test/sample.jsonl"])[0]
        migrated = migrate_record(old)
        self.assertNotIn("split", migrated)
        self.assertNotIn("expected_output", migrated)
        self.assertEqual(migrated["oracle"]["canonical_output"], old["expected_output"])
        self.assertEqual(migrated["source_observations"][0], old["source"])

    def test_cluster_groups_sources_but_preserves_locale(self):
        rows = [
            {
                "language": "en",
                "locale": "en-US",
                "input": "Value 3/4.",
                "source": {"benchmark": "a", "source_id": "1", "source_version": "r"},
            },
            {
                "language": "en",
                "locale": "en-US",
                "input": "Value 3/4.",
                "source": {"benchmark": "b", "source_id": "2", "source_version": "r"},
            },
            {
                "language": "en",
                "locale": "en-GB",
                "input": "Value 3/4.",
                "source": {"benchmark": "a", "source_id": "3", "source_version": "r"},
            },
        ]
        cases = cluster_observations(rows)
        self.assertEqual(len(cases), 2)
        us = next(case for case in cases if case["locale"] == "en-US")
        self.assertEqual(len(us["source_observations"]), 2)
        self.assertEqual(
            sentence_key("en", "en-US", "Value  3/4."),
            sentence_key("en", "en-US", "Value 3/4."),
        )

    def test_review_check_requires_independent_reviewer_ids(self):
        case = {"case_id": "case-1", "language": "en", "locale": "en-US", "input": "x"}

        def row(slot, reviewer):
            return {
                "case_id": "case-1",
                "reviewer_slot": slot,
                "reviewer_id": reviewer,
                "annotation": {},
                "review": {"status": "complete"},
            }

        self.assertTrue(
            check_reviews([case], [row("A", "a")], [row("B", "b")])["ready"]
        )
        self.assertFalse(
            check_reviews([case], [row("A", "same")], [row("B", "same")])["ready"]
        )

    def test_integration_is_atomic_on_invalid_adjudication(self):
        original = read_records([ROOT / "data/corpus.jsonl"])[0]
        case = {
            "case_id": "case-1",
            "language": original["language"],
            "locale": original["locale"],
            "input": original["input"],
            "source_observations": original["source_observations"],
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            build_batch([case], root, batch_id="batch-1")
            for slot, reviewer in (("A", "reviewer-a"), ("B", "reviewer-b")):
                write_jsonl(
                    root / f"{slot.lower()}.complete.jsonl",
                    [
                        {
                            "case_id": "case-1",
                            "reviewer_slot": slot,
                            "reviewer_id": reviewer,
                            "annotation": {},
                            "review": {"status": "complete"},
                        }
                    ],
                )
            write_jsonl(
                root / "adjudicated.jsonl",
                [
                    {
                        "case_id": "case-1",
                        "adjudicator_id": "judge",
                        "decision": "unresolved",
                    }
                ],
            )
            target = root / "corpus.jsonl"
            target.write_text(json.dumps(original) + "\n", encoding="utf-8")
            before = target.read_bytes()
            with self.assertRaises(ValueError):
                integrate_batch(root, target, write=True)
            self.assertEqual(before, target.read_bytes())


if __name__ == "__main__":
    unittest.main()
