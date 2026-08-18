import tempfile
import unittest
from pathlib import Path

from spokenform_gold.release import build_release


ROOT = Path(__file__).resolve().parents[1]


class ReleaseTests(unittest.TestCase):
    def test_release_builds_manifest_and_checksums(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest = build_release(version="0.1.0", data_paths=[str(ROOT / "data/dev"), str(ROOT / "data/test")], out_root=Path(tmpdir) / "release")
            output_root = Path(tmpdir) / "release"
            self.assertEqual(manifest["benchmark_version"], "0.1.0")
            self.assertTrue((output_root / "manifest.json").exists())
            self.assertTrue((output_root / "SHA256SUMS").exists())
            self.assertTrue((output_root / "data/dev/sample.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
