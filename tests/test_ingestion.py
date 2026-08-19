import shutil
import tempfile
import unittest
from pathlib import Path

from spokenform_gold.ingestion import run_upstream_ingestion
from spokenform_gold.io import read_json, read_records

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "importers"


class IngestionTests(unittest.TestCase):
    def _cache(self, root: Path) -> Path:
        cache = root / "sources"
        (cache / "async_tn" / "data").mkdir(parents=True)
        shutil.copy2(FIXTURES / "async_english.json", cache / "async_tn" / "data" / "sentences.json")
        shutil.copy2(FIXTURES / "async_multilingual.json", cache / "async_tn" / "data" / "multilingual-sentences.json")
        shutil.copytree(FIXTURES / "polynorm_official", cache / "polynorm" / "polynorm_bench")
        for language in ("English", "Spanish"):
            shutil.copytree(
                FIXTURES / "proteno_official" / language,
                cache / "proteno" / "data" / language,
            )
        return cache

    def test_fixture_cache_writes_all_shards_and_reports(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            cache = self._cache(root)
            summary = run_upstream_ingestion(cache, root / "work", batch_limit=3)
            self.assertEqual(summary["records"], 17)
            self.assertTrue(all(item["row_accounting_ok"] for item in summary["shards"]))
            work = root / "work"
            for path in (
                work / "candidates" / "async_en.jsonl",
                work / "candidates" / "async_multilingual.jsonl",
                work / "candidates" / "polynorm.jsonl",
                work / "candidates" / "proteno_en.jsonl",
                work / "candidates" / "proteno_es.jsonl",
                work / "reports" / "ranked_candidates.jsonl",
                work / "reports" / "upstream_pool_summary.json",
                work / "review_batches" / "batch-0001.jsonl",
            ):
                self.assertTrue(path.exists(), path)
            records = read_records([work / "candidates" / "all.jsonl"])
            self.assertTrue(records)
            self.assertTrue(all(record["status"] == "quarantine" for record in records))
            self.assertEqual(read_json(work / "reports" / "ingestion-summary.json"), summary)

    def test_missing_required_source_path_fails_before_ingestion(self):
        with tempfile.TemporaryDirectory() as tmpdir, self.assertRaisesRegex(
            ValueError, "missing source checkout"
        ):
            run_upstream_ingestion(Path(tmpdir) / "missing", Path(tmpdir) / "work")


if __name__ == "__main__":
    unittest.main()
