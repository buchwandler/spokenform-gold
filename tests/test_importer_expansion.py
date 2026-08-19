import json
import tempfile
import unittest
from pathlib import Path

from spokenform_gold.importers import import_async
from spokenform_gold.importers.async_tn import detect_async_source_schema
from spokenform_gold.taxonomy import load_categories, load_mapping

ROOT = Path(__file__).resolve().parents[1]


class ImporterExpansionTests(unittest.TestCase):
    def test_current_async_english_schema_and_report(self):
        payload = [
            {
                "row_index": 1,
                "original_text": "The event is on 05/20/2023.",
                "normalized_text": "The event is on May twentieth twenty twenty three.",
                "categories": ["date"],
                "units": [{"text": "05/20/2023", "norm_category": "date"}],
            },
            {
                "row_index": 2,
                "original_text": "No normalization here.",
                "normalized_text": "No normalization here.",
                "categories": [],
                "units": [],
            },
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "sentences.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            result = import_async(path)
        self.assertEqual(
            detect_async_source_schema(payload, "english"), "async_tn_english_v2"
        )
        self.assertEqual(
            result.diagnostics["source_bundle_schema"], "async_tn_english_v2"
        )
        self.assertTrue(result.diagnostics["row_accounting_ok"])
        self.assertEqual(result.diagnostics["records_without_units"], 1)
        self.assertEqual(
            result.records[0]["units"][0]["features"]["surface_pattern"], "slash_date"
        )
        self.assertTrue(
            all(record["status"] == "quarantine" for record in result.records)
        )
        self.assertTrue(
            all(record["expected_output"] is None for record in result.records)
        )

    def test_current_async_multilingual_schema(self):
        payload = [
            {
                "sentence_id": "curated-1",
                "languages": {
                    "en": {
                        "language_code": "en",
                        "original_text": "Figure 2: CD 100203.",
                        "normalized_text": "Figure two: C D one zero zero two zero three.",
                        "categories": ["cardinal", "mixed_doc"],
                        "units": [
                            {"text": "2", "norm_category": "cardinal"},
                            {"text": "CD 100203", "norm_category": "mixed_doc"},
                        ],
                    }
                },
            }
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "multilingual-sentences.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            result = import_async(path, suite="multilingual")
        self.assertEqual(
            detect_async_source_schema(payload, "multilingual"),
            "async_tn_multilingual_v2",
        )
        self.assertEqual(result.source_rows, 1)
        self.assertEqual(len(result.records[0]["units"]), 2)
        self.assertEqual(result.records[0]["language"], "en")

    def test_all_current_async_categories_are_explicitly_mapped(self):
        categories = load_categories()["categories"]
        mapping = load_mapping("async_tn")["mappings"]
        self.assertTrue(set(categories) <= set(mapping))
        payload = []
        for index, category in enumerate(categories, 1):
            payload.append(
                {
                    "row_index": index,
                    "original_text": f"X{index}",
                    "normalized_text": f"X {index}",
                    "categories": [category],
                    "units": [
                        {
                            "text": f"X{index}",
                            "norm_category": category,
                            "start": 0,
                            "end": len(f"X{index}"),
                        }
                    ],
                }
            )
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "all.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            result = import_async(path)
        self.assertEqual(result.source_rows, len(categories))
        self.assertEqual(len(result.records), len(categories))
        self.assertFalse(result.exclusions)

    def test_legacy_aliases_and_unknown_categories(self):
        payload = [
            {
                "row_id": "id",
                "original_text": "AB12",
                "normalized_text": "A B twelve",
                "units": [
                    {"text": "AB12", "norm_category": "ID", "start": 0, "end": 4}
                ],
            },
            {
                "row_id": "ip",
                "original_text": "192.168.0.1",
                "normalized_text": "...",
                "units": [
                    {
                        "text": "192.168.0.1",
                        "norm_category": "IP",
                        "start": 0,
                        "end": 11,
                    }
                ],
            },
            {
                "row_id": "bad",
                "original_text": "X",
                "normalized_text": "X",
                "units": [
                    {"text": "X", "norm_category": "UNKNOWN", "start": 0, "end": 1}
                ],
            },
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "legacy.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            result = import_async(path)
        self.assertEqual(len(result.records), 2)
        self.assertEqual(result.records[0]["units"][0]["category"], "identifier")
        self.assertEqual(result.records[1]["units"][0]["category"], "ip_address")
        self.assertEqual(
            result.exclusions[0]["reason"], "unmappable_or_unresolved_unit"
        )

    def test_checked_in_fixture_candidates_are_expanded_and_quarantined(self):
        async_records = (ROOT / "data/candidates/async_tn.jsonl").read_text(encoding="utf-8").splitlines()
        polynorm_records = (ROOT / "data/candidates/polynorm.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(async_records), 8)
        self.assertEqual(len(polynorm_records), 6)
        from spokenform_gold.io import read_records
        from spokenform_gold.validation import validate_records
        records = read_records(
            [ROOT / "data/candidates/async_tn.jsonl", ROOT / "data/candidates/polynorm.jsonl"]
        )
        self.assertEqual(validate_records(records), [])
        self.assertTrue(all(record["status"] == "quarantine" for record in records))
        self.assertEqual(
            sum(record["source"]["benchmark"] == "async_tn" for record in records),
            8,
        )
        self.assertEqual(
            sum(record["source"]["benchmark"] == "polynorm" for record in records),
            6,
        )



if __name__ == "__main__":
    unittest.main()
