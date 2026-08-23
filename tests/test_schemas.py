import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "schemas"


class ReviewSchemaTests(unittest.TestCase):
    def _load(self, name):
        return json.loads((SCHEMAS / name).read_text(encoding="utf-8"))

    def test_review_schemas_are_valid_json_contracts(self):
        for name in (
            "blind-review-row.schema.json",
            "completed-review-row.schema.json",
            "canonical-review-decision.schema.json",
            "review-task.schema.json",
            "canonical-review-manifest.schema.json",
        ):
            schema = self._load(name)
            self.assertEqual(schema["type"], "object")
            self.assertIn("$schema", schema)

    def test_canonical_decision_requires_independent_review_metadata(self):
        schema = self._load("canonical-review-decision.schema.json")
        self.assertTrue({
            "sentence_oracle_id", "record_id", "family_id", "reviewers",
            "adjudicator", "review_status", "status", "input", "language",
            "locale", "expected_output", "units", "negative_for", "notes", "oracle",
        }.issubset(schema["required"]))
        self.assertEqual(schema["properties"]["review_status"]["enum"], ["adjudicated", "release_ready"])
        self.assertNotIn("candidate_id", schema["required"])

    def test_completed_row_requires_reviewer_and_annotation(self):
        schema = self._load("completed-review-row.schema.json")
        self.assertIn("reviewer_id", schema["required"])
        self.assertIn("annotation", schema["required"])
        self.assertIn("oracle", schema["properties"]["annotation"]["required"])

    def test_manifest_accepts_explicit_artifact_hash_contract(self):
        schema = self._load("canonical-review-manifest.schema.json")
        artifact = schema["$defs"]["artifact"]
        self.assertIn("sha256", artifact["required"])
        self.assertEqual(len(artifact["anyOf"]), 2)


if __name__ == "__main__":
    unittest.main()
