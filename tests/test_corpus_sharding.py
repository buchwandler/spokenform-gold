from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from spokenform_gold.corpus import (
    read_corpus,
    shard_corpus,
    shard_records_by_language,
    validate_corpus_layout,
    write_corpus_atomic,
)
from spokenform_gold.io import read_records, write_jsonl

ROOT = Path(__file__).resolve().parents[1]


class CorpusShardingTests(unittest.TestCase):
    def test_grouping_and_ordering(self):
        records = [
            {"id": "sfg-2", "language": "en"},
            {"id": "sfg-1", "language": "en"},
            {"id": "sfg-3", "language": "de"},
        ]
        shards = shard_records_by_language(records)
        self.assertEqual(list(shards), ["de", "en"])
        self.assertEqual([row["id"] for row in shards["en"]], ["sfg-1", "sfg-2"])

    def test_atomic_write_is_deterministic(self):
        records = [
            {"id": "sfg-2", "language": "en"},
            {"id": "sfg-1", "language": "de"},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "first"
            second = root / "second"
            write_corpus_atomic(first, records)
            write_corpus_atomic(second, list(reversed(records)))
            self.assertEqual(
                sorted(path.name for path in first.iterdir()),
                ["de.jsonl", "en.jsonl"],
            )
            self.assertEqual(
                [path.read_bytes() for path in sorted(first.iterdir())],
                [path.read_bytes() for path in sorted(second.iterdir())],
            )
            self.assertEqual(read_corpus(first), read_records([first]))

    def test_language_file_mismatch_fails_layout_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "corpus"
            root.mkdir()
            write_jsonl(root / "de.jsonl", [{"id": "sfg-1", "language": "en"}])
            errors = validate_corpus_layout(root)
            self.assertTrue(any("does not match shard" in error for error in errors))
            with self.assertRaisesRegex(ValueError, "invalid corpus layout"):
                read_corpus(root)

    def test_duplicate_id_across_shards_fails_globally(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "corpus"
            root.mkdir()
            write_jsonl(root / "de.jsonl", [{"id": "sfg-1", "language": "de"}])
            write_jsonl(root / "en.jsonl", [{"id": "sfg-1", "language": "en"}])
            errors = validate_corpus_layout(root)
            self.assertTrue(any("duplicate id" in error for error in errors))

    def test_migration_preserves_legacy_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "corpus.jsonl"
            shutil.copy2(ROOT / "data/dev/sample.jsonl", source)
            destination = root / "corpus"
            expected = read_records([source])
            self.assertEqual(shard_corpus(source, destination), len(expected))
            self.assertFalse(source.exists())
            actual = read_corpus(destination)
            clean = lambda row: {
                key: value for key, value in row.items() if not key.startswith("_")
            }
            self.assertEqual(
                sorted(json.dumps(clean(row), sort_keys=True) for row in expected),
                sorted(json.dumps(clean(row), sort_keys=True) for row in actual),
            )


if __name__ == "__main__":
    unittest.main()
