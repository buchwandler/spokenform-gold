import tempfile
import unittest
from pathlib import Path

from spokenform_gold.census import build_upstream_census, write_census_artifacts
from spokenform_gold.io import read_jsonl


class CensusTests(unittest.TestCase):
    def test_row_accounting_and_duplicate_lineage(self):
        candidates = [
            {
                "id": "a",
                "language": "en",
                "locale": "en-US",
                "input": "The date is 03/04/2025.",
                "source": {
                    "benchmark": "async_tn",
                    "source_id": "1",
                    "source_version": "rev",
                    "source_hash": "sha256:a",
                    "upstream_expected": "March fourth",
                },
            },
            {
                "id": "p",
                "language": "en",
                "locale": "en-US",
                "input": "The date is 03/04/2025.",
                "source": {
                    "benchmark": "polynorm",
                    "source_id": "2",
                    "source_version": "rev",
                    "source_hash": "sha256:b",
                    "upstream_expected": "April third",
                },
            },
        ]
        exclusions = [{"source": "proteno", "source_id": "3", "reason": "unsupported"}]
        census = build_upstream_census(candidates, exclusions, [{"source_rows": 3}])
        self.assertTrue(census["summary"]["row_accounting_ok"])
        self.assertEqual(census["summary"]["rows_observed"], 3)
        self.assertEqual(len(census["sentence_clusters"]), 1)
        self.assertEqual(len(census["sentence_clusters"][0]["source_refs"]), 2)

    def test_artifacts_are_written(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            census = build_upstream_census([], [], [])
            paths = write_census_artifacts(Path(tmpdir), census)
            self.assertTrue(Path(paths["rows"]).exists())
            self.assertEqual(read_jsonl(paths["rows"]), [])


if __name__ == "__main__":
    unittest.main()
