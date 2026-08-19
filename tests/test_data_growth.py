import tempfile
import unittest
from pathlib import Path

from spokenform_gold.coverage import build_coverage, load_targets
from spokenform_gold.io import read_records
from spokenform_gold.release import build_release
from spokenform_gold.source_manifest import load_and_validate_source_manifest
from spokenform_gold.validation import validate_records

ROOT = Path(__file__).resolve().parents[1]


class DataGrowthTests(unittest.TestCase):
    def test_regression_candidates_are_quarantine_only_and_provenance_complete(self):
        candidates = read_records([ROOT / "data/candidates/01_todo_regressions.jsonl"])

        self.assertEqual(len(candidates), 25)
        self.assertEqual(validate_records(candidates), [])
        self.assertTrue(all(candidate["status"] == "quarantine" for candidate in candidates))
        self.assertTrue(all(candidate["split"] == "candidate" for candidate in candidates))
        self.assertTrue(all(candidate["expected_output"] is None for candidate in candidates))
        self.assertTrue(
            all(candidate["source"]["benchmark"] == "spokenform_discovered" for candidate in candidates)
        )
        self.assertTrue(
            all(candidate["source"].get("source_hash", "").startswith("sha256:") for candidate in candidates)
        )
        categories = {
            unit["category"]
            for candidate in candidates
            for unit in candidate["units"]
        }
        self.assertIn("identifier", categories)
        self.assertIn("version", categories)
        self.assertGreaterEqual(
            sum(1 for candidate in candidates if "version" in candidate["negative_for"]),
            3,
        )

    def test_candidate_source_manifest_and_train_shard_are_valid(self):
        manifest = load_and_validate_source_manifest(
            ROOT / "sources/manifest.json",
            repo_root=ROOT,
            source_names={"spokenform_discovered"},
            filter_to_source_names=True,
        )
        self.assertEqual(manifest["sources"][0]["name"], "spokenform_discovered")
        self.assertEqual(read_records([ROOT / "data/train/sample.jsonl"]), [])

    def test_train_is_first_class_in_release_data(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            release = build_release(
                version="0.2.0-train-test",
                data_paths=[
                    str(ROOT / "data/train"),
                    str(ROOT / "data/dev"),
                    str(ROOT / "data/test"),
                ],
                out_root=Path(tmpdir) / "release",
                maturity="experimental",
                registry_path=ROOT / "splits/family_assignments.json",
            )

        self.assertEqual(release["counts"]["records"], 62)
        self.assertEqual(
            build_coverage(
                read_records([ROOT / "data/train", ROOT / "data/dev", ROOT / "data/test"]),
                load_targets(ROOT / "taxonomy/coverage_targets.json"),
            )["records"],
            62,
        )


if __name__ == "__main__":
    unittest.main()
