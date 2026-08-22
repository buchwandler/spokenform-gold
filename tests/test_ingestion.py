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

    def test_source_order_is_canonical_and_reruns_are_stable(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            cache = self._cache(root)
            work = root / "work"
            first = run_upstream_ingestion(
                cache,
                work,
                sources=("proteno", "async_tn", "polynorm"),
                languages=("pt", "en", "es"),
                batch_limit=3,
            )
            first_bytes = {
                path.relative_to(work): path.read_bytes()
                for path in work.rglob("*")
                if path.is_file()
            }
            second = run_upstream_ingestion(
                cache,
                work,
                sources=("polynorm", "async_tn", "proteno"),
                languages=("es", "en", "pt"),
                batch_limit=3,
            )
            second_bytes = {
                path.relative_to(work): path.read_bytes()
                for path in work.rglob("*")
                if path.is_file()
            }
            self.assertEqual(first["sources"], ["async_tn", "polynorm", "proteno"])
            self.assertEqual(first["sources"], second["sources"])
            self.assertEqual(first["languages"], ["en", "es", "pt"])
            records = read_records([work / "candidates" / "all.jsonl"])
            self.assertTrue(records)
            self.assertLessEqual(
                {record["language"] for record in records}, {"en", "es", "pt"}
            )
            exclusions = read_json(work / "reports" / "exclusions.json")
            self.assertIn("language_not_selected", exclusions["reasons"])
            self.assertTrue(all(item["row_accounting_ok"] for item in first["shards"]))
            self.assertEqual(first_bytes, second_bytes)
            self.assertEqual(first["records"], second["records"])
            self.assertEqual(first["exclusions"], second["exclusions"])


    def test_named_review_batch_is_deterministic_and_does_not_overwrite_default(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            cache = self._cache(root)
            work = root / "work"
            first = run_upstream_ingestion(cache, work, batch_name="batch-0002", batch_limit=3)
            self.assertEqual(first["batch_name"], "batch-0002")
            named = work / "review_batches" / "batch-0002.jsonl"
            self.assertTrue(named.exists())
            default = run_upstream_ingestion(cache, work, batch_limit=3)
            self.assertEqual(default["batch_name"], "batch-0001")
            self.assertTrue((work / "review_batches" / "batch-0001.jsonl").exists())
            self.assertEqual(named.read_bytes(), (work / "review_batches" / "batch-0002.jsonl").read_bytes())
            with self.assertRaisesRegex(ValueError, "batch_name"):
                run_upstream_ingestion(cache, root / "invalid", batch_name="batch-2")


    def test_missing_required_source_path_fails_before_ingestion(self):
        with tempfile.TemporaryDirectory() as tmpdir, self.assertRaisesRegex(
            ValueError, "missing source checkout"
        ):
            run_upstream_ingestion(Path(tmpdir) / "missing", Path(tmpdir) / "work")


if __name__ == "__main__":
    unittest.main()
