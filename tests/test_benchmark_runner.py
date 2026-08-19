import tempfile
import unittest
from pathlib import Path

from spokenform_gold.benchmark import (
    load_release_control_records,
    load_release_records,
    run_benchmark,
 )
from spokenform_gold.io import read_json
from spokenform_gold.release import build_release

ROOT = Path(__file__).resolve().parents[1]


class BenchmarkRunnerTests(unittest.TestCase):
    def test_runner_loads_release_and_writes_artifacts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            release_root = Path(tmpdir) / "release"
            results_root = Path(tmpdir) / "results"
            build_release(
                version="0.2.0-exp",
                data_paths=[str(ROOT / "data/train"), str(ROOT / "data/dev"), str(ROOT / "data/test")],
                out_root=release_root,
                maturity="experimental",
                registry_path=ROOT / "splits/family_assignments.json",
            )
            summary = run_benchmark(
                gold_root=release_root,
                split="test",
                prepare_module="tests.fixtures.runner.sample_prepare:prepare_gold_record",
                results_dir=results_root,
                mode="canonical",
            )
            self.assertEqual(summary["profile_name"], "gold-v1")
            self.assertEqual(summary["profile_id"], "gold-v1")
            self.assertEqual(summary["profile_config"]["prepare_kwargs"]["sequence_fallback_mode"], "preserve")
            self.assertTrue(summary["profile_registry_hash"])
            self.assertTrue((results_root / "summary.json").exists())
            self.assertTrue((results_root / "predictions.jsonl").exists())
            self.assertTrue((results_root / "failures.jsonl").exists())
            self.assertTrue((results_root / "failures.md").exists())
            persisted = read_json(results_root / "summary.json")
            self.assertEqual(persisted["split"], "test")
            self.assertGreaterEqual(persisted["canonical_score"], 0.9)


    def test_loader_separates_controls_from_canonical_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            release_root = Path(tmpdir) / "release"
            build_release(
                version="0.2.0-exp",
                data_paths=[str(ROOT / "data/train"), str(ROOT / "data/dev"), str(ROOT / "data/test")],
                control_paths=[str(ROOT / "data/controls")],
                out_root=release_root,
                maturity="experimental",
                registry_path=ROOT / "splits/family_assignments.json",
            )
            _, records = load_release_records(release_root)
            _, controls = load_release_control_records(release_root)
            self.assertEqual(len(records), 62)
            self.assertEqual(len(controls), 23)
            self.assertTrue(all(record.get("split") in {"train", "dev", "test"} for record in records))
            self.assertTrue(all("control" in record for record in controls))


if __name__ == "__main__":
    unittest.main()
