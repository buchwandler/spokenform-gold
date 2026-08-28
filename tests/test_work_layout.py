import tempfile
import unittest
from pathlib import Path

from spokenform_gold.collection import select_cases
from spokenform_gold.corpus import read_corpus, write_corpus_atomic
from spokenform_gold.corrections import apply_correction_to_corpus
from spokenform_gold.io import read_records
from spokenform_gold.migration import (
    classify_work_root,
    migrate_work_root,
    work_migration_plan,
)
from spokenform_gold.review_lineage import backfill_legacy_evidence
from spokenform_gold.work_layout import WorkLayout


class WorkLayoutTests(unittest.TestCase):
    def test_paths_are_stage_owned_and_packet_names_are_deterministic(self):
        layout = WorkLayout(Path("/tmp/work-layout"))
        batch = layout.batch("batch-0001")
        self.assertEqual(
            batch.cases, layout.root / "batches/batch-0001/cases/cases.jsonl"
        )
        self.assertEqual(
            batch.review_blind("A"),
            layout.root / "batches/batch-0001/reviews/a/blind.jsonl",
        )
        self.assertEqual(
            batch.review_packet("B", 3, result=True).name, "0003.result.jsonl"
        )
        self.assertEqual(layout.correction("record", 2).result.name, "result.json")

    def test_migration_dry_run_does_not_write_and_apply_preserves_hash(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            batch = root / "batches" / "batch-0001"
            batch.mkdir(parents=True)
            source = batch / "a.blind.jsonl"
            source.write_text('{"case_id":"one"}\n', encoding="utf-8")
            before = source.read_bytes()
            plan = work_migration_plan(root)
            self.assertEqual(plan[0]["action"], "move")
            self.assertEqual(len(classify_work_root(root)["batches"]), 1)
            migrate_work_root(root)
            self.assertTrue(source.exists())
            migrate_work_root(root, apply=True)
            target = batch / "reviews/a/blind.jsonl"
            self.assertEqual(target.read_bytes(), before)
            self.assertFalse(source.exists())

    def test_migration_refuses_distinct_target(self):
        with tempfile.TemporaryDirectory() as temporary:
            batch = Path(temporary) / "batches" / "batch-0001"
            (batch / "reviews/a").mkdir(parents=True)
            (batch / "a.blind.jsonl").write_text("old\n", encoding="utf-8")
            (batch / "reviews/a/blind.jsonl").write_text("new\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "overwrite distinct"):
                migrate_work_root(temporary, apply=True)

    def test_collection_accounting_explains_duplicate_and_empty_inputs(self):
        observations = [
            {
                "id": "one",
                "language": "en",
                "locale": "en-US",
                "input": "Same.",
                "source": {"benchmark": "x", "source_version": "1", "source_id": "1"},
            },
            {
                "id": "duplicate",
                "language": "en",
                "locale": "en-US",
                "input": "Same.",
                "source": {"benchmark": "x", "source_version": "1", "source_id": "1"},
            },
        ]
        result = select_cases(
            observations,
            reviewed=[
                {
                    "id": "gold",
                    "language": "en",
                    "locale": "en-US",
                    "input": "Same.",
                    "source_observations": [
                        {"benchmark": "x", "source_version": "1", "source_id": "1"}
                    ],
                }
            ],
        )
        self.assertEqual(result.cases, [])
        self.assertEqual(result.accounting.input_observations, 2)
        self.assertEqual(result.accounting.duplicate_observations, 1)
        self.assertEqual(result.accounting.available_cases, 0)

    def test_targeted_correction_writes_shard_and_compact_receipt(self):
        original = read_records([Path("data/test/sample.jsonl")])[0]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            corpus = root / "corpus"
            write_corpus_atomic(corpus, read_records([Path("data/test/sample.jsonl")]))
            replacement = dict(original)
            replacement["notes"] = "targeted correction"
            output = root / "correction"
            paths = apply_correction_to_corpus(
                corpus,
                root / "lineage/review-evidence.jsonl",
                original,
                {
                    "record_id": original["id"],
                    "actor": "agent",
                    "reason": "fixture",
                    "new_record": replacement,
                },
                backfill_legacy_evidence([original]),
                output,
            )
            self.assertFalse((output / "records.jsonl").exists())
            self.assertTrue(
                paths["receipt" if "receipt" in paths else "result"].exists()
            )
            corrected = next(
                row for row in read_corpus(corpus) if row["id"] == original["id"]
            )
            self.assertEqual(corrected["notes"], "targeted correction")


if __name__ == "__main__":
    unittest.main()
