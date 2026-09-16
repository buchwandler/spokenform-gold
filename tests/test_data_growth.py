import tempfile
import unittest
from pathlib import Path

from spokenform_gold.coverage import build_coverage, load_targets
from spokenform_gold.io import read_json, read_records
from spokenform_gold.release import build_release

ROOT = Path(__file__).resolve().parents[1]


class DataGrowthTests(unittest.TestCase):
    def test_regression_candidates_are_removed(self):
        candidates_path = ROOT / "data/candidates/01_todo_regressions.jsonl"
        self.assertFalse(candidates_path.exists())

    def test_discovered_source_is_absent_from_manifest(self):
        manifest = read_json(ROOT / "sources/manifest.json")
        self.assertNotIn(
            "spokenform_discovered",
            {source["name"] for source in manifest["sources"]},
        )

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
                read_records(
                    [ROOT / "data/train", ROOT / "data/dev", ROOT / "data/test"]
                ),
                load_targets(ROOT / "taxonomy/coverage_targets.json"),
            )["records"],
            62,
        )


if __name__ == "__main__":
    unittest.main()
