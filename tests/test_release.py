import json
import shutil
import tempfile
import unittest
from pathlib import Path

from spokenform_gold.benchmark import load_release_records, verify_release
from spokenform_gold.coverage import build_coverage, load_targets
from spokenform_gold.io import expand_jsonl_paths, read_json, read_records
from spokenform_gold.release import _enforce_maturity, build_release

ROOT = Path(__file__).resolve().parents[1]


class ReleaseTests(unittest.TestCase):
    def test_release_builds_manifest_checksums_and_audit_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest = build_release(
                version="0.2.0-exp",
                data_paths=[
                    str(ROOT / "data/train"),
                    str(ROOT / "data/dev"),
                    str(ROOT / "data/test"),
                ],
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
            html = (output_root / "records.html").read_text(encoding="utf-8")
            self.assertIn("Spokenform Gold 0.2.0-exp", html)
            self.assertIn("Release records", html)
            release_manifest = read_json(output_root / "manifest.json")
            self.assertEqual(
                release_manifest["record_files"],
                [
                    "data/dev/sample.jsonl",
                    "data/test/sample.jsonl",
                    "data/train/sample.jsonl",
                ],
            )
            self.assertEqual(release_manifest["control_files"], [])
            self.assertEqual(release_manifest["maturity"], "experimental")
            self.assertEqual(release_manifest["record_browser"], "records.html")
            self.assertIn("records.html", release_manifest["file_hashes"])
            self.assertEqual(release_manifest["profile_registry_version"], "1.0.0")
            self.assertTrue(release_manifest["profile_registry_hash"])
            self.assertIn(
                "taxonomy/evaluation_profiles.json", release_manifest["file_hashes"]
            )
            self.assertIn("control_coverage.json", release_manifest["file_hashes"])
            self.assertIn("sources/manifest.json", release_manifest["file_hashes"])
            source_manifest = read_json(output_root / "sources/manifest.json")
            self.assertEqual(
                [source["name"] for source in source_manifest["sources"]],
                ["spokenform_curated"],
            )

    def test_v2_release_flattens_corpus_shards(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmpdir:
            tmp_root = Path(tmpdir)
            input_root = tmp_root / "corpus"
            input_root.mkdir()
            for name in ("es.jsonl", "fr.jsonl", "it.jsonl", "pt.jsonl"):
                shutil.copy2(ROOT / "data/corpus" / name, input_root / name)
            output_root = tmp_root / "release"
            manifest = build_release(
                version="0.2.0-sharded",
                data_paths=[str(input_root)],
                out_root=output_root,
                maturity="experimental",
            )
            self.assertTrue((output_root / "corpus.jsonl").is_file())
            self.assertEqual(manifest["record_files"], ["corpus.jsonl"])
            self.assertEqual(manifest["corpus_file"], "corpus.jsonl")
            _, records = load_release_records(output_root, language="es")
            self.assertGreater(len(records), 0)

    def test_release_copies_and_records_control_coverage(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = Path(tmpdir) / "release"
            manifest = build_release(
                version="0.3.0-exp",
                data_paths=[str(ROOT / "data/dev"), str(ROOT / "data/test")],
                control_paths=[str(ROOT / "data/controls")],
                out_root=output_root,
                maturity="experimental",
                registry_path=ROOT / "splits/family_assignments.json",
            )
            self.assertEqual(manifest["control_records"], 23)
            self.assertTrue(
                (output_root / "data/controls/sequence_fallback.jsonl").exists()
            )
            self.assertEqual(
                read_json(output_root / "control_coverage.json")["gaps"], []
            )

    def test_release_rejects_external_canonical_inputs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            external = Path(tmpdir) / "external.jsonl"
            external.write_text(
                (ROOT / "data/test/sample.jsonl").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "repository-local canonical data"):
                build_release(
                    version="0.2.0-exp",
                    data_paths=[str(external)],
                    out_root=Path(tmpdir) / "release",
                    maturity="experimental",
                    registry_path=ROOT / "splits/family_assignments.json",
                )

    def test_release_rejects_missing_split_registry_family(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = read_json(ROOT / "splits/family_assignments.json")
            registry["families"].pop(next(iter(registry["families"])))
            registry_path = Path(tmpdir) / "registry.json"
            registry_path.write_text(
                json.dumps(registry, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "missing from split registry"):
                build_release(
                    version="0.2.0-exp",
                    data_paths=[str(ROOT / "data/dev"), str(ROOT / "data/test")],
                    out_root=Path(tmpdir) / "release",
                    maturity="experimental",
                    registry_path=registry_path,
                )

    def test_release_rejects_split_registry_mismatch(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = read_json(ROOT / "splits/family_assignments.json")
            family_id, split = next(iter(registry["families"].items()))
            registry["families"][family_id] = "test" if split == "dev" else "dev"
            registry_path = Path(tmpdir) / "registry.json"
            registry_path.write_text(
                json.dumps(registry, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                ValueError, "does not match registry assignment"
            ):
                build_release(
                    version="0.2.0-exp",
                    data_paths=[str(ROOT / "data/dev"), str(ROOT / "data/test")],
                    out_root=Path(tmpdir) / "release",
                    maturity="experimental",
                    registry_path=registry_path,
                )

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

    def test_release_ignores_unreferenced_source_policy_failures(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            broken_manifest = Path(tmpdir) / "manifest.json"
            payload = read_json(ROOT / "sources/manifest.json")
            payload["sources"][1]["source_url"] = "https://example.invalid/source"
            broken_manifest.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            manifest = build_release(
                version="0.2.0-candidate",
                data_paths=[str(ROOT / "data/dev"), str(ROOT / "data/test")],
                out_root=Path(tmpdir) / "release",
                maturity="candidate",
                registry_path=ROOT / "splits/family_assignments.json",
                source_manifest_path=broken_manifest,
            )
            self.assertEqual(manifest["source_integrity"]["source_count"], 1)

    def test_release_rejects_embedded_restricted_source(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            restricted_manifest = Path(tmpdir) / "manifest.json"
            payload = read_json(ROOT / "sources/manifest.json")
            payload["sources"][0]["redistribution_status"] = "metadata_only"
            payload["sources"][0]["materialization_policy"] = "external_ref_only"
            restricted_manifest.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                build_release(
                    version="0.2.0-exp",
                    data_paths=[str(ROOT / "data/dev"), str(ROOT / "data/test")],
                    out_root=Path(tmpdir) / "release",
                    maturity="experimental",
                    registry_path=ROOT / "splits/family_assignments.json",
                    source_manifest_path=restricted_manifest,
                )

    def test_stable_release_requires_split_registry(self):
        with tempfile.TemporaryDirectory() as tmpdir, self.assertRaises(ValueError):
            build_release(
                version="0.2.0",
                data_paths=[str(ROOT / "data/dev"), str(ROOT / "data/test")],
                out_root=Path(tmpdir) / "release",
                maturity="stable",
                registry_path=Path(tmpdir) / "missing.json",
            )

    def test_stable_release_rejects_remaining_gaps_after_language_minimum(self):
        records = read_records(
            expand_jsonl_paths([str(ROOT / "data/dev"), str(ROOT / "data/test")])
        )
        records.append({"language": "cs"})
        coverage = build_coverage(
            records, load_targets(ROOT / "taxonomy" / "coverage_targets.json")
        )
        with self.assertRaisesRegex(
            ValueError, "stable release does not allow coverage gaps"
        ):
            _enforce_maturity(
                profile_name="stable",
                records=records,
                coverage=coverage,
                source_manifest={"sources": [{"release_ready": True}]},
            )


if __name__ == "__main__":
    unittest.main()
