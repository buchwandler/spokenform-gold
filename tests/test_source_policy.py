import tempfile
import unittest
from pathlib import Path

from spokenform_gold.io import write_json
from spokenform_gold.source_policy import (
    apply_source_decision,
    effective_source_manifest,
    make_source_decision,
    source_manifest_hash,
    validate_source_decision,
    validate_source_decisions,
)


class SourcePolicyTests(unittest.TestCase):
    def test_decision_is_bound_to_revision_evidence_and_manifest(self):
        source = {"name": "fixture", "revision": "rev-1"}
        manifest = {"version": "1", "sources": [source]}
        with tempfile.TemporaryDirectory() as tmp:
            evidence = Path(tmp) / "LICENSE"
            evidence.write_text("fixture license", encoding="utf-8")
            decision = make_source_decision(
                source,
                decision="external_ref_only",
                manifest_hash=source_manifest_hash(manifest),
                evidence=[evidence],
                maintainer_approval={"approved": True, "actor": "maintainer"},
                root=tmp,
            )
            self.assertEqual(
                validate_source_decision(
                    decision,
                    source,
                    manifest_hash=source_manifest_hash(manifest),
                    repo_root=tmp,
                ),
                [],
            )
            stale = dict(decision, source_revision="rev-2")
            self.assertIn(
                "stale source revision",
                validate_source_decision(
                    stale,
                    source,
                    manifest_hash=source_manifest_hash(manifest),
                    repo_root=tmp,
                ),
            )

    def test_apply_is_idempotent_and_does_not_touch_canonical_records(self):
        source = {
            "name": "fixture",
            "revision": "rev-1",
            "release_ready": False,
            "materialization_policy": "review_required",
            "redistribution_status": "review_required",
        }
        manifest = {"version": "1", "sources": [source]}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence = root / "LICENSE"
            evidence.write_text("fixture license", encoding="utf-8")
            manifest_path = root / "manifest.json"
            write_json(manifest_path, manifest)
            decision = make_source_decision(
                source,
                decision="external_ref_only",
                manifest_hash=source_manifest_hash(manifest),
                evidence=[evidence],
                maintainer_approval={"approved": True, "actor": "maintainer"},
                root=tmp,
            )
            first = apply_source_decision(manifest_path, decision, write=True)
            second = apply_source_decision(manifest_path, decision, write=True)
            self.assertEqual(first, second)
            self.assertTrue(second["sources"][0]["release_ready"])
            self.assertEqual(
                second["sources"][0]["materialization_policy"], "external_ref_only"
            )

    def test_effective_manifest_applies_decisions_without_mutating_base(self):
        source = {
            "name": "fixture",
            "revision": "rev-1",
            "release_ready": False,
            "materialization_policy": "review_required",
            "redistribution_status": "review_required",
        }
        manifest = {"version": "1", "sources": [source]}
        with tempfile.TemporaryDirectory() as tmp:
            evidence = Path(tmp) / "LICENSE"
            evidence.write_text("fixture license", encoding="utf-8")
            decision = make_source_decision(
                source,
                decision="exclude_public",
                manifest_hash=source_manifest_hash(manifest),
                evidence=[evidence],
                maintainer_approval={"approved": True, "actor": "maintainer"},
                root=tmp,
            )
            effective = effective_source_manifest(
                manifest, [decision], repo_root=tmp, require_all=True
            )
        self.assertFalse(manifest["sources"][0]["release_ready"])
        self.assertTrue(effective["sources"][0]["release_ready"])
        self.assertEqual(
            effective["sources"][0]["effective_source_policy_decision"],
            "exclude_public",
        )
        self.assertEqual(
            effective["sources"][0]["redistribution_status"],
            "not_redistributable",
        )

    def test_decision_set_rejects_duplicates_and_missing_sources(self):
        manifest = {
            "version": "1",
            "sources": [{"name": "fixture", "revision": "rev-1"}],
        }
        decision = {"source": "fixture"}
        errors = validate_source_decisions([decision, decision], manifest)
        self.assertIn("duplicate source decision: fixture", errors)
        self.assertIn("fixture: stale source revision", errors)
        self.assertTrue(
            any(
                error.startswith("missing source decision:")
                for error in validate_source_decisions([], manifest, require_all=True)
            )
        )


if __name__ == "__main__":
    unittest.main()
