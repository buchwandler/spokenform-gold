import unittest
from pathlib import Path

from spokenform_gold.corpus_status import build_corpus_status
from spokenform_gold.io import read_json, read_records

ROOT = Path(__file__).resolve().parents[1]


class CorpusStatusTests(unittest.TestCase):
    def test_status_keeps_canonical_count_distinct_from_release_count(self):
        records = read_records([ROOT / "data/corpus"])
        result = build_corpus_status(
            records,
            source_manifest=read_json(ROOT / "sources/manifest.json"),
            retry_backlog=28,
        )
        self.assertEqual(result["canonical"], 19789)
        self.assertEqual(result["local_benchmark_records"], 19789)
        self.assertEqual(result["review_gaps"], 0)
        self.assertEqual(result["retry_backlog"], 28)


if __name__ == "__main__":
    unittest.main()
