import copy
import unittest
from pathlib import Path

from spokenform_gold.corpus import read_corpus
from spokenform_gold.io import read_records
from spokenform_gold.source_manifest import validate_source_manifest
from spokenform_gold.validation import validate_records

ROOT = Path(__file__).resolve().parents[1]


class ValidationTests(unittest.TestCase):
    def test_samples_are_valid(self):
        records = read_records([ROOT / "data/dev", ROOT / "data/test"])
        self.assertEqual(validate_records(records), [])

    def test_duplicate_id_is_rejected(self):
        records = read_records([ROOT / "data/dev/sample.jsonl"])
        records.append(dict(records[0]))
        self.assertTrue(
            any("duplicate id" in error for error in validate_records(records))
        )

    def test_missing_source_version_is_rejected(self):
        records = read_records([ROOT / "data/dev/sample.jsonl"])
        broken = copy.deepcopy(records[0])
        del broken["source"]["source_version"]
        errors = validate_records([broken])
        self.assertTrue(
            any("source.source_version is required" in error for error in errors)
        )

    def test_invalid_policy_is_rejected(self):
        records = read_records([ROOT / "data/dev/sample.jsonl"])
        broken = copy.deepcopy(next(record for record in records if record["units"]))
        broken["units"][0]["policy"] = "missing-policy"
        errors = validate_records([broken])
        self.assertTrue(any("unknown policy" in error for error in errors))

    def test_invalid_semantic_is_rejected(self):
        records = read_records([ROOT / "data/test/sample.jsonl"])
        broken = copy.deepcopy(
            next(
                record for record in records if record["units"][0]["category"] == "time"
            )
        )
        broken["units"][0]["semantic"] = {"hour": 28, "minute": 0}
        errors = validate_records([broken])
        self.assertTrue(any("time hour out of range" in error for error in errors))

    def test_imported_record_requires_source_hash(self):
        records = read_records(
            [ROOT / "tests/fixtures/candidates/sample_candidates.jsonl"]
        )
        broken = copy.deepcopy(records[0])
        del broken["source"]["source_hash"]
        errors = validate_records([broken])
        self.assertTrue(any("source.source_hash" in error for error in errors))

    def test_source_manifest_hashes_and_release_ready_validate(self):
        manifest = {
            "version": "1.0.0",
            "sources": [
                {
                    "name": "fixture",
                    "revision": "rev-1",
                    "source_url": "https://example.com/repo",
                    "license": "Apache-2.0",
                    "license_id": "Apache-2.0",
                    "license_scope": "source:fixture",
                    "materialization_policy": "embedded_public",
                    "redistribution_status": "allowed",
                    "release_ready": True,
                    "files": [
                        {
                            "path": "README.md",
                            "sha256": "0" * 64,
                        }
                    ],
                }
            ],
        }
        errors = validate_source_manifest(manifest, repo_root=ROOT)
        self.assertTrue(any("sha256 mismatch" in error for error in errors))

    def test_judge_ambiguity_family_must_match_category(self):
        records = read_records([ROOT / "data/judge_gold/sample.jsonl"])
        broken = copy.deepcopy(records[0])
        broken["ambiguity_family"] = "fraction-vs-division"
        errors = validate_records([broken], judge=True)
        self.assertTrue(any("ambiguity_family" in error for error in errors))

    def test_ambiguous_date_units_require_candidate_semantics(self):
        records = read_corpus(ROOT / "data/corpus")
        record = copy.deepcopy(
            next(item for item in records if item["id"] == "sfg-000ec27c2adaddabdea0")
        )
        date_units = [
            unit
            for unit in record["units"]
            if unit.get("category") == "date"
            and unit.get("mapping_status") == "ambiguous"
        ]
        self.assertGreaterEqual(len(date_units), 2)
        for unit in date_units:
            semantic = unit["semantic"]
            if "candidates" in semantic:
                semantic = semantic["candidates"][0]
            unit["canonical"] = None
            unit["semantic"] = copy.deepcopy(semantic)
        errors = validate_records([record])
        self.assertEqual(
            sum("ambiguous date unit requires" in error for error in errors),
            len(date_units),
        )

        for unit in date_units:
            semantic = copy.deepcopy(unit["semantic"])
            alternate = copy.deepcopy(semantic)
            alternate["year"] -= 100
            unit["semantic"] = {"candidates": [semantic, alternate]}
        errors = validate_records([record])
        self.assertFalse(
            any("ambiguous date unit requires" in error for error in errors)
        )


if __name__ == "__main__":
    unittest.main()
