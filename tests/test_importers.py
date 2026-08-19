import json
import pickle
import tempfile
import unittest
from pathlib import Path

from spokenform_gold.importers import import_async, import_polynorm, import_proteno
from spokenform_gold.importers.async_tn import detect_async_source_schema
from spokenform_gold.io import read_json

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

    def test_async_source_fixtures_match_supported_bundle_schema(self):
        english_payload = read_json(
            ROOT / "tests/fixtures/importers/async_english.json"
        )
        multilingual_payload = read_json(
            ROOT / "tests/fixtures/importers/async_multilingual.json"
        )
        self.assertEqual(
            detect_async_source_schema(english_payload, "english"),
            "async_tn_english_v1",
        )
        self.assertEqual(
            detect_async_source_schema(multilingual_payload, "multilingual"),
            "async_tn_multilingual_v1",
        )

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

    def test_polynorm_import_supports_official_file_and_directory(self):
        official_file = (
            ROOT
            / "tests/fixtures/importers/polynorm_official/en-US/en-US_groundtruth.jsonl"
        )
        official_dir = ROOT / "tests/fixtures/importers/polynorm_official"
        single = import_polynorm(official_file, format="official")
        combined = import_polynorm(official_dir, format="official")

        self.assertEqual(single.source_rows, 3)
        self.assertEqual(len(single.records), 2)
        self.assertEqual(len(single.exclusions), 1)
        self.assertEqual(single.records[0]["source"]["source_id"], "en-US:1")
        self.assertEqual(single.records[0]["units"][0]["surface"], "05/20/2023")
        self.assertEqual(single.records[1]["units"], [])
        self.assertIn("unsupported", single.records[1]["notes"])
        self.assertEqual(single.exclusions[0]["reason"], "unsupported_category")

        self.assertEqual(combined.source_rows, 5)
        self.assertEqual(
            {record["locale"] for record in combined.records},
            {"de-DE", "en-US"},
        )
        self.assertEqual(
            len(combined.records) + len(combined.exclusions), combined.source_rows
        )
        version_record = next(
            record
            for record in combined.records
            if record["source"]["source_category"] == "Version Number"
        )
        self.assertEqual(
            version_record["units"][0]["category"],
            "version",
        )

    def test_proteno_import_preserves_projection_notes(self):
        result = import_proteno(ROOT / "tests/fixtures/importers/proteno_sample.json")
        self.assertEqual(result.source_rows, 3)
        self.assertEqual(
            result.records[0]["source"]["projection_notes"], "ISO date projection"
        )
        self.assertTrue(result.records[2]["units"][0]["features"]["identity_example"])

    def test_proteno_import_supports_official_pairs(self):
        english = import_proteno(
            ROOT / "tests/fixtures/importers/proteno_official/English",
            format="official",
        )
        spanish = import_proteno(
            ROOT / "tests/fixtures/importers/proteno_official/Spanish",
            format="official",
        )
        self.assertEqual(english.source_rows, 3)
        self.assertEqual(english.records[0]["source"]["benchmark"], "proteno_en")
        self.assertEqual(english.records[0]["source"]["source_split"], "upstream_train")
        self.assertEqual(len(english.records[2]["units"]), 2)
        self.assertEqual(
            {unit["category"] for unit in english.records[2]["units"]},
            {"phone", "time"},
        )
        self.assertEqual(spanish.records[0]["units"][0]["category"], "currency")
        self.assertEqual(
            spanish.records[0]["units"][0]["features"]["upstream_spoken"],
            "doce euros con cincuenta céntimos",
        )
        self.assertEqual(
            spanish.records[1]["units"][0]["category"],
            "url_or_email",
        )

    def test_proteno_official_accepts_tokenized_pairs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "English"
            root.mkdir(parents=True, exist_ok=True)
            with (root / "unnorm_list.pkl").open("wb") as handle:
                pickle.dump([["2006", "IUCN", "."]], handle)
            with (root / "norm_list.pkl").open("wb") as handle:
                pickle.dump([["two thousand six", "i u c n", ""]], handle)
            result = import_proteno(root, format="official")
        self.assertEqual(result.source_rows, 1)
        self.assertEqual(len(result.records), 1)
        self.assertEqual(result.records[0]["input"], "2006 IUCN .")
        self.assertEqual(
            result.records[0]["source"]["upstream_expected"],
            "two thousand six i u c n",
        )


    def test_proteno_official_rejects_length_mismatch(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "English"
            root.mkdir(parents=True, exist_ok=True)
            with (root / "unnorm_list.pkl").open("wb") as handle:
                pickle.dump(["One row"], handle)
            with (root / "norm_list.pkl").open("wb") as handle:
                pickle.dump(["One row", "Two rows"], handle)
            with self.assertRaises(ValueError):
                import_proteno(root, format="official")

    def test_proteno_rejects_unsafe_pickle(self):
        class Evil:
            def __reduce__(self):
                return (print, ("boom",))

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "unsafe.pkl"
            path.write_bytes(pickle.dumps(Evil()))
            with self.assertRaises(pickle.UnpicklingError):
                import_proteno(path)

    def test_proteno_tamil_remains_separate_source_identity(self):
        tamil = import_proteno(
            ROOT / "tests/fixtures/importers/proteno_official/Tamil",
            format="official",
        )
        self.assertTrue(tamil.records)
        self.assertEqual({record["language"] for record in tamil.records}, {"ta"})
        self.assertEqual(
            {record["source"]["benchmark"] for record in tamil.records},
            {"proteno_ta"},
        )



if __name__ == "__main__":
    unittest.main()
