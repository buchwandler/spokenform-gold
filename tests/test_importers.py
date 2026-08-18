import json
import pickle
import tempfile
import unittest
from pathlib import Path

from spokenform_gold.importers import import_async, import_polynorm, import_proteno


ROOT = Path(__file__).resolve().parents[1]


class ImporterTests(unittest.TestCase):
    def test_async_import_preserves_spans_and_resolves_unique_surface(self):
        result = import_async(
            ROOT / "tests/fixtures/importers/async_english.json", suite="english"
        )
        self.assertEqual(result.source_rows, 2)
        self.assertEqual(len(result.records), 2)
        self.assertEqual(result.records[0]["units"][0]["start"], 4)
        self.assertEqual(result.records[0]["units"][1]["start"], 11)
        self.assertEqual(
            result.records[1]["units"][0]["features"]["span_origin"], "resolved-exact"
        )

    def test_async_import_handles_all_six_multilingual_rows(self):
        result = import_async(
            ROOT / "tests/fixtures/importers/async_multilingual.json",
            suite="multilingual",
        )
        self.assertEqual(result.source_rows, 6)
        self.assertEqual(
            {record["language"] for record in result.records},
            {"de", "en", "es", "fr", "it", "pt"},
        )
        self.assertEqual(
            len(result.records) + len(result.exclusions), result.source_rows
        )

    def test_async_import_reports_bad_rows(self):
        payload = [
            {
                "row_id": "bad-lang",
                "language": "sv",
                "original_text": "Hej 09:30",
                "normalized_text": "Hej",
                "units": [],
            },
            {
                "row_id": "bad-category",
                "language": "en",
                "original_text": "X 123",
                "normalized_text": "X",
                "units": [{"text": "123", "norm_category": "UNKNOWN"}],
            },
            {
                "row_id": "bad-text",
                "language": "en",
                "original_text": 9,
                "normalized_text": "nine",
                "units": [],
            },
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "payload.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            result = import_async(path, suite="english")
        reasons = {item["reason"] for item in result.exclusions}
        self.assertIn("unsupported_language", reasons)
        self.assertIn("unmappable_or_unresolved_unit", reasons)
        self.assertIn("malformed_row", reasons)

    def test_polynorm_import_supports_raw_bundle_and_projection(self):
        raw = import_polynorm(ROOT / "tests/fixtures/importers/polynorm_raw.json")
        projection = import_polynorm(
            ROOT / "tests/fixtures/importers/polynorm_sample.jsonl", format="projection"
        )
        self.assertEqual(raw.source_rows, 2)
        self.assertEqual(
            projection.records[0]["source"]["upstream_expected"],
            "Leave at nine ten PM.",
        )
        self.assertEqual(raw.records[1]["units"][0]["category"], "fraction")
        self.assertEqual(raw.records[1]["source"]["import_format"], "raw")

    def test_proteno_import_preserves_projection_notes(self):
        result = import_proteno(ROOT / "tests/fixtures/importers/proteno_sample.json")
        self.assertEqual(result.source_rows, 3)
        self.assertEqual(
            result.records[0]["source"]["projection_notes"], "ISO date projection"
        )
        self.assertTrue(result.records[2]["units"][0]["features"]["identity_example"])

    def test_proteno_rejects_unsafe_pickle(self):
        class Evil:
            def __reduce__(self):
                return (print, ("boom",))

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "unsafe.pkl"
            path.write_bytes(pickle.dumps(Evil()))
            with self.assertRaises(Exception):
                import_proteno(path)


if __name__ == "__main__":
    unittest.main()
