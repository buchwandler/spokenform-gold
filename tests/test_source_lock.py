import unittest
from pathlib import Path

from spokenform_gold.source_lock import build_source_lock

ROOT = Path(__file__).resolve().parents[1]


class SourceLockTests(unittest.TestCase):
    def test_lock_preserves_source_policy_and_observes_local_fixture_hashes(self):
        lock = build_source_lock(ROOT / "sources/manifest.json")
        sources = {entry["name"]: entry for entry in lock["sources"]}
        self.assertEqual(
            sources["async_tn"]["revision"], "ad8fa8152279bb13c0ded87e3d465494c319da30"
        )
        self.assertEqual(
            sources["polynorm"]["materialization_policy"], "external_ref_only"
        )
        self.assertEqual(sources["proteno_ta"]["license_scope"], "language:ta")
        async_artifacts = sources["async_tn"]["artifacts"]
        self.assertTrue(
            all("observed_sha256" in artifact for artifact in async_artifacts)
        )

    def test_lock_is_deterministic(self):
        path = ROOT / "sources/manifest.json"
        self.assertEqual(build_source_lock(path), build_source_lock(path))


if __name__ == "__main__":
    unittest.main()
