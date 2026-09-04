import tempfile
import unittest
from pathlib import Path

from spokenform_gold.io import write_json
from spokenform_gold.source_policy import (
    apply_source_decision,
    make_source_decision,
    source_manifest_hash,
    validate_source_decision,
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


if __name__ == "__main__":
    unittest.main()
