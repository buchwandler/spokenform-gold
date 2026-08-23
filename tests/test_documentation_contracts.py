import unittest
from pathlib import Path

from spokenform_gold.cli import build_parser

ROOT = Path(__file__).resolve().parents[1]


class DocumentationContractTests(unittest.TestCase):
    def test_documented_workflow_commands_exist(self):
        help_text = build_parser().format_help()
        for command in ("review-preflight", "validate-review", "doctor", "prepare-canonical-rereview", "compare-reviews", "apply-reviewed-oracles"):
            self.assertIn(command, help_text)

    def test_canonical_templates_contain_safety_invariants(self):
        canonical = (ROOT / "templates/canonical-rereview-adjudicator-task.md").read_text()
        for text in (
            "review-preflight",
            "canonical records do not store sentence_oracle_id",
            "stop if ready=no",
            "do not inspect source evidence before preflight",
        ):
            self.assertIn(text, canonical)
        reviewer = (ROOT / "templates/reviewer-ab-task.md").read_text()
        self.assertIn("validate-review", reviewer)
        self.assertIn(".complete.jsonl", reviewer)

    def test_canonical_artifact_names_and_schemas_are_documented(self):
        paths = [
            ROOT / "README.md",
            ROOT / "AGENTS.md",
            ROOT / "docs/ORACLE_REVIEW.md",
            ROOT / "templates/README.md",
            ROOT / "spokenform-gold-template-review-and-release-runbook.md",
        ]
        combined = "\n".join(path.read_text() for path in paths)
        for name in (
            "canonical-a.blind.jsonl",
            "canonical-a.complete.jsonl",
            "canonical-b.blind.jsonl",
            "canonical-b.complete.jsonl",
            "preflight.json",
            "comparison.jsonl",
            "decisions.jsonl",
            "manifest.json",
            "schemas/canonical-review-decision.schema.json",
        ):
            self.assertIn(name, combined)
        self.assertTrue((ROOT / "templates/canonical-rereview-integration-task.md").exists())

    def test_canonical_records_do_not_require_persisted_identity(self):
        records = list((ROOT / "data/test").glob("*.jsonl"))
        self.assertTrue(records)
        for path in records:
            for line in path.read_text().splitlines():
                if line.strip():
                    self.assertNotIn('"sentence_oracle_id"', line)


if __name__ == "__main__":
    unittest.main()
