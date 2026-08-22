import tempfile
import unittest
from pathlib import Path

from spokenform_gold.benchmark import load_release_records
from spokenform_gold.io import (
    read_json,
    read_records,
    sha256_file,
    write_json,
    write_jsonl,
)
from spokenform_gold.source_resolver import (
    build_external_overlay,
    hydrate_external_overlay,
    resolve_release_record,
)
from spokenform_gold.validation import validate_records

ROOT = Path(__file__).resolve().parents[1]


class SourceResolverTests(unittest.TestCase):
    def test_external_overlay_round_trip_preserves_annotation(self):
        record = read_records([ROOT / "data/test/sample.jsonl"])[0]
        overlay = build_external_overlay(record, source_artifact="bundle://sample-1")
        self.assertEqual(overlay["materialization"], "external_ref")
        self.assertIsNone(overlay["input"])
        hydrated = hydrate_external_overlay(overlay, input_text=record["input"])
        self.assertEqual(hydrated["input"], record["input"])
        self.assertEqual(hydrated["expected_output"], record["expected_output"])
        self.assertEqual(hydrated["units"], record["units"])

    def test_external_overlay_validates_and_requires_source_artifact(self):
        record = read_records([ROOT / "data/test/sample.jsonl"])[0]
        overlay = build_external_overlay(record, source_artifact="bundle://sample-1")
        self.assertEqual(validate_records([overlay]), [])
        broken = dict(overlay)
        broken["source"] = dict(overlay["source"])
        broken["source"].pop("source_artifact")
        self.assertTrue(
            any("source_artifact" in error for error in validate_records([broken]))
        )

    def test_hydration_validates_surface_and_semantics(self):
        record = read_records([ROOT / "data/test/sample.jsonl"])[0]
        overlay = build_external_overlay(record, source_artifact="bundle://sample-1")
        bad_input = "The time is 28:00."
        with self.assertRaisesRegex(
            ValueError, "hydrated external_ref record is invalid"
        ):
            resolve_release_record(overlay, source_loader=lambda _: bad_input)

    def test_resolve_release_record_requires_loader_for_external_ref(self):
        record = read_records([ROOT / "data/test/sample.jsonl"])[0]
        overlay = build_external_overlay(record, source_artifact="bundle://sample-1")
        with self.assertRaises(ValueError):
            resolve_release_record(overlay, source_loader=None)

    def test_load_release_records_hydrates_external_ref_records(self):
        record = read_records([ROOT / "data/test/sample.jsonl"])[0]
        overlay = build_external_overlay(record, source_artifact="bundle://sample-1")
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "release"
            data_dir = root / "data" / "test"
            data_dir.mkdir(parents=True, exist_ok=True)
            write_jsonl(data_dir / "sample.jsonl", [overlay])
            sources_dir = root / "sources"
            sources_dir.mkdir(parents=True, exist_ok=True)
            source_manifest = read_json(ROOT / "sources/manifest.json")
            filtered_manifest = {
                **source_manifest,
                "sources": [
                    entry
                    for entry in source_manifest["sources"]
                    if entry["name"] == record["source"]["benchmark"]
                ],
            }
            write_json(sources_dir / "manifest.json", filtered_manifest)
            manifest = {
                "benchmark_version": "0.0.0-test",
                "maturity": "experimental",
                "file_hashes": {
                    "data/test/sample.jsonl": sha256_file(data_dir / "sample.jsonl"),
                    "sources/manifest.json": sha256_file(sources_dir / "manifest.json"),
                },
            }
            write_json(root / "manifest.json", manifest)

            _, records = load_release_records(
                root,
                split="test",
                source_loader=lambda release_record: record["input"],
            )
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["input"], record["input"])
            self.assertEqual(records[0]["units"], record["units"])


if __name__ == "__main__":
    unittest.main()
