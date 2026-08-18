import json
import tempfile
import unittest
from pathlib import Path

from spokenform_gold.benchmark import verify_release
from spokenform_gold.io import read_json
from spokenform_gold.release import build_release


ROOT = Path(__file__).resolve().parents[1]


class ReleaseTests(unittest.TestCase):
    def test_release_builds_manifest_checksums_and_audit_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest = build_release(
                version="0.2.0-exp",
                data_paths=[str(ROOT / "data/dev"), str(ROOT / "data/test")],
                out_root=Path(tmpdir) / "release",
                maturity="experimental",
                registry_path=ROOT / "splits/family_assignments.json",
            )
            output_root = Path(tmpdir) / "release"
            self.assertEqual(manifest["benchmark_version"], "0.2.0-exp")
            self.assertTrue((output_root / "manifest.json").exists())
            self.assertTrue((output_root / "SHA256SUMS").exists())
            self.assertTrue((output_root / "sources/manifest.json").exists())
            self.assertTrue((output_root / "splits/family_assignments.json").exists())
            self.assertTrue((output_root / "RELEASE_NOTES.md").exists())
            release_manifest = read_json(output_root / "manifest.json")
            self.assertEqual(release_manifest["maturity"], "experimental")
            self.assertIn("sources/manifest.json", release_manifest["file_hashes"])

    def test_release_verifier_detects_nested_source_manifest_tampering(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = Path(tmpdir) / "release"
            build_release(
                version="0.2.0-exp",
                data_paths=[str(ROOT / "data/dev"), str(ROOT / "data/test")],
                out_root=output_root,
                maturity="experimental",
                registry_path=ROOT / "splits/family_assignments.json",
            )
            source_manifest = output_root / "sources/manifest.json"
            payload = read_json(source_manifest)
            payload["sources"][0]["notes"] = "tampered"
            source_manifest.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                verify_release(output_root)

    def test_candidate_release_enforces_profile_gate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            single = (ROOT / "data/test/sample.jsonl").read_text(encoding="utf-8")
            data_dir = Path(tmpdir) / "data"
            data_dir.mkdir(parents=True, exist_ok=True)
            (data_dir / "sample.jsonl").write_text(
                single.splitlines()[0] + "\n", encoding="utf-8"
            )
            with self.assertRaises(ValueError):
                build_release(
                    version="0.2.0-candidate",
                    data_paths=[str(data_dir)],
                    out_root=Path(tmpdir) / "release",
                    maturity="candidate",
                    registry_path=ROOT / "splits/family_assignments.json",
                )

    def test_stable_release_rejects_placeholder_source_metadata(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            broken_manifest = Path(tmpdir) / "manifest.json"
            payload = read_json(ROOT / "sources/manifest.json")
            payload["sources"][0]["release_ready"] = True
            payload["sources"][0]["source_url"] = "https://example.invalid/source"
            broken_manifest.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                build_release(
                    version="0.2.0",
                    data_paths=[str(ROOT / "data/dev"), str(ROOT / "data/test")],
                    out_root=Path(tmpdir) / "release",
                    maturity="stable",
                    registry_path=ROOT / "splits/family_assignments.json",
                    source_manifest_path=broken_manifest,
                )

    def test_stable_release_requires_split_registry(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(ValueError):
                build_release(
                    version="0.2.0",
                    data_paths=[str(ROOT / "data/dev"), str(ROOT / "data/test")],
                    out_root=Path(tmpdir) / "release",
                    maturity="stable",
                    registry_path=Path(tmpdir) / "missing.json",
                )


if __name__ == "__main__":
    unittest.main()
