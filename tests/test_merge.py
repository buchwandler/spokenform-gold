import tempfile
import unittest
from pathlib import Path

from spokenform_gold.io import write_jsonl
from spokenform_gold.merge import merge_candidate_files, merge_candidates


class MergeTests(unittest.TestCase):
    def _record(self, record_id, benchmark, language, locale, source_id):
        return {
            "id": record_id,
            "language": language,
            "locale": locale,
            "source": {"benchmark": benchmark, "source_id": source_id},
        }

    def test_stable_source_order_and_unicode(self):
        records = [
            self._record("b", "z_source", "en", "en-US", "2"),
            self._record("a", "a_source", "de", "de-DE", "1"),
            self._record("c", "a_source", "en", "en-US", "1"),
        ]
        ordered = merge_candidates(records)
        self.assertEqual([item["id"] for item in ordered], ["a", "c", "b"])

    def test_duplicate_ids_are_rejected(self):
        record = self._record("same", "source", "en", "en-US", "1")
        with self.assertRaisesRegex(ValueError, "duplicate"):
            merge_candidates([record, dict(record)])

    def test_file_merge_accepts_glob_and_preserves_source_identity(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_jsonl(root / "one.jsonl", [self._record("one", "b", "en", "en-US", "1")])
            write_jsonl(root / "two.jsonl", [self._record("two", "a", "en", "en-US", "1")])
            out = root / "merged.jsonl"
            merged = merge_candidate_files([str(root / "*.jsonl")], out)
            self.assertEqual([item["id"] for item in merged], ["two", "one"])
            self.assertEqual(merged[0]["source"]["benchmark"], "a")

    def test_same_input_from_distinct_sources_is_retained(self):
        first = self._record("async-1", "async_tn", "en", "en-US", "row-1")
        second = self._record("proteno-1", "proteno_en", "en", "en-US", "proteno:en:1")
        first["input"] = second["input"] = "Unicode café 3/4"
        merged = merge_candidates([second, first])
        self.assertEqual([record["id"] for record in merged], ["async-1", "proteno-1"])
        self.assertEqual(
            [record["source"]["source_id"] for record in merged],
            ["row-1", "proteno:en:1"],
        )



if __name__ == "__main__":
    unittest.main()
